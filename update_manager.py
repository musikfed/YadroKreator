"""Controlled Git update and one-step rollback for the Huananzhi dashboard.

Only the fixed YadroKreator origin/main is trusted. No user-controlled
paths, commands or commit SHAs. Actions run in separate systemd user units.
"""
from __future__ import annotations

import fcntl
import contextvars
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core import ROOT, DATA, DB

APP = ROOT / "projects" / "YadroKreator"
VENV = ROOT / "factory-venv"
STATE_FILE = DATA / "updates.json"
LOCK_FILE = DATA / "updates.lock"
# An updater is one detached systemd process. Contextvars prevent command
# output from leaking into another operation if tests run in-process.
_CURRENT_OP = contextvars.ContextVar("dashboard_update_op", default="")
ORIGIN = "https://github.com/musikfed/YadroKreator.git"
SHA = re.compile(r"^[0-9a-f]{40}$")
ACTIONS = ("check", "apply", "rollback")
BUSY = ("queued", "running")
# Distinct steps for the UI. The percentages reflect deployment milestones,
# never promise a wall-clock ETA.
STEP_ORDER = ("queued", "fetch", "checkout", "dependencies", "tests", "restart", "done")
STEP_INDEX = {name: index for index, name in enumerate(STEP_ORDER)}


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def locked():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOCK_FILE.open("a+b") as handle:
        os.chmod(LOCK_FILE, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text())


def _write(state: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".updates-", dir=DATA)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, STATE_FILE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _log_file(operation: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", operation):
        raise ValueError("Invalid update operation ID")
    return DATA / "update-logs" / (operation + ".log")


def append_log(operation: str, message: str) -> None:
    """Write only updater diagnostics, *never* the firmware build log."""
    if not operation:
        return
    (DATA / "update-logs").mkdir(parents=True, exist_ok=True, mode=0o700)
    with _log_file(operation).open("a", encoding="utf-8") as stream:
        os.chmod(_log_file(operation), 0o600)
        stream.write("[" + stamp() + "] " + message.strip()[-12000:] + "\n")


def log_tail(operation: str, limit: int = 6000) -> str:
    """Bound response size; no paths, user input or raw shell arguments."""
    if not operation or not re.fullmatch(r"[0-9a-f]{32}", operation):
        return ""
    try:
        with _log_file(operation).open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - limit))
            return stream.read().decode("utf-8", "replace")[-limit:]
    except OSError:
        return ""


def run(cmd: list[str], timeout: int = 90, *, stream: bool = False) -> str:
    """Git commands capture stdout; slow installer steps stream to private log.

    A backend restart cannot erase log output because it is on disk, and
    '/api/update' can display its tail without reading the kernel-build log.
    """
    operation = _CURRENT_OP.get()
    if stream and operation:
        path = _log_file(operation)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("ab") as output:
            os.chmod(path, 0o600)
            output.write(("[" + stamp() + "] Start installer step\n").encode())
            output.flush()
            result = subprocess.run(cmd, stdout=output, stderr=subprocess.STDOUT,
                                    cwd=str(APP), timeout=timeout)
        if result.returncode:
            raise RuntimeError(log_tail(operation, 1600) or "Installer step failed")
        return ""
    result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout,
                            cwd=str(APP))
    output = (result.stdout + "\n" + result.stderr).strip()
    if output and operation:
        append_log(operation, output[-7000:])
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-1600:]
                           or "Updater command failed")
    return result.stdout.strip()


def git(*args: str, timeout: int = 90) -> str:
    return run(["git", "-C", str(APP), *args], timeout=timeout)


def installed() -> str:
    try:
        return git("rev-parse", "--verify", "HEAD", timeout=5)
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return ""


def view() -> dict:
    with locked():
        state = _read()
    current = installed()
    state.setdefault("phase", "idle")
    state.setdefault("action", "")
    state.setdefault("checked_at", "")
    state.setdefault("remote_sha", "")
    state.setdefault("rollback_sha", "")
    state.setdefault("step", "idle")
    state.setdefault("step_index", 0)
    state.setdefault("step_total", len(STEP_ORDER)-1)
    state["installed_sha"] = current
    state["update_available"] = bool(state["remote_sha"] and
                                    state["remote_sha"] != current and
                                    state.get("can_fast_forward"))
    state["operation_log"] = log_tail(state.get("operation", ""))
    state["rollback_available"] = bool(state.get("rollback_sha")
                                       and state.get("rollback_from") == current)
    return state


