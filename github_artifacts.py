"""Scoped GitHub Actions orchestration using pre-authorized gh CLI on CORE.

No tokens in browser/config, no arbitrary repo/workflow or shell command.
Functions return explicit errors when gh is unavailable: never fake success.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
from typing import Any

REPOS = {
    "builds": "musikfed/wificam_T23N",
    "irila": "musikfed/Irila_baikal_v1.0",
}
WORKFLOWS = {
    "irila": ("build-installed-full-secureboot-img.yml", "main"),
}
ARTIFACT_ID=re.compile(r"[1-9][0-9]{0,18}\Z")


def gh(args: list[str], timeout: int=18) -> str:
    env=dict(os.environ, GH_PROMPT_DISABLED="1", GIT_TERMINAL_PROMPT="0",
             GH_NO_UPDATE_NOTIFIER="1")
    try:
        result=subprocess.run(["gh", *args],text=True,capture_output=True,
                              timeout=timeout,check=False,env=env)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("gh CLI is unavailable, not authenticated, or timed out") from exc
    if result.returncode!=0:
        # Do not echo sensitive auth output or environment into the web response.
        raise ValueError("GitHub CLI request failed. Check gh auth status and Actions permissions on CORE.")
    return result.stdout


def list_artifacts(project: str) -> list[dict[str, Any]]:
    repo=REPOS.get(project)
    if not repo:
        raise ValueError("Unapproved GitHub project")
    raw=gh(["api",f"repos/{repo}/actions/artifacts?per_page=60",
            "--jq",".artifacts"])
    items=json.loads(raw)
    if not isinstance(items,list):
        raise ValueError("Unexpected GitHub artifact response")
    result=[]
    for a in items:
        if not isinstance(a,dict):
            continue
        aid=a.get("id")
        if not isinstance(aid,int) or not ARTIFACT_ID.fullmatch(str(aid)):
            continue
        run=a.get("workflow_run") or {}
        run_id=run.get("id")
        result.append({
            "id":aid,
            "name":str(a.get("name") or "")[:160],
            "bytes":int(a.get("size_in_bytes") or 0),
            "expired":bool(a.get("expired")),
            "created_at":a.get("created_at"),
            "updated_at":a.get("updated_at"),
            "sha":str(run.get("head_sha") or "")[:40],
            "run_id":run_id if isinstance(run_id,int) else None,
            "url":f"https://github.com/{repo}/actions/runs/{run_id}" if isinstance(run_id,int)
                 else f"https://github.com/{repo}/actions",
        })
    return result


def delete_artifact(project: str, artifact_id: str) -> None:
    repo=REPOS.get(project)
    if not repo or not ARTIFACT_ID.fullmatch(str(artifact_id)):
        raise ValueError("Invalid GitHub artifact identity")
    if os.environ.get("PEGINELAB_GITHUB_ARTIFACT_DELETE","")!="1":
        raise ValueError("GitHub deletion disabled: opt in using PEGINELAB_GITHUB_ARTIFACT_DELETE=1")
    # Confirm that the artifact belongs to the EXACT allowlisted repository,
    # not an artifact ID from another project, before deleting it.
    valid_ids={str(a["id"]) for a in list_artifacts(project)}
    if str(artifact_id) not in valid_ids:
        raise ValueError("Artifact does not belong to the selected GitHub project")
    gh(["api","-X","DELETE",f"repos/{repo}/actions/artifacts/{artifact_id}"])


def dispatch_irila() -> None:
    workflow,branch=WORKFLOWS["irila"]
    gh(["workflow","run",workflow,"--repo",REPOS["irila"],"--ref",branch,
        "-f","profile=full","-f","max_mib=12288"])
