"""Strict, opt-in helper -> factory build preset contract.

The helper cannot insert shell commands, kernel fragments, Git refs or arbitrary
Buildroot parameters. Factory pins an immutable JSON copy per job.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core import ROOT

SCHEMA = "peginelab.wifcam-helper.build-preset.v1"
CAMERA = "galayou_g2_t23n_sc2336_atbm6012bx"
BRANCH = "mymarrchWFcam"
ID_RE = re.compile(r"[0-9a-f]{32}\Z")


def helper_profile_source(root: Path = ROOT) -> Path:
    return root / "projects" / "wifcam_helper" / "profiles" / "t23n_lean.json"


def checked_profile(data: object, *, branch: str) -> dict:
    if not isinstance(data, dict) or set(data) != {
        "schema", "camera", "branch", "build_env",
        "requires_hardware_verification", "notes"
    }:
        raise ValueError("Unrecognized helper profile schema")
    if data["schema"] != SCHEMA or data["camera"] != CAMERA:
        raise ValueError("Wrong helper hardware profile")
    if data["branch"] != BRANCH or branch != BRANCH:
        raise ValueError("Helper profile is only defined for mymarrchWFcam")
    if data["requires_hardware_verification"] is not True:
        raise ValueError("Unsafe profile: cannot claim hardware verified")
    if not isinstance(data["notes"], str) or len(data["notes"]) > 600:
        raise ValueError("Invalid profile notes")
    env = data["build_env"]
    if not isinstance(env, dict) or set(env) != {"WIFICAM_WEBRTC"}:
        raise ValueError("Only WIFICAM_WEBRTC is an allowed build option")
    if env["WIFICAM_WEBRTC"] not in ("0", "1"):
        raise ValueError("WIFICAM_WEBRTC must be 0 or 1")
    return dict(data)


def load_helper_profile(*, root: Path = ROOT, branch: str = BRANCH) -> dict:
    path = helper_profile_source(root)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("Helper profile missing, linked or too large")
    return checked_profile(json.loads(path.read_text(encoding="utf-8")), branch=branch)


def job_profile_path(job_id: str, *, root: Path = ROOT) -> Path:
    if not ID_RE.fullmatch(job_id):
        raise ValueError("Invalid job ID")
    return root / "build" / "jobs" / job_id / "helper-preset.json"


def snapshot_profile(job_id: str, profile: dict, *, root: Path = ROOT) -> Path:
    checked_profile(profile, branch=BRANCH)
    path = job_profile_path(job_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    path.chmod(0o600)
    return path


def job_env(job_id: str, *, root: Path = ROOT, branch: str = BRANCH) -> dict[str, str]:
    path = job_profile_path(job_id, root=root)
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 8192:
        raise ValueError("Invalid job-pinned helper profile")
    data = checked_profile(json.loads(path.read_text(encoding="utf-8")), branch=branch)
    return data["build_env"].copy()
