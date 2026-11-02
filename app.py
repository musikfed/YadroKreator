"""PegineLab Factory API. Native VPN/LAN build dashboard."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from core import ROOT, DATA, LOGS, PROJECT, THINGINO, ACTIVE, connect, get_job, now, record_status
from git_sources import BRANCHES, workspace_for, validate_branch

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=4096, JSON_AS_ASCII=False)
JOB_ID = re.compile(r"^[0-9a-f]{32}$")

@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
    return response

@app.before_request
def gate():
    # Mutation requests require a custom header to block browser CSRF.
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if request.headers.get("X-PegineLab-Action") != "1":
            return jsonify(error="Request header required"), 403

@app.get("/")
def index():
    return render_template("index.html")

def unit_active(unit: str) -> bool:
    try:
        result = subprocess.run(["systemctl", "--user", "is-active", unit],
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip() in ("active", "activating", "reloading", "deactivating")
    except (OSError, subprocess.TimeoutExpired):
        # Unknown is NOT proof of termination; keep persisted state.
        return True

def reconcile():
    db = connect()
    try:
        active = [dict(r) for r in db.execute(
            "SELECT id,unit,status,created_at,started_at FROM jobs WHERE status IN ('queued','running','stopping')")]
    finally:
        db.close()
    for j in active:
        # Allow transient systemd-run startup race; do not overwrite a new job.
        entered = j["started_at"] or j["created_at"]
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(entered)).total_seconds()
        if age > 20 and not unit_active(j["unit"]):
            record_status(j["id"], "stopped" if j["status"] == "stopping" else "interrupted",
                          details="Unit ended before final status was recorded")

def safe_job(job_id: str):
    if not JOB_ID.fullmatch(job_id):
        return None
    return get_job(job_id)

@app.get("/api/overview")
def overview():
    reconcile()
    db = connect()
    try:
        jobs = [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 40")]
    finally:
        db.close()
    for j in jobs:
        j.pop("log_path", None)
    meminfo = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, v = line.partition(":")
            if k in ("MemTotal", "MemAvailable"):
                meminfo[k] = int(v.strip().split()[0]) * 1024
    except OSError:
        pass
    disk = shutil.disk_usage(ROOT)
    images = []
    for label, path in (
        ("Новый SD-кандидат (не проверен на камере)", PROJECT / "out/candidate-sd/thingino-t23-sd.bin"),
        ("Персональный SD-кандидат (не проверен)", PROJECT / "out/private-sd/thingino-t23-sd.bin"),
        ("Эталон 0.1_test (проверен SD boot, UI с ошибками)", PROJECT / "Thingino/thingino-t23-sd.bin"),
    ):
        if path.is_file():
            checksum = path.with_name(path.name + ".sha256")
            sha = ""
            if checksum.is_file():
                candidate = checksum.read_text(errors="replace").split()
                if candidate and re.fullmatch("[0-9a-fA-F]{64}", candidate[0]):
                    sha = candidate[0]
            images.append(dict(label=label, name=path.name, bytes=path.stat().st_size,
                               sha256=sha, location=str(path)))
    # Each detached Git worktree has its own candidate image, tagged by the
    # exact source commit. Do not confuse these with the 0.1_test baseline.
    for job in jobs:
        # A Git worktree may already contain an old tracked SD image before
        # a new build starts. Never label it as a build result on failure,
        # cancellation, or while the compiler is still running.
        if job["status"] != "success" or not job["source_sha"]:
            continue
        source = workspace_for(job["id"])
        for candidate in (
            source / "out/private-sd/thingino-t23-sd.bin",
            source / "out/candidate-sd/thingino-t23-sd.bin",
            source / "Thingino/thingino-t23-sd.bin",
        ):
            if not candidate.is_file():
                continue
            checksum = candidate.with_name(candidate.name + ".sha256")
            digest = ""
            if checksum.is_file():
                token = checksum.read_text(errors="replace").split()
                if token and re.fullmatch("[0-9a-fA-F]{64}", token[0]):
                    digest = token[0]
            images.append(dict(
                label="Git-сборка " + job["repo_ref"] + "@" + (job["source_sha"][:12] or "?") +
                      " — НЕ проверена на камере",
                name=candidate.name, bytes=candidate.stat().st_size,
                sha256=digest, location=str(candidate), job_id=job["id"],
            ))
            break
    return jsonify(
        jobs=jobs, images=images, allowed_branches=list(BRANCHES),
        metrics=dict(load_1=round(os.getloadavg()[0], 2),
                     load_5=round(os.getloadavg()[1], 2), cpus=os.cpu_count(),
                     memory_total=meminfo.get("MemTotal", 0),
                     memory_used=meminfo.get("MemTotal", 0) - meminfo.get("MemAvailable", 0),
                     disk_total=disk.total, disk_used=disk.used),
        paths=dict(root=str(ROOT), project=str(PROJECT), thingino=str(THINGINO)),
        port=62404,
    )

@app.post("/api/jobs")
def start_job():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("profile") != "t23n_sd":
        return jsonify(error="Unsupported build profile"), 400
    try:
        repo_ref = validate_branch(data.get("branch", "mymarrchWFcam"))
    except ValueError:
        return jsonify(error="Unsupported WIFICAM branch"), 400
    if not (THINGINO / ".git").is_dir():
        return jsonify(error="Missing pinned Thingino checkout"), 409
    # Refuse to race with the earlier manually launched system-level build unit.
    for scope in (["systemctl"], ["systemctl", "--user"]):
        try:
            legacy = subprocess.run(scope + ["is-active", "--quiet", "peginelab-t23n-build.service"], timeout=3)
            if legacy.returncode == 0:
                return jsonify(error="Legacy PegineLab build is running; stop/check it before starting here"), 409
        except (OSError, subprocess.TimeoutExpired):
            return jsonify(error="Cannot verify legacy build status"), 503
    reconcile()
    job_id = uuid.uuid4().hex
    unit = "peginelab-t23n-" + job_id
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        busy = db.execute("SELECT id FROM jobs WHERE status IN ('queued','running','stopping') LIMIT 1").fetchone()
        if busy:
            db.rollback()
            return jsonify(error="Сборка уже выполняется", job_id=busy["id"]), 409
        db.execute("INSERT INTO jobs (id,profile,status,created_at,unit,log_path,repo_ref) VALUES (?,?,?,?,?,?,?)",
                   (job_id, "t23n_sd", "queued", now(), unit, str(LOGS / (job_id + ".log")), repo_ref))
        db.commit()
    finally:
        db.close()
    cmd = [
        "systemd-run", "--user", "--collect", "--unit=" + unit,
        "--description=PegineLab T23N SD firmware",
        "--property=Nice=10", "--property=CPUAffinity=0-15",
        "--property=IOSchedulingClass=3",
        "--setenv=PEGINELAB_HOME=" + str(ROOT),
        os.sys.executable, str(Path(__file__).with_name("worker.py")), job_id,
    ]
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
        if proc.returncode != 0:
            record_status(job_id, "failed", details=(proc.stderr or proc.stdout).strip()[:400])
            return jsonify(error="systemd-run failed; check job details", job_id=job_id), 500
    except (OSError, subprocess.TimeoutExpired) as exc:
        record_status(job_id, "failed", details=str(exc))
        return jsonify(error="Cannot start systemd-run", job_id=job_id), 500
    return jsonify(ok=True, job_id=job_id, branch=repo_ref), 201

@app.post("/api/jobs/<job_id>/stop")
def stop_job(job_id):
    j = safe_job(job_id)
    if j is None:
        return jsonify(error="Job not found"), 404
    if j["status"] not in ACTIVE:
        return jsonify(error="Job already finished"), 409
    record_status(job_id, "stopping")
    try:
        proc = subprocess.run(["systemctl", "--user", "stop", j["unit"]],
                              text=True, capture_output=True, timeout=20)
        if proc.returncode != 0:
            record_status(job_id, "interrupted", details=proc.stderr.strip()[:400])
            return jsonify(error="Could not stop user service"), 500
    except (OSError, subprocess.TimeoutExpired):
        return jsonify(error="Stop requested; check job status"), 202
    # Worker usually marks stopped; reconcile handles abrupt shutdown.
    return jsonify(ok=True)

@app.get("/api/jobs/<job_id>/log")
def job_log(job_id):
    j = safe_job(job_id)
    if j is None:
        return jsonify(error="Job not found"), 404
    try:
        offset = max(0, int(request.args.get("offset", "0")))
    except ValueError:
        return jsonify(error="Invalid offset"), 400
    path = LOGS / (job_id + ".log")
    if not path.is_file():
        return jsonify(text="", offset=0, status=j["status"])
    size = path.stat().st_size
    if offset > size:
        offset = 0
    with path.open("rb") as handle:
        handle.seek(offset)
        chunk = handle.read(65536)
        next_offset = handle.tell()
    return jsonify(text=chunk.decode("utf-8", errors="replace"), offset=next_offset,
                   more=next_offset < size, status=j["status"])

if __name__ == "__main__":
    raise SystemExit("Run with Waitress: waitress-serve --listen=192.168.0.100:62404 app:app")
