#!/usr/bin/env python3
"""Run each source-pinned firmware build inside its own systemd user unit."""
from __future__ import annotations
import os
import fcntl
import signal
import subprocess
import sys
from pathlib import Path

from core import ROOT, PROJECT, THINGINO, LOGS, get_job, record_status, record_source_sha, now
from git_sources import checkout_source
from helper_profiles import job_env
from irila_sources import checkout_irila
from irila_preflight import audit as audit_irila
from project_profiles import project_build_root, project_log_path


def main(job_id: str) -> int:
    job = get_job(job_id)
    if not job or job["profile"] not in ("t23n_sd", "irila_preflight"):
        return 2
    log_path = project_log_path(job_id, job["profile"], root=ROOT, data=LOGS.parent)
    log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
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
    # Temporary files and compiler cache belong to the selected production.
    # Irila and WIFICAM never share temp, XDG cache, CCACHE or bare Git cache.
    build = project_build_root(job["profile"], root=ROOT)
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
    # Secondary lock: the SQLite transaction already allows one active job.
    # This also protects against a second worker accidentally started by systemd.
    lock_dir = ROOT / "build" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "factory-build.lock").open("a+b") as factory_lock:
      try:
        fcntl.flock(factory_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
      except BlockingIOError:
        record_status(job_id, "failed", details="Another factory worker owns the build lock")
        return 3
      with log_path.open("ab", buffering=0) as log:
        log.write(("\n=== PegineLab " + job["profile"] + " job " + now() + " ===\n").encode())
        try:
            record_status(job_id, "running")
            if job["profile"] == "irila_preflight":
                if job["repo_ref"] != "main":
                    raise RuntimeError("Irila accepts only the pinned main branch")
                source, sha = checkout_irila(job_id, log, on_process=current_process)
                record_source_sha(job_id, sha)
                if stopped:
                    raise RuntimeError("Irila checkout stopped")
                report = audit_irila(job_id, sha, root=ROOT)
                log.write((report["message"] + "\n").encode())
                log.write(b"No sudo, loop, mkfs, USB IMG or kernel build executed.\n")
                code = 0
            elif job["profile"] == "t23n_sd":
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
                extra = job_env(job_id, root=ROOT, branch=job["repo_ref"])
                if extra:
                    env.update(extra)
                    log.write(b"WifCam Helper preset WIFICAM_WEBRTC=" +
                              extra["WIFICAM_WEBRTC"].encode() + b".\n")
                proc = subprocess.Popen(
                    ["/bin/sh", "scripts/build_thingino_wificam_image.sh"],
                    cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT,
                )
                code = proc.wait()
                if code == 0:
                    # Fresh detached worktrees contain the Git-tracked 0.1_test
                    # baseline. A successful job MUST output its own raw SD
                    # candidate and checksum; never accept the old baseline.
                    candidates = (
                        source / "out/private-sd/thingino-t23-sd.bin",
                        source / "out/candidate-sd/thingino-t23-sd.bin",
                    )
                    if not any(path.is_file() and
                               path.with_name(path.name + ".sha256").is_file()
                               for path in candidates):
                        log.write(b"BUILD ERROR: no new per-job SD candidate and SHA256 sidecar.\n")
                        code = 1
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
