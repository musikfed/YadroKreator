"""Manually refresh the two approved camera firmware Git caches without compiling.

Use the same per-profile locks/refs as the immutable checkout performed by
worker.py. Existing detached worktrees, job pins, and ready images stay intact.
"""
from __future__ import annotations

import fcntl
import re
import subprocess
from pathlib import Path

from core import ROOT
from git_sources import REPO_URL, validate_branch
from helper_firmware import BASE_BRANCH, ORIGIN
from project_profiles import project_cache_root

SHA = re.compile(r"[0-9a-f]{40}\Z")


def specifications(profile: str, branch: str | None = None, *, root: Path = ROOT):
    if profile == "t23n_sd":
        ref = validate_branch(branch or BASE_BRANCH, root=root)
        return [("WIFICAM", REPO_URL, ref, "wificam_T23N.git")]
    if profile == "t23n_helper_sd":
        if branch not in (None, "", "main"):
            raise ValueError("Helper uses main and the fixed WIFICAM base branch")
        return [
            ("Helper", ORIGIN, "main", "wifcam_helper.git"),
            ("WIFICAM base", REPO_URL, BASE_BRANCH, "wificam_T23N.git"),
        ]
    raise ValueError("Unsupported firmware source profile")


def _git(*args: str, timeout: int = 45) -> str:
    result = subprocess.run(["git", *args], check=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout)
    return result.stdout.strip()


def _cached_sha(cache: Path, branch: str) -> str | None:
    if cache.is_symlink() or not cache.is_dir():
        return None
    try:
        sha = _git("-C", str(cache), "rev-parse", "--verify",
                   f"refs/remotes/origin/{branch}^{{commit}}", timeout=10)
        return sha if SHA.fullmatch(sha) else None
    except (OSError, subprocess.SubprocessError):
        return None


def get_source_status(profile: str, branch: str | None = None, *, root: Path = ROOT) -> dict:
    specs = specifications(profile, branch, root=root)
    cache_root = project_cache_root(profile, root=root)
    return {
        "profile": profile,
        "sources": [
            {"name": name, "repository": origin.removesuffix(".git"),
             "branch": ref, "sha": _cached_sha(cache_root / filename, ref)}
            for name, origin, ref, filename in specs
        ],
        "note": "Локальный Git-кэш. Для проверки актуальной версии нажми «Обновить исходники из GitHub».",
    }


def refresh_sources(profile: str, branch: str | None = None, *, root: Path = ROOT) -> dict:
    specs = specifications(profile, branch, root=root)
    cache_root = project_cache_root(profile, root=root)
    cache_root.mkdir(parents=True, exist_ok=True)
    updated = []
    # Every fetch takes the same lock used by immutable build checkouts.
    with (cache_root / "fetch.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        for name, origin, ref, filename in specs:
            cache = cache_root / filename
            if cache.is_symlink():
                raise ValueError("Unsafe Git cache symlink")
            if not cache.exists():
                _git("init", "--bare", str(cache))
                _git("-C", str(cache), "remote", "add", "origin", origin)
            if not cache.is_dir():
                raise ValueError("Unsafe Git cache path")
            actual = _git("-C", str(cache), "remote", "get-url", "origin")
            if actual != origin:
                raise ValueError("Git cache origin mismatch: " + name)
            refspec = f"+refs/heads/{ref}:refs/remotes/origin/{ref}"
            _git("-C", str(cache), "fetch", "--no-tags", "--depth=1",
                 "origin", refspec, timeout=90)
            sha = _cached_sha(cache, ref)
            if sha is None:
                raise RuntimeError("Could not verify fetched SHA: " + name)
            updated.append({"name": name, "repository": origin.removesuffix(".git"),
                            "branch": ref, "sha": sha})
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return {"profile": profile, "sources": updated,
            "note": "Git fetch выполнен. Компиляция, прошивка SD и перезапуск служб не запускались."}
