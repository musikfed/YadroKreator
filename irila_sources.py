"""Detached, SHA-pinned Irila Git snapshot. Never touch the user's local tree."""
from __future__ import annotations
import fcntl
import re
import subprocess
from pathlib import Path

from core import ROOT
from project_profiles import profile_workspace

ORIGIN = "https://github.com/musikfed/Irila_baikal_v1.0.git"
BRANCH = "main"
SHA = re.compile(r"[0-9a-f]{40}"+r"\Z")


def checkout_irila(job_id: str, log, *, root: Path = ROOT, on_process=None,
                   repo_url: str = ORIGIN) -> tuple[Path, str]:
    work = profile_workspace(job_id, "irila_preflight", root=root)
    if work.exists() or work.is_symlink():
        raise RuntimeError("Irila source workspace already exists")
    cache_dir = root / "build" / "git-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    work.parent.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / "Irila_baikal_v1.0.git"
    def git(*args, capture=False):
        cmd = ["git", *args]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE if capture else log,
                                stderr=log)
        if on_process:
            on_process(proc)
        try:
            if capture:
                output, _ = proc.communicate(timeout=90)
            else:
                output = b""
                proc.wait(timeout=90)
            if proc.returncode:
                raise RuntimeError("Git source operation failed")
            return output.decode().strip()
        finally:
            if on_process:
                on_process(None)
    with (cache_dir / "fetch.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not cache.exists():
            git("init", "--bare", str(cache))
            git("-C", str(cache), "remote", "add", "origin", repo_url)
        if git("-C", str(cache), "remote", "get-url", "origin", capture=True) != repo_url:
            raise RuntimeError("Irila cache remote mismatch")
        git("-C", str(cache), "fetch", "--no-tags", "--depth=1", "origin",
            "+refs/heads/main:refs/remotes/origin/main")
        sha = git("-C", str(cache), "rev-parse", "--verify",
                  "refs/remotes/origin/main^{commit}", capture=True)
        if not SHA.fullmatch(sha):
            raise RuntimeError("Unrecognized Irila source SHA")
        git("-C", str(cache), "worktree", "add", "--detach", str(work), sha)
    log.write(("Irila pinned source main@" + sha + "\n").encode())
    return work, sha
