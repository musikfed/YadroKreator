"""Unprivileged Irila source audit; NOT an image builder, kernel compiler or flasher."""
from __future__ import annotations
import json
import os
import platform
from pathlib import Path

from core import ROOT
from project_profiles import profile_workspace

REQUIRED = (
    "scripts/prepare_source.sh",
    "scripts/prepare_source_installed.sh",
    "scripts/bake_image_secureboot.sh",
    "scripts/bake_image_installed_secureboot.sh",
    ".github/workflows/build-readonly-img.yml",
    ".github/workflows/build-installed-full-secureboot-img.yml",
    "hardware/acer_swift3_sf314-41.json",
)
def audit(job_id: str, sha: str, *, root: Path = ROOT) -> dict:
    src = profile_workspace(job_id, "irila_preflight", root=root)
    if not src.is_dir() or src.is_symlink():
        raise ValueError("Missing pinned Irila source checkout")
    present = {name: (src / name).is_file() and not (src / name).is_symlink()
               for name in REQUIRED}
    report = {
        "profile": "irila_preflight",
        "source_sha": sha,
        "host_architecture": platform.machine(),
        "source_files": present,
        "ready_for_manual_ci": all(present.values()),
        "linux_kernel_build_started": False,
        "usb_image_built": False,
        "hardware_boot_verified": False,
        "message": "Source audit only: real IMG builder needs explicit privileged loop/mkfs; "
                   "the approved GitHub Actions workflow builds signed Ubuntu images.",
    }
    out = root / "build" / "jobs" / job_id / "irila-source-audit.json"
    with out.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    out.chmod(0o600)
    if not report["ready_for_manual_ci"]:
        raise ValueError("Missing required Irila build sources; see irila-source-audit.json")
    return report