def mark_step(operation: str, step: str, message: str) -> None:
    """Persist each stage before running a potentially slow command.

    Browser restarts/reconnects can read the same progress from updates.json.
    """
    if step not in STEP_INDEX:
        raise ValueError("Unknown deployment step")
    with locked():
        s = _read()
        if s.get("operation") != operation:
            return
        s.update(step=step, step_index=STEP_INDEX[step],
                 step_total=len(STEP_ORDER)-1,
                 message=message[:350], updated_at=stamp())
        _write(s)
    append_log(operation, "STAGE " + step + ": " + message)


def builds_active() -> bool:
    if DB.exists():
        db = sqlite3.connect(DB, timeout=4)
        try:
            return bool(db.execute(
                "SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1"
            ).fetchone())
        finally:
            db.close()
    return False


def check_preconditions() -> None:
    if os.geteuid() == 0:
        raise RuntimeError("Updater must not run as root")
    if not (APP / ".git").is_dir():
        raise RuntimeError("YadroKreator Git checkout missing")
    if git("symbolic-ref", "--short", "HEAD", timeout=5) != "main":
        raise RuntimeError("Updater requires YadroKreator main")
    if git("remote", "get-url", "origin", timeout=5) != ORIGIN:
        raise RuntimeError("Unexpected Git origin")
    if git("status", "--porcelain", "--untracked-files=no", timeout=10):
        raise RuntimeError("Tracked local changes: refusing overwrite")
    if not (VENV / "bin" / "python").is_file():
        raise RuntimeError("Python venv missing")


def check_remote() -> tuple[str, str, bool]:
    check_preconditions()
    git("fetch", "--no-tags", "origin",
        "refs/heads/main:refs/remotes/origin/main", timeout=180)
    current = git("rev-parse", "--verify", "HEAD")
    target = git("rev-parse", "--verify", "refs/remotes/origin/main^{commit}")
    if not SHA.fullmatch(current) or not SHA.fullmatch(target):
        raise RuntimeError("Invalid Git commit SHA")
    ancestor = subprocess.run(["git", "-C", str(APP), "merge-base",
                               "--is-ancestor", current, target], timeout=10)
    return current, target, ancestor.returncode == 0


def start(action: str, expected: str = "") -> dict:
    if action not in ACTIONS:
        raise ValueError("Unsupported update action")
    with locked():
        state = _read()
        if state.get("phase") in BUSY:
            raise RuntimeError("Another update operation is already running")
        if action != "check" and builds_active():
            raise RuntimeError("Build is active; update/rollback is blocked")
        if action == "apply":
            if not SHA.fullmatch(expected) or expected != state.get("remote_sha"):
                raise RuntimeError("Check for updates again before applying")
            if not state.get("can_fast_forward") or expected == installed():
                raise RuntimeError("No safe fast-forward update available")
        if action == "rollback":
            if not SHA.fullmatch(state.get("rollback_sha", "")):
                raise RuntimeError("No recorded previous successful version")
            if installed() != state.get("rollback_from"):
                raise RuntimeError("Installed version changed; rollback blocked")
        operation = uuid.uuid4().hex
        state.update(phase="queued", action=action, operation=operation,
                     expected_sha=expected, message="Queued in systemd",
                     started_at=stamp(), updated_at=stamp(),
                     step="queued", step_index=0, step_total=len(STEP_ORDER)-1,
                     launch="cli", failed_step="")
        _write(state)
    append_log(operation, action.upper() + " requested")
    return state


def finish(operation: str, phase: str, message: str, **changes) -> None:
    with locked():
        s = _read()
        if s.get("operation") != operation:
            return
        if phase == "failed":
            s["failed_step"] = s.get("step", "queued")
        s.update(phase=phase, message=message[-1600:], finished_at=stamp(),
                 updated_at=stamp(),
                 step=("done" if phase == "success" else "failed"),
                 step_index=(len(STEP_ORDER)-1 if phase == "success" else
                             s.get("step_index", 0)), **changes)
        _write(s)
    append_log(operation, "FINISH " + phase.upper() + ": " + message[-1600:])


def pending(operation: str) -> dict:
    with locked():
        s = _read()
        if s.get("operation") != operation or s.get("phase") != "queued":
            raise RuntimeError("Invalid update operation")
        s["phase"] = "running"
        s["message"] = "Запуск " + s["action"]
        s["updated_at"] = stamp()
        _write(s)
    return s


