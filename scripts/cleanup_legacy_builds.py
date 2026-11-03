#!/usr/bin/env python3
"""Explicit, guarded retirement of pre-isolation factory results.

Dry-run by default. Delete ONLY the old shared build/jobs/<uuid> worktrees,
old shared logs/validation and matching finished SQLite job rows. Never touch
projects/, the current per-project build trees, Thingino or any SD baseline.

Usage:
    python3 scripts/cleanup_legacy_builds.py
    python3 scripts/cleanup_legacy_builds.py --apply --confirm DELETE-LEGACY-JOBS
    python3 scripts/cleanup_legacy_builds.py --apply --confirm DELETE-LEGACY-JOBS --prune-old-git-cache
"""
from __future__ import annotations

import argparse
import fcntl
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
ACTIVE = ("queued", "running", "stopping")
PHRASE = "DELETE-LEGACY-JOBS"
OLD_CACHES = ("wificam_T23N.git", "Irila_baikal_v1.0.git")


class CleanupError(RuntimeError):
    pass


def _safe_root(root: Path) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise CleanupError("PegineLab root is missing or symlinked")
    return root.resolve()


def _check_anchors(root: Path) -> None:
    """Do not let any symlinked ancestor redirect a cleanup outside CORE."""
    for relative in (
        "build", "build/jobs", "build/git-cache", "build/locks",
        "factory-state", "factory-state/logs", "factory-state/validation",
    ):
        item = root / relative
        if item.is_symlink():
            raise CleanupError("Refusing symlinked cleanup anchor: " + str(item))
        if item.exists() and not item.resolve().is_relative_to(root):
            raise CleanupError("Cleanup anchor escaped PegineLab root")


def _within(child: Path, parent: Path) -> bool:
    return not child.is_symlink() and child.resolve().is_relative_to(parent.resolve())


def plan(root: Path, *, caches: bool = False) -> dict:
    root = _safe_root(root)
    _check_anchors(root)
    data = root / "factory-state"
    database = data / "factory.sqlite3"
    if database.is_symlink():
        raise CleanupError("Refusing symlinked factory database")

    legacy_jobs = root / "build" / "jobs"
    legacy_logs = data / "logs"
    legacy_validation = data / "validation"
    selected: list[Path] = []
    db_ids: list[str] = []
    active: list[str] = []

    if database.is_file():
        db = sqlite3.connect(database)
        try:
            jobs = db.execute("SELECT id,status,log_path FROM jobs").fetchall()
        except sqlite3.Error as exc:
            raise CleanupError("Cannot inspect factory SQLite history") from exc
        finally:
            db.close()

        for job_id, status, log in jobs:
            if status in ACTIVE:
                active.append(str(job_id))
                continue
            if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
                continue
            # Only legacy job rows: newer jobs have project-specific log paths.
            if log != str(legacy_logs / (job_id + ".log")):
                continue
            db_ids.append(job_id)
            for path in (
                legacy_jobs / job_id, legacy_logs / (job_id + ".log"),
                legacy_validation / (job_id + ".json"),
            ):
                if path.is_symlink():
                    raise CleanupError("Refusing symlinked legacy result: " + str(path))
                if path.exists():
                    parent = path.parent
                    if parent.is_symlink() or not _within(path, parent):
                        raise CleanupError("Unsafe legacy result path")
                    selected.append(path)

    if caches:
        directory = root / "build" / "git-cache"
        if directory.is_symlink():
            raise CleanupError("Refusing symlinked old Git cache root")
        for filename in OLD_CACHES:
            path = directory / filename
            if path.is_symlink():
                raise CleanupError("Refusing symlinked old Git cache")
            if path.exists():
                if not _within(path, directory):
                    raise CleanupError("Unsafe Git cache path")
                selected.append(path)
    return {
        "root": str(root),
        "active_jobs": active,
        "finished_legacy_job_ids": sorted(db_ids),
        "delete_paths": sorted(set(map(str, selected))),
        "prune_git_cache": caches,
    }


def run(root: Path, *, apply: bool = False, confirm: str = "", caches: bool = False) -> dict:
    root = _safe_root(root)
    _check_anchors(root)
    # Cooperate with the worker's global file lock. A running job aborts cleanup.
    lock_path = root / "build" / "locks" / "factory-build.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_symlink():
        raise CleanupError("Unsafe build lock")
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CleanupError("Factory worker is running; refusing cleanup") from exc

        report = plan(root, caches=caches)
        if report["active_jobs"]:
            raise CleanupError("Factory has active/queued/stopping jobs; refusing cleanup")
        if not apply:
            return report
        if confirm != PHRASE:
            raise CleanupError("Deletion requires --apply --confirm " + PHRASE)

        data = root / "factory-state"
        database = data / "factory.sqlite3"
        if database.is_file():
            db = sqlite3.connect(database, timeout=10)
            try:
                db.execute("BEGIN IMMEDIATE")
                active = db.execute(
                    "SELECT 1 FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1"
                ).fetchone()
                if active:
                    raise CleanupError("A job became active; refusing cleanup")
                # Paths and matching job IDs come solely from inspected legacy
                # rows, and are allowlisted to dedicated old directories.
                _check_anchors(root)
                for file in report["delete_paths"]:
                    path = Path(file)
                    if path.is_symlink():
                        raise CleanupError("Symlink appeared during cleanup")
                    if path.is_dir():
                        shutil.rmtree(path)
                    elif path.is_file():
                        path.unlink()
                for job_id in report["finished_legacy_job_ids"]:
                    db.execute(
                        "DELETE FROM jobs WHERE id=? AND status NOT IN ('queued','running','stopping') "
                        "AND log_path=?",
                        (job_id, str(data / "logs" / (job_id + ".log"))),
                    )
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()
        elif report["delete_paths"]:
            # Only old bare caches can exist with no old database.
            for filename in report["delete_paths"]:
                path = Path(filename)
                if path.is_dir():
                    shutil.rmtree(path)
        report["applied"] = True
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run legacy PegineLab job cleanup")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--prune-old-git-cache", action="store_true",
                        help="also remove only old bare caches from build/git-cache")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        print("Refusing root: use the regular YadroKreator service user", file=sys.stderr)
        return 2
    root = Path(os.environ.get("PEGINELAB_HOME", "/1tbdisk/PegineLab"))
    try:
        result = run(root, apply=args.apply, confirm=args.confirm,
                     caches=args.prune_old_git_cache)
        print(("DELETED" if args.apply else "DRY RUN — nothing removed"))
        print("Old jobs:", len(result["finished_legacy_job_ids"]))
        for path in result["delete_paths"]:
            print("  ", path)
        print("Source trees in projects/, new build/projects/, and Thingino baseline: NEVER targeted")
        return 0
    except (CleanupError, OSError, sqlite3.Error) as exc:
        print("CLEANUP REFUSED:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
