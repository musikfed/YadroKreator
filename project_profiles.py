"""Explicit project registry: no implicit sharing of source trees or artifacts."""
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
# Irila's real IMG pipeline uses sudo/loop/mkfs and Canonical-signed kernel.
# Do not execute it as an unattended unprivileged dashboard worker.
IRILA_IMAGE_WORKFLOW = "https://github.com/musikfed/Irila_baikal_v1.0/actions/workflows/build-installed-full-secureboot-img.yml"


def profile_workspace(job_id: str, profile: str, *, root: Path) -> Path:
    if profile not in PROFILES:
        raise ValueError("Unsupported build profile")
    from git_sources import JOB_ID
    if not isinstance(job_id, str) or not JOB_ID.fullmatch(job_id):
        raise ValueError("Invalid build job id")
    return root / "build" / "jobs" / job_id / PROFILES[profile]["source_dir"]