def verify_and_restart(operation: str = "") -> None:
    """Run installed requirements/tests, then restart *only* the web panel.

    The updater runs as a detached systemd user unit. Restarting Waitress
    cannot terminate this worker or erase state recorded in updates.json.
    """
    py = str(VENV / "bin" / "python")
    if operation:
        mark_step(operation, "dependencies", "Установка зависимостей Python")
    run([py, "-m", "pip", "install", "--disable-pip-version-check",
         "-r", str(APP / "requirements.txt")], timeout=240, stream=True)
    if operation:
        mark_step(operation, "tests", "Проверяем Python, JavaScript и тесты проекта")
    run([py, "-m", "unittest", "discover", "-s", str(APP / "tests"),
         "-p", "test_*.py", "-v"], timeout=180, stream=True)
    run([py, "-m", "compileall", "-q", str(APP / "app.py"),
         str(APP / "core.py"), str(APP / "worker.py"),
         str(APP / "git_sources.py"), str(APP / "artifact_checks.py"),
         str(APP / "build_metrics.py"), str(APP / "update_manager.py")], timeout=30)
    run(["bash", "-n", str(APP / "deploy.sh"), str(APP / "install.sh"),
         str(APP / "bootstrap.sh"), str(APP / "setup-update-timer.sh")], timeout=30)
    if operation:
        mark_step(operation, "restart", "Перезапуск веб-панели и проверка службы")
    run(["systemctl", "--user", "restart", "peginelab-factory.service"],
        timeout=40)
    run(["systemctl", "--user", "is-active", "--quiet",
         "peginelab-factory.service"], timeout=20)


def switch_to(target: str, *, rollback: bool) -> None:
    if not SHA.fullmatch(target):
        raise RuntimeError("Invalid saved SHA")
    check_preconditions()
    if builds_active():
        raise RuntimeError("Build is active; refusing dashboard change")
    if rollback:
        # Only restore a SHA saved on the previous successful deployment,
        # never a SHA submitted by the browser.
        git("reset", "--hard", target, timeout=30)
    else:
        git("merge", "--ff-only", target, timeout=30)


def perform(operation: str) -> None:
    s = pending(operation)
    token = _CURRENT_OP.set(operation)
    action = s["action"]
    before = ""
    changed = False
    try:
        if action == "check":
            mark_step(operation, "fetch", "Проверка GitHub main")
            current, remote, safe = check_remote()
            finish(operation, "success", ("Обновление доступно" if
                   current != remote and safe else
                   "Версия актуальна" if current == remote else
                   "Ветки разошлись: автоматическое обновление запрещено"),
                   remote_sha=remote, can_fast_forward=safe,
                   checked_at=stamp())
            return
        if builds_active():
            raise RuntimeError("Build is running; stop/finish it before updating")
        if action == "apply":
            mark_step(operation, "fetch", "Получение проверенной версии с GitHub")
            before, target, safe = check_remote()
            if not safe or target != s["expected_sha"] or target == before:
                raise RuntimeError("Git main changed since check; check updates again")
            mark_step(operation, "checkout", "Обновление файлов Git (fast-forward)")
            switch_to(target, rollback=False)
            changed = True
            verify_and_restart(operation)
            finish(operation, "success", "Установлено обновление " + target[:12],
                   rollback_sha=before, rollback_from=target,
                   remote_sha=target, checked_at=stamp(), can_fast_forward=True)
        elif action == "rollback":
            check_preconditions()
            before = installed()
            target = s["rollback_sha"]
            if before != s.get("rollback_from") or not SHA.fullmatch(target):
                raise RuntimeError("Recorded rollback is no longer applicable")
            mark_step(operation, "checkout", "Восстановление сохранённого Git SHA")
            git("merge-base", "--is-ancestor", target, before, timeout=10)
            switch_to(target, rollback=True)
            changed = True
            verify_and_restart(operation)
            finish(operation, "success", "Восстановлена предыдущая версия " + target[:12],
                   rollback_sha="", rollback_from="", can_fast_forward=True)
        else:
            raise RuntimeError("Unknown operation")
    except Exception as exc:
        # Keep the original failing stage even when auto-recovery switches
        # to checkout/restart stages afterwards.
        with locked():
            original_failure_step = _read().get("step", "queued")
        error = str(exc)
        if changed and before:
            try:
                # The automatic fallback returns to the previously working
                # revision, without touching external build worktrees/data.
                if not git("status", "--porcelain", "--untracked-files=no"):
                    mark_step(operation, "checkout", "Ошибка! Возврат к прежней версии")
                    git("reset", "--hard", before, timeout=30)
                    verify_and_restart(operation)
                    error += "; прежняя версия восстановлена"
                else:
                    error += "; локальные изменения, автоматический возврат запрещён"
            except Exception as recovery:
                error += "; ОШИБКА ВОССТАНОВЛЕНИЯ: " + str(recovery)
        finish(operation, "failed", error, failed_step=original_failure_step)
    finally:
        _CURRENT_OP.reset(token)


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not re.fullmatch(r"[0-9a-f]{32}", argv[1]):
        raise SystemExit("Usage: python update_manager.py OPERATION_ID")
    perform(argv[1])
    with locked():
        state = _read()
    return 0 if state.get("phase") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
