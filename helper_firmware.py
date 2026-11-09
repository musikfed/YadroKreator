"""Distinct, SHA-pinned camera-head firmware source + allowlisted rootfs overlay.

Camera-side shell/CGI files are sourced from musikfed/wifcam_helper/main;
the heavyweight Python/LLM test bench is never put into the 64 MB rootfs.
The approved WIFICAM base is checked out separately by git_sources.py.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from core import ROOT
from project_profiles import job_root, project_cache_root
from helper_audio import read_score, render_score

ORIGIN = "https://github.com/musikfed/wifcam_helper.git"
BRANCH = "main"
BASE_BRANCH = "mymarrchWFcam"
PROFILE = "t23n_helper_sd"
SHA = re.compile(r"[0-9a-f]{40}\Z")
APPROVED = {
    "etc/wifcam-helper-release": 0o644,
    "etc/init.d/S92wifcam-helper": 0o755,
    "usr/bin/wifcam-helper-probe": 0o755,
    "usr/bin/wifcam-helper-mode": 0o755,
    "usr/share/wificam-web/cgi-bin/helper-capabilities": 0o755,
}
# Dedicated Helper edition UI: preserve the complete camera dashboard and all
# existing PTZ/Wi-Fi/storage/security pages; source of truth belongs to Helper.
APPROVED_UI = {
    "index.html": 50000,
    "styles.css": 35000,
    "app.js": 70000,
    "assets/peginelab-logo.svg": 35000,
}
SCORE_PATH = "firmware/audio/boot-jingle.json"
MARKER = b"PEGINELAB_HELPER_FIRMWARE_V1"

def checkout_helper(job_id: str, log, *, root: Path = ROOT,
                    repo_url: str = ORIGIN, on_process=None) -> tuple[Path,str]:
    """Fixed repository/ref, isolated shallow detached worktree; tests may inject a local Git source."""
    work = job_root(job_id, PROFILE, root=root) / "wifcam_helper"
    cache_dir = project_cache_root(PROFILE, root=root)
    cache = cache_dir / "wifcam_helper.git"
    if work.exists() or work.is_symlink():
        raise RuntimeError("Helper worktree already exists; refusing overwrite")
    work.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    def git(*args, capture=False):
        process = subprocess.Popen(["git", *args], stdout=subprocess.PIPE if capture else log,
                                   stderr=log)
        if on_process:
            on_process(process)
        try:
            if capture:
                output,_ = process.communicate(timeout=90)
            else:
                output=b""
                process.wait(timeout=90)
            if process.returncode:
                raise RuntimeError("Helper Git fetch/checkout failed")
            return output.decode("utf-8",errors="strict").strip()
        finally:
            if on_process:
                on_process(None)

    with (cache_dir / "fetch.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        if not cache.exists():
            git("init","--bare",str(cache))
            git("-C",str(cache),"remote","add","origin",repo_url)
        if git("-C",str(cache),"remote","get-url","origin",capture=True) != repo_url:
            raise RuntimeError("Helper Git cache origin mismatch")
        git("-C",str(cache),"fetch","--no-tags","--depth=1","origin",
            "+refs/heads/main:refs/remotes/origin/main")
        sha=git("-C",str(cache),"rev-parse","--verify",
                "refs/remotes/origin/main^{commit}",capture=True)
        if not SHA.fullmatch(sha):
            raise RuntimeError("Invalid Helper Git SHA")
        git("-C",str(cache),"worktree","add","--detach",str(work),sha)
    log.write(("Helper pinned main@" + sha + "\n").encode())
    return work,sha


def stage_helper_overlay(helper: Path, camera: Path, job_id: str,
                         helper_sha: str, base_sha: str, *, root: Path=ROOT) -> Path:
    """Copy only known fixed files into disposable WIFICAM worktree. No scripts run."""
    if not SHA.fullmatch(helper_sha) or not SHA.fullmatch(base_sha):
        raise ValueError("Unpinned source SHA")
    base_job=job_root(job_id,PROFILE,root=root)
    if (not helper.resolve().is_relative_to(base_job.resolve()) or
            not camera.resolve().is_relative_to(base_job.resolve())):
        raise ValueError("Cross-project firmware overlay refused")
    overlay=helper/"firmware"/"overlay"
    if overlay.is_symlink() or not overlay.is_dir():
        raise FileNotFoundError("Helper firmware/overlay missing from pinned Git")
    actual=set()
    for path in overlay.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Unsupported Helper overlay file type")
        if path.is_file():
            actual.add(path.relative_to(overlay).as_posix())
    if actual != set(APPROVED):
        raise ValueError("Unexpected/missing Helper firmware overlay paths")
    # Validate every UI and sound input *before* changing the isolated camera tree.
    ui_root = helper / "firmware/ui"
    if ui_root.is_symlink() or not ui_root.is_dir():
        raise ValueError("Helper edition UI source missing")
    actual_ui = set()
    for file in ui_root.rglob("*"):
        if file.is_symlink() or not (file.is_file() or file.is_dir()):
            raise ValueError("Unsafe Helper UI asset type")
        if file.is_file():
            actual_ui.add(file.relative_to(ui_root).as_posix())
    if actual_ui != set(APPROVED_UI):
        raise ValueError("Unexpected or incomplete Helper UI files")
    for relative, limit in APPROVED_UI.items():
        file = ui_root / relative
        if not file.is_file() or file.stat().st_size == 0 or file.stat().st_size > limit:
            raise ValueError("Missing, empty or oversized Helper UI asset")
    if b"PegineLab WIFICAM T23N" not in (ui_root / "index.html").read_bytes():
        raise ValueError("Helper UI must retain the native WIFICAM safety identity")
    if b"helper-capabilities" not in (ui_root / "app.js").read_bytes():
        raise ValueError("Helper UI must retain authenticated camera head controls")
    score = read_score(helper / SCORE_PATH)
    for relative in APPROVED:
        target = camera / "rootfs" / relative
        if target.exists() or target.is_symlink():
            raise RuntimeError("Helper overlay would overwrite WIFICAM base file")
        if any(parent.is_symlink() for parent in (target.parent, *target.parents)):
            raise ValueError("Symlink in target rootfs path")
    for relative in APPROVED_UI:
        target = camera / "web" / relative
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError("Unexpected Helper UI target")
        if any(parent.is_symlink() for parent in (target.parent, *target.parents)):
            raise ValueError("Symlink in target UI path")
    audio_path = camera / "web/assets"
    if any(parent.is_symlink() for parent in (audio_path, *audio_path.parents)):
        raise ValueError("Symlink in Helper sound target path")
    for filename in ("boot-jingle.wav", "boot-jingle.s16le"):
        target = audio_path / filename
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError("Unsafe existing Helper sound target")
    for relative, mode in APPROVED.items():
        source=overlay/relative
        target=camera/"rootfs"/relative
        if not source.is_file() or source.is_symlink() or source.stat().st_size>8192:
            raise ValueError("Unsafe or oversized Helper firmware file")
        if target.exists() or target.is_symlink():
            raise RuntimeError("Helper overlay would overwrite WIFICAM base file")
        if any(parent.is_symlink() for parent in (target.parent,*target.parents)):
            raise ValueError("Symlink in target rootfs path")
        target.parent.mkdir(parents=True,exist_ok=True)
        with source.open("rb") as infile,target.open("xb") as outfile:
            shutil.copyfileobj(infile,outfile)
        target.chmod(mode)
    if (camera/"rootfs/etc/wifcam-helper-release").read_bytes().find(MARKER)<0:
        raise ValueError("Helper firmware identity marker missing")
    # Copy the *Helper-owned* frontend over the base checkout only inside this
    # job. WIFICAM's separate firmware remains untouched on disk and in Git.
    for relative in APPROVED_UI:
        source = ui_root / relative
        target = camera / "web" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)
    wav, pcm = render_score(score, audio_path)
    digests = {}
    for relative in APPROVED_UI:
        digests["ui/" + relative] = hashlib.sha256((ui_root / relative).read_bytes()).hexdigest()
    digests["audio/boot-jingle.json"] = hashlib.sha256((helper / SCORE_PATH).read_bytes()).hexdigest()
    digests["audio/boot-jingle.wav"] = hashlib.sha256(wav.read_bytes()).hexdigest()
    digests["audio/boot-jingle.s16le"] = hashlib.sha256(pcm.read_bytes()).hexdigest()
    record=base_job/"source-pins.json"
    record.write_text(json.dumps({
        "schema":"peginelab.helper-firmware-pins.v1",
        "helper_repo":"musikfed/wifcam_helper","helper_sha":helper_sha,
        "base_repo":"musikfed/wificam_T23N","base_sha":base_sha,
        "base_branch":BASE_BRANCH,"overlay_files":sorted(APPROVED),
        "ui_files":sorted(APPROVED_UI),"media_sha256":digests,
    },sort_keys=True)+"\n",encoding="utf-8")
    record.chmod(0o600)
    return record
