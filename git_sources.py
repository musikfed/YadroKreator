"""Git-backed, immutable WIFICAM source snapshot for each factory build.

No user-supplied clone URLs or arbitrary shell. Git is invoked with argv only.
The reference bare repo is a cache; a separate detached worktree is created
for each job, so updating a ref cannot switch a running compilation.
"""
from __future__ import annotations

import fcntl
import os
import re
import shutil
import subprocess
from pathlib import Path

from core import ROOT, PROJECT

REPO_URL = "https://github.com/musikfed/wificam_T23N.git"
BRANCHES = ("mymarrchWFcam", "main")
JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def validate_branch(value: object) -> str:
    if not isinstance(value, str) or value not in BRANCHES:
        raise ValueError("Unsupported WIFICAM Git branch")
    return value


def workspace_for(job_id: str, root: Path = ROOT) -> Path:
    if not JOB_ID.fullmatch(job_id):
        raise ValueError("Invalid job ID")
    return root / "build" / "jobs" / job_id / "wificam_T23N"


def checkout_source(branch: str, job_id: str, log, *,
                    root: Path = ROOT, project: Path = PROJECT,
                    repo_url: str = REPO_URL, on_process=None) -> tuple[Path, str]:
    """Fetch allowed Git branch and pin a detached, isolated checkout to SHA.

    repo_url/root/project overrides exist only for offline tests. Never pass
    client input into those arguments from the API.
    """
    validate_branch(branch)
    work = workspace_for(job_id, root)
    cache_dir = root / "build" / "git-cache"
    cache = cache_dir / "wificam_T23N.git"
    cache_dir.mkdir(parents=True, exist_ok=True)
    work.parent.mkdir(parents=True, exist_ok=True)
    if work.exists() or work.is_symlink():
        raise RuntimeError("Build workspace already exists; refusing overwrite")

    def git(*args: str, capture: bool = False) -> str:
        cmd = ["git", *args]
        if capture:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                                    stderr=log, text=True, timeout=30)
            return result.stdout.strip()
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        if on_process:
            on_process(proc)
        try:
            if proc.wait() != 0:
                raise RuntimeError("Git command failed: " + " ".join(args[:3]))
        finally:
            if on_process:
                on_process(None)
        return ""

    lock_path = cache_dir / "fetch.lock"
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not cache.exists():
            git("init", "--bare", str(cache))
            git("-C", str(cache), "remote", "add", "origin", repo_url)
        origin = git("-C", str(cache), "remote", "get-url", "origin", capture=True)
        if origin != repo_url:
            raise RuntimeError("Unexpected cache remote; refusing to fetch")
        # The GitHub branch is selected by a finite allowlist, not arbitrary ref.
        refspec = f"+refs/heads/{branch}:refs/remotes/origin/{branch}"
        git("-C", str(cache), "fetch", "--no-tags", "--depth=1", "origin", refspec)
        sha = git("-C", str(cache), "rev-parse", "--verify",
                  f"refs/remotes/origin/{branch}^{{commit}}", capture=True)
        if not SHA.fullmatch(sha):
            raise RuntimeError("Invalid SHA from Git")
        log.write(f"Source pinned: {repo_url} {branch} @ {sha}\n".encode())
        # Detached worktree is pinned to the fetched SHA, not a mutable branch.
        git("-C", str(cache), "worktree", "add", "--detach", str(work), sha)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    # Preserve local Wi-Fi provisioning without ever committing or logging it.
    # Existing project checkout is read-only: no git pull/reset/clean on it.
    secret = project / "local" / "wifi.env"
    if secret.is_symlink():
        raise RuntimeError("Refusing symlinked local/wifi.env")
    if secret.is_file():
        dest = work / "local" / "wifi.env"
        dest.parent.mkdir(parents=True, exist_ok=True)
        with secret.open("rb") as src, dest.open("xb") as dst:
            shutil.copyfileobj(src, dst)
        os.chmod(dest, 0o600)
        log.write(b"Private Wi-Fi configuration loaded locally (contents hidden).\n")
    return work, sha
