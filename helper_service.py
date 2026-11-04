"""Independent Helper project inventory and fixed-unit lifecycle.

Never imports code from wifcam_helper or touches firmware jobs. No arbitrary
shell, Docker daemon, GPU, camera SSH, or private report payload over HTTP.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import subprocess

from core import ROOT

HELPER_UNIT = "peginelab-wifcam-helper.service"


def _cmd(*args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            list(args), timeout=5, capture_output=True, text=True, check=False
        )
        return result.returncode, result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def status(root: Path = ROOT, state: Path | None = None) -> dict:
    source = root / "projects" / "wifcam_helper"
    state = state if state is not None else Path.home() / ".local/state/wifcam-helper"
    present = (source / "wifcam_helper" / "web.py").is_file()
    sha = ""
    if present and (source / ".git").exists():
        code, output = _cmd("git", "-C", str(source), "rev-parse", "HEAD")
        if code == 0 and len(output) == 40 and all(c in "0123456789abcdef" for c in output):
            sha = output
    unit_code, _ = _cmd("systemctl", "--user", "cat", HELPER_UNIT)
    installed = unit_code == 0
    if installed:
        work_code, work = _cmd("systemctl", "--user", "show",
                               "--property=WorkingDirectory", "--value", HELPER_UNIT)
        exec_code, exec_detail = _cmd("systemctl", "--user", "show",
                                      "--property=ExecStart", "--value", HELPER_UNIT)
        installed = (work_code == 0 and work == str(source)
                     and exec_code == 0 and "-m wifcam_helper web" in exec_detail)
    if installed:
        _, output = _cmd("systemctl", "--user", "is-active", HELPER_UNIT)
        service = output if output in (
            "active", "inactive", "failed", "activating", "deactivating", "reloading"
        ) else "unknown"
    else:
        service = "not-installed"
    count = None
    last_test = None
    db = state / "history.sqlite3"
    if db.is_file() and not db.is_symlink():
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2)
            try:
                count = con.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
                row = con.execute(
                    "SELECT test_name FROM reports ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
                last_test = row[0] if row else None
            finally:
                con.close()
        except (sqlite3.DatabaseError, OSError):
            pass
    return {
        "name": "WifCam Helper",
        "source": str(source),
        "source_present": present,
        "source_sha": sha,
        "service_unit": HELPER_UNIT,
        "service_installed": installed,
        "service_state": service,
        "bind": "127.0.0.1:8765",
        "access": "SSH localhost tunnel only",
        "report_database": str(db),
        "report_count": count,
        "last_test": last_test,
        "factory_database": str(root / "factory-state/factory.sqlite3"),
        "independent_from_firmware": True,
    }


def lifecycle(action: str) -> bool:
    if action not in ("start", "stop", "restart"):
        raise ValueError("Unsupported Helper action")
    code, _ = _cmd("systemctl", "--user", action, HELPER_UNIT)
    return code == 0
