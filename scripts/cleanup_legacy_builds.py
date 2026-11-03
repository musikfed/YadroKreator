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
import json
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
        "build", "build/jobs", "build/git-cache", "build/cache", "build/tmp", "build/locks",
        "factory-state", "factory-state/logs", "factory-state/validation",
    ):
        item = root / relative
        if item.is_symlink():
            raise CleanupError("Refusing symlinked cleanup anchor: " + str(item))
        if item.exists() and not item.resolve().is_relative_to(root):
            raise CleanupError("Cleanup anchor escaped PegineLab root")


def _verify_no_dashboard_update(root: Path) -> None:
    """Never remove old shared caches during a dashboard apply/rollback."""
    state = root / "factory-state" / "updates.json"
    if state.is_symlink():
        raise CleanupError("Refusing symlinked updater state")
    if not state.is_file():
        return
    try:
        if state.stat().st_size > 128_000:
            raise CleanupError("Updater state unexpectedly large")
        status = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise CleanupError("Cannot verify YadroKreator updater is idle") from exc
    if not isinstance(status, dict):
        raise CleanupError("Invalid updater state")
    if status.get("phase") in ("queued", "running"):
        raise CleanupError("YadroKreator update is running; refuse legacy cleanup")


def _within(child: Path, parent: Path) -> bool:
    return not child.is_symlink() and child.resolve().is_relative_to(parent.resolve())


def plan(root: Path, *, caches: bool = False, orphans: bool = False, shared_cache: bool = False) -> dict:
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
    existing_ids: set[str] = set()
    orphan_ids: set[str] = set()

    if database.is_file():
        db = sqlite3.connect(database)
        try:
            jobs = db.execute("SELECT id,status,log_path FROM jobs").fetchall()
        except sqlite3.Error as exc:
            raise CleanupError("Cannot inspect factory SQLite history") from exc
        finally:
            db.close()

        for job_id, status, log in jobs:
            existing_ids.add(str(job_id))
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

    # Optional orphan scan: only precisely named old UUID worktrees/logs
    # with NO matching row in SQLite. Never recurse into project trees.
    if orphans:
        for directory, suffix, is_directory in (
            (legacy_jobs, "", True),
            (legacy_logs, ".log", False),
            (legacy_validation, ".json", False),
        ):
            if not directory.is_dir():
                continue
            for candidate in directory.iterdir():
                basename = candidate.name
                job_id = basename[:-len(suffix)] if suffix else basename
                if not JOB_ID.fullmatch(job_id) or job_id in existing_ids:
                    continue
                if candidate.is_symlink() or not _within(candidate, directory):
                    raise CleanupError("Refusing unsafe orphan path " + str(candidate))
                if (candidate.is_dir() if is_directory else candidate.is_file()):
                    orphan_ids.add(job_id)
                    selected.append(candidate)

    if shared_cache:
        for dirname in ("cache", "tmp"):
            path = root / "build" / dirname
            if path.is_symlink():
                raise CleanupError("Refusing symlinked shared cache")
            if path.is_dir():
                if not _within(path, root / "build"):
                    raise CleanupError("Unsafe old shared cache path")
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
        "orphan_legacy_job_ids": sorted(orphan_ids),
        "delete_paths": sorted(set(map(str, selected))),
        "prune_git_cache": caches,
        "prune_shared_cache": shared_cache,
    }


def run(root: Path, *, apply: bool = False, confirm: str = "", caches: bool = False, orphans: bool = False, shared_cache: bool = False) -> dict:
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

        _verify_no_dashboard_update(root)
        report = plan(root, caches=caches, orphans=orphans, shared_cache=shared_cache)
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
            # Explicit orphan-only/file cleanup can run without a database.
            _check_anchors(root)
            for filename in report["delete_paths"]:
                path = Path(filename)
                if path.is_symlink():
                    raise CleanupError("Symlink appeared during cleanup")
                if path.is_dir():
                    shutil.rmtree(path)
                elif path.is_file():
                    path.unlink()
        report["applied"] = True
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run legacy PegineLab job cleanup")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--include-orphans", action="store_true",
                        help="also inspect old 32-hex UUID files with no SQLite record")
    parser.add_argument("--prune-old-shared-cache", action="store_true",
                        help="also remove old global build/cache and build/tmp, not new project caches")
    parser.add_argument("--prune-old-git-cache", action="store_true",
                        help="also remove only old bare caches from build/git-cache")
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        print("Refusing root: use the regular YadroKreator service user", file=sys.stderr)
        return 2
    root = Path(os.environ.get("PEGINELAB_HOME", "/1tbdisk/PegineLab"))
    try:
        result = run(root, apply=args.apply, confirm=args.confirm,
                     caches=args.prune_old_git_cache,
                     orphans=args.include_orphans,
                     shared_cache=args.prune_old_shared_cache)
        print(("DELETED" if args.apply else "DRY RUN — nothing removed"))
        print("Old DB jobs:", len(result["finished_legacy_job_ids"]))
        print("Orphan legacy IDs:", len(result["orphan_legacy_job_ids"]))
        for path in result["delete_paths"]:
            print("  ", path)
        print("Source trees in projects/, new build/projects/, and Thingino baseline: NEVER targeted")
        return 0
    except (CleanupError, OSError, sqlite3.Error) as exc:
        print("CLEANUP REFUSED:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
