#!/usr/bin/env python3
"""Run each source-pinned firmware build inside its own systemd user unit."""
from __future__ import annotations
import os
import signal
import subprocess
import sys
from pathlib import Path

from core import ROOT, PROJECT, THINGINO, LOGS, get_job, record_status, record_source_sha, now
from git_sources import checkout_source
from helper_profiles import job_env


def main(job_id: str) -> int:
    job = get_job(job_id)
    if not job or job["profile"] != "t23n_sd":
        return 2
    log_path = LOGS / (job_id + ".log")
    stopped = False
    proc = None

    def current_process(child):
        nonlocal proc
        proc = child

    def terminate(_sig, _frame):
        nonlocal stopped
        stopped = True
        if proc is not None and proc.poll() is None:
            proc.terminate()

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)

    env = os.environ.copy()
    build = ROOT / "build"
    for directory in (build / "tmp", build / "cache", build / "cache" / "ccache"):
        directory.mkdir(parents=True, exist_ok=True)
    # Buildroot rejects an inherited LD_LIBRARY_PATH with an empty/current-dir
    # element. Do not pass host loader paths to cross-compilation at all.
    # Preserve the system/user environment; sanitize this worker's child only.
    env.pop("LD_LIBRARY_PATH", None)
    env.update({
        "TMPDIR": str(build / "tmp"),
        "XDG_CACHE_HOME": str(build / "cache"),
        "CCACHE_DIR": str(build / "cache" / "ccache"),
        "THINGINO_DIR": str(THINGINO),
        "THINGINO_FAST": "0",
        "PUBLISH": "0",
    })
    code = 1
    with log_path.open("ab", buffering=0) as log:
        log.write(("\n=== PegineLab T23N build " + now() + " ===\n").encode())
        try:
            record_status(job_id, "running")
            if not (THINGINO / ".git").is_dir():
                raise RuntimeError("Thingino checkout not found on ext4")
            source, sha = checkout_source(job["repo_ref"], job_id, log, on_process=current_process)
            record_source_sha(job_id, sha)
            if stopped:
                raise RuntimeError("Build stopped during source fetch")
            if not (source / "scripts/build_thingino_wificam_image.sh").is_file():
                raise RuntimeError("WIFICAM build script missing in pinned Git revision")
            log.write(f"WIFICAM source = {job['repo_ref']} @ {sha}\n".encode())
            log.write(b"PUBLISH=0: candidate stays local; no Git push or SD flashing.\n")
            # Profile is snapshotted at job creation; never use a mutable live
            # helper report during hours of compilation.
            extra = job_env(job_id, root=ROOT, branch=job["repo_ref"])
            if extra:
                env.update(extra)
                log.write(b"WifCam Helper approved preset: WIFICAM_WEBRTC=" +
                          extra["WIFICAM_WEBRTC"].encode() + b" (not hardware verified).\n")
            proc = subprocess.Popen(
                ["/bin/sh", "scripts/build_thingino_wificam_image.sh"],
                cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            code = proc.wait()
        except Exception as exc:
            log.write(("BUILD ERROR: " + str(exc) + "\n").encode())
        status = "stopped" if stopped else ("success" if code == 0 else "failed")
        log.write(f"=== BUILD_EXIT={code} STATUS={status} ===\n".encode())
    record_status(job_id, status, exit_code=code)
    return 143 if stopped else code


if __name__ == "__main__":
    if len(sys.argv) != 2 or len(sys.argv[1]) != 32:
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
