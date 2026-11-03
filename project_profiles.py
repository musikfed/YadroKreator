"""Project-specific factory trees; legacy jobs stay readable, never relocated.

SQLite remains the shared scheduler. Every new job has a project-scoped source,
cache, temporary files, report and log directory. No cross-project fallbacks.
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
    """New layout; old job workspaces continue to resolve without migration.

    An existing legacy job is identified by its old UUID directory. Never
    move, merge or overwrite an old tree as part of a dashboard update.
    """
    _check(profile, job_id)
    legacy = root / "build" / "jobs" / job_id
    if legacy.exists() or legacy.is_symlink():
        return legacy
    return project_build_root(profile, root=root) / "jobs" / job_id


def profile_workspace(job_id: str, profile: str, *, root: Path) -> Path:
    name = _check(profile, job_id)
    return job_root(job_id, profile, root=root) / name


def project_cache_root(profile: str, *, root: Path) -> Path:
    return project_build_root(profile, root=root) / "git-cache"


def project_log_path(job_id: str, profile: str, *, root: Path, data: Path) -> Path:
    name = _check(profile, job_id)
    legacy = data / "logs" / (job_id + ".log")
    if legacy.is_file() and not legacy.is_symlink():
        return legacy
    return data / "projects" / name / "logs" / (job_id + ".log")
