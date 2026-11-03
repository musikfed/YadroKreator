"""Strict project-separated sources, build outputs, caches, logs and reports.

Existing jobs in legacy directories require explicit opt-in cleanup; they are
never silently copied or merged into a new project build tree.
"""
from __future__ import annotations

import re
from pathlib import Path

PROFILES = {
    "t23n_sd": {
        "name": "WIFICAM T23N · SD",
        "repository": "https://github.com/musikfed/wificam_T23N.git",
        "source_dir": "wificam_T23N",
        "type": "sd_image",
        "build_enabled": True,
    },
    "irila_preflight": {
        "name": "Irila Baikal · проверка исходников",
        "repository": "https://github.com/musikfed/Irila_baikal_v1.0.git",
        "source_dir": "Irila_baikal_v1.0",
        "type": "source_audit",
        "build_enabled": True,
    },
}

IRILA_IMAGE_WORKFLOW = "https://github.com/musikfed/Irila_baikal_v1.0/actions/workflows/build-installed-full-secureboot-img.yml"
ID = re.compile(r"[0-9a-f]{32}\Z")


def _check(profile: str, job_id: str | None = None) -> str:
    if profile not in PROFILES:
        raise ValueError("Unsupported build profile")
    if job_id is not None and (not isinstance(job_id, str) or not ID.fullmatch(job_id)):
        raise ValueError("Invalid build job id")
    return PROFILES[profile]["source_dir"]


def project_build_root(profile: str, *, root: Path) -> Path:
    """Root for ONE production line; no firmware or cache from other lines."""
    name = _check(profile)
    return root / "build" / "projects" / name


def job_root(job_id: str, profile: str, *, root: Path) -> Path:
    """Exact per-project build tree; never fall back to a foreign/legacy job."""
    _check(profile, job_id)
    return project_build_root(profile, root=root) / "jobs" / job_id


def profile_workspace(job_id: str, profile: str, *, root: Path) -> Path:
    name = _check(profile, job_id)
    return job_root(job_id, profile, root=root) / name


def project_cache_root(profile: str, *, root: Path) -> Path:
    return project_build_root(profile, root=root) / "git-cache"


def project_log_path(job_id: str, profile: str, *, root: Path, data: Path) -> Path:
    """Project-scoped logs under factory-state; same scheduler, separate files."""
    name = _check(profile, job_id)
    return data / "projects" / name / "logs" / (job_id + ".log")
