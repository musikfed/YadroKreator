#!/usr/bin/env python3
"""Review old GitHub branches, delete only explicitly named fully merged branches.

Default: report only. Never delete main, active camera work branch,
release/0.1_test, unmerged commits, current/local branches or any worktree.
Deletion requires both --apply and a confirmation phrase, and uses a Git
remote-SHA lease to block races. Only acts in the SELECTED repository.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

# Work both as "python -m scripts.prune_merged_branches" and direct script invocation.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.sync_core_projects import REPOS, FACTORY_URL, check_root, inspect_checkout, invoke, SyncError

REPOSITORIES = {**REPOS, "YadroKreator": FACTORY_URL}
PROTECTED = {
    "YadroKreator": frozenset(("main",)),
    "wificam_T23N": frozenset(("main", "mymarrchWFcam", "release/0.1_test")),
    "wifcam_helper": frozenset(("main",)),
    "Irila_baikal_v1.0": frozenset(("main",)),
}
CONFIRM = "DELETE-MERGED-REMOTE-BRANCHES"
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class BranchError(SyncError):
    pass


def valid_branch(name: str) -> None:
    if not BRANCH.fullmatch(name) or name.startswith("origin/"):
        raise BranchError("Invalid branch name")
    result = subprocess.run(["git", "check-ref-format", "--branch", name], capture_output=True)
    if result.returncode:
        raise BranchError("Git rejected branch name")


def fetch_for_inspection(repo: Path) -> None:
    # Fetch into remote-tracking refs, never checkout, reset or modify local work.
    invoke("git", "-C", str(repo), "fetch", "--no-tags", "origin",
           "+refs/heads/*:refs/remotes/origin/*", capture=False, timeout=240)


def listed_branches(repo: Path) -> list[str]:
    raw = invoke("git", "-C", str(repo), "for-each-ref", "--format=%(refname:strip=3)",
                 "refs/remotes/origin")
    return [name for name in raw.splitlines() if name and name != "HEAD"]


def merged_into_main(repo: Path, name: str) -> bool:
    result = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                             f"refs/remotes/origin/{name}",
                             "refs/remotes/origin/main"], capture_output=True, text=True)
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise BranchError("Could not verify branch ancestry: " + result.stderr[-500:])


def review(root: Path, project: str) -> list[dict]:
    if project not in REPOSITORIES:
        raise BranchError("Unexpected project")
    root = check_root(root)
    repo = root / "projects" / project
    inspect_checkout(repo, REPOSITORIES[project])
    fetch_for_inspection(repo)
    local = invoke("git", "-C", str(repo), "for-each-ref", "--format=%(refname:short)",
                   "refs/heads").splitlines()
    current = invoke("git", "-C", str(repo), "symbolic-ref", "--short", "HEAD")
    out = []
    for name in listed_branches(repo):
        valid_branch(name)
        sha = invoke("git", "-C", str(repo), "rev-parse",
                     "--verify", f"refs/remotes/origin/{name}")
        if not SHA.fullmatch(sha):
            raise BranchError("Invalid fetched SHA")
        if name in PROTECTED[project]:
            status = "PROTECTED"
        elif name == current or name in local:
            status = "LOCAL BRANCH - no remote deletion"
        elif merged_into_main(repo, name):
            status = "MERGED - eligible by exact name only"
        else:
            status = "UNMERGED - preserve"
        out.append({"project": project, "branch": name, "sha": sha, "status": status})
    return out


def delete_named(root: Path, project: str, names: list[str], *, apply: bool, confirm: str = "") -> list[dict]:
    if not names:
        raise BranchError("Provide at least one exact --branch to delete")
    if len(set(names)) != len(names):
        raise BranchError("Duplicate target branch names")
    for name in names:
        valid_branch(name)
    rows = review(root, project)
    by_name = {row["branch"]: row for row in rows}
    selected = []
    for name in names:
        row = by_name.get(name)
        if row is None:
            raise BranchError(f"Branch {name!r} not found on remote")
        if row["status"] != "MERGED - eligible by exact name only":
            raise BranchError(f"{name}: refused ({row['status']})")
        selected.append(row)
    if not apply:
        return selected
    if confirm != CONFIRM:
        raise BranchError("Deletion needs --apply --confirm " + CONFIRM)
    repo = root / "projects" / project
    for row in selected:
        # Lease fails if someone updated GitHub branch since the report.
        invoke("git", "-C", str(repo), "push",
               f"--force-with-lease=refs/heads/{row['branch']}:{row['sha']}",
               "origin", f":refs/heads/{row['branch']}", capture=False)
    return selected


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Inspect or explicitly delete merged GitHub branches")
    p.add_argument("--project", choices=sorted(REPOSITORIES), required=True)
    p.add_argument("--branch", action="append", default=[], help="exact branch to delete (repeatable)")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--confirm", default="")
    args = p.parse_args(argv)
    if os.geteuid() == 0:
        print("Run as normal user; root not allowed", file=sys.stderr)
        return 2
    root = Path(os.environ.get("PEGINELAB_HOME", "/1tbdisk/PegineLab"))
    try:
        if args.branch:
            rows = delete_named(root, args.project, args.branch, apply=args.apply,
                                confirm=args.confirm)
            print("REMOTE DELETED" if args.apply else "DRY RUN: eligible targets only")
        else:
            if args.apply:
                raise BranchError("--apply requires exact --branch targets")
            rows = review(root, args.project)
            print("BRANCH AUDIT: no remote deletions")
        for row in rows:
            print(f"{row['branch']:<54} {row['sha'][:12]} {row['status']}")
        print("Protected branches, unmerged changes, local branches and commits are never auto-deleted.")
        return 0
    except (BranchError, SyncError, OSError, subprocess.TimeoutExpired) as exc:
        print("BRANCH CLEANUP REFUSED:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
