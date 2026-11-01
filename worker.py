#!/usr/bin/env python3
"""One systemd transient service per job; survives browser and SSH disconnects."""
from __future__ import annotations
import os
import signal
import subprocess
import sys
from pathlib import Path
from core import ROOT, PROJECT, THINGINO, LOGS, get_job, record_status, now

def main(job_id: str) -> int:
    job = get_job(job_id)
    if not job or job["profile"] != "t23n_sd":
        return 2
    log_path = LOGS / (job_id + ".log")
    stopped = False
    proc = None

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
            if not (PROJECT / "scripts/build_thingino_wificam_image.sh").is_file():
                raise RuntimeError("WIFICAM build script not found")
            if not (THINGINO / ".git").is_dir():
                raise RuntimeError("Thingino checkout not found on ext4")
            proc = subprocess.Popen(
                ["/bin/sh", "scripts/build_thingino_wificam_image.sh"],
                cwd=PROJECT, env=env, stdout=log, stderr=subprocess.STDOUT
            )
            code = proc.wait()
        except Exception as exc:
            log.write(("BUILD ERROR: " + str(exc) + "\n").encode())
        if stopped:
            status = "stopped"
        else:
            status = "success" if code == 0 else "failed"
        log.write((f"=== BUILD_EXIT={code} STATUS={status} ===\n").encode())
    record_status(job_id, status, exit_code=code)
    return code if not stopped else 143

if __name__ == "__main__":
    if len(sys.argv) != 2 or len(sys.argv[1]) != 32:
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
