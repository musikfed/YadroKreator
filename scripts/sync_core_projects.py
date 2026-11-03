#!/usr/bin/env python3
"""Safe GitHub checkout/update of sibling CORE projects.

No hard reset, no clean, no branch switching and no remote branch deletion.
Factory self-update is delegated to the existing tested updater (--with-factory).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

ROOT_DEFAULT = Path("/1tbdisk/PegineLab")
REPOS = {
    "wificam_T23N": "https://github.com/musikfed/wificam_T23N.git",
    "wifcam_helper": "https://github.com/musikfed/wifcam_helper.git",
    "Irila_baikal_v1.0": "https://github.com/musikfed/Irila_baikal_v1.0.git",
}
FACTORY_URL = "https://github.com/musikfed/YadroKreator.git"
ALLOWED = {"main", "mymarrchWFcam"}  # never fast-forward the hardware baseline
SHA = re.compile(r"[a-f0-9]{40}\Z")


class SyncError(RuntimeError):
    pass


def invoke(*args: str, capture: bool = True, timeout: int = 180) -> str:
    result = subprocess.run(args, check=False, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None, timeout=timeout)
    if result.returncode:
        raise SyncError(f"{' '.join(args[:4])}: {result.stderr[-1500:] if capture else 'command failed'}")
    return result.stdout.strip() if capture else ""


def check_root(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise SyncError("PegineLab root missing or symlinked")
    base = root.resolve()
    projects = base / "projects"
    if projects.is_symlink() or not projects.is_dir():
        raise SyncError("projects/ missing or symlinked")
    return base


def ensure_idle(root: Path) -> None:
    path = root / "factory-state/factory.sqlite3"
    if path.is_symlink():
        raise SyncError("Factory SQLite symlink refused")
    if not path.is_file():
        return
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    try:
        busy = db.execute(
            "SELECT id FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1"
        ).fetchone()
        if busy:
            raise SyncError("Factory job active: " + str(busy[0]) + "; no project update")
    except sqlite3.Error as exc:
        raise SyncError("Could not safely inspect factory SQLite") from exc
    finally:
        db.close()


def origin_ok(remote: str, expected: str) -> bool:
    owner_and_repo = expected.removeprefix("https://github.com/").removesuffix(".git")
    return remote in (expected, expected.removesuffix(".git"),
                      f"git@github.com:{owner_and_repo}.git",
                      f"git@github.com:{owner_and_repo}")


def inspect_checkout(directory: Path, url: str) -> dict:
    if directory.is_symlink() or not directory.is_dir() or not (directory / ".git").is_dir():
        raise SyncError(f"{directory}: not a standard Git checkout; refusing to replace it")
    remote = invoke("git", "-C", str(directory), "remote", "get-url", "origin")
    if not origin_ok(remote, url):
        raise SyncError(f"{directory}: unexpected Git origin, refusing update")
    branch = invoke("git", "-C", str(directory), "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch not in ALLOWED:
        raise SyncError(f"{directory}: branch {branch!r} is not allowlisted; do not reset it")
    if directory.name != "wificam_T23N" and branch != "main":
        raise SyncError(f"{directory}: expected main, got {branch!r}")
    dirty = invoke("git", "-C", str(directory), "status", "--porcelain", "--untracked-files=normal")
    if dirty:
        raise SyncError(f"{directory}: local modifications/untracked files; manual inspection required")
    sha = invoke("git", "-C", str(directory), "rev-parse", "--verify", "HEAD")
    if not SHA.fullmatch(sha):
        raise SyncError("Invalid local Git SHA")
    return {"directory": str(directory), "branch": branch, "local_sha": sha}


def sync_one(root: Path, name: str, *, apply: bool) -> dict:
    if name not in REPOS:
        raise SyncError("Unknown project")
    directory = root / "projects" / name
    url = REPOS[name]
    if directory.is_symlink():
        raise SyncError("Symlinked project refused: " + str(directory))
    if not directory.exists():
        if not apply:
            return {"project": name, "action": "WOULD CLONE", "branch": "main"}
        invoke("git", "clone", "--branch", "main", "--single-branch", "--no-tags",
               url, str(directory), capture=False, timeout=600)
        state = inspect_checkout(directory, url)
        return {"project": name, "action": "CLONED", **state}
    state = inspect_checkout(directory, url)
    if not apply:
        return {"project": name, "action": "WOULD FETCH / FAST-FORWARD", **state}
    # Explicitly do not change the chosen branch. In particular do NOT force
    # a WIFICAM working checkout from mymarrchWFcam onto main.
    branch = state["branch"]
    invoke("git", "-C", str(directory), "fetch", "--no-tags", "origin",
           f"+refs/heads/{branch}:refs/remotes/origin/{branch}", capture=False)
    # Fail unless the currently checked out branch can fast-forward.
    invoke("git", "-C", str(directory), "merge", "--ff-only", f"refs/remotes/origin/{branch}",
           capture=False)
    state = inspect_checkout(directory, url)
    return {"project": name, "action": "UPDATED / NO RESET", **state}


def sync(root: Path, *, apply: bool, with_factory: bool = False) -> list[dict]:
    root = check_root(root)
    if apply:
        ensure_idle(root)
    results = []
    for name in REPOS:
        results.append(sync_one(root, name, apply=apply))
    if with_factory:
        factory = root / "projects/YadroKreator"
        if not factory.is_dir() or factory.is_symlink():
            raise SyncError("Factory checkout missing")
        state = inspect_checkout(factory, FACTORY_URL)
        if state["branch"] != "main":
            raise SyncError("Factory must be on main; use its approved updater")
        if apply:
            # Already implements SHA comparison, test gate, service restart and
            # rollback. Never implement competing git reset/pull here.
            invoke("bash", str(factory / "deploy.sh"), "--apply",
                   capture=False, timeout=1200)
            results.append({"project": "YadroKreator", "action": "FACTORY UPDATER", **state})
        else:
            results.append({"project": "YadroKreator", "action": "WOULD CALL deploy.sh --apply", **state})
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Safely sync PegineLab sibling projects from GitHub")
    p.add_argument("--apply", action="store_true", help="clone/fetch/fast-forward projects")
    p.add_argument("--with-factory", action="store_true", help="also run approved factory deploy.sh --apply")
    args = p.parse_args(argv)
    if os.geteuid() == 0:
        print("Run as normal CORE user, not sudo/root", file=sys.stderr)
        return 2
    root = Path(os.environ.get("PEGINELAB_HOME", str(ROOT_DEFAULT)))
    try:
        print("SYNC" if args.apply else "DRY RUN", "ROOT", root, flush=True)
        for result in sync(root, apply=args.apply, with_factory=args.with_factory):
            print(result, flush=True)
        print("No reset, clean, reflashing, deletion or branch switching performed.")
        return 0
    except (SyncError, OSError, subprocess.TimeoutExpired) as exc:
        print("SYNC REFUSED:", str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
