"""Persistent state for PegineLab Firmware Factory. No secrets in Git."""
from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("PEGINELAB_HOME", "/1tbdisk/PegineLab")).resolve()
PROJECT = ROOT / "projects" / "wificam_T23N"
THINGINO = ROOT / "build" / "thingino-firmware"
DATA = ROOT / "factory-state"
LOGS = DATA / "logs"
DB = DATA / "factory.sqlite3"

ACTIVE = ("queued", "running", "stopping")

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def connect() -> sqlite3.Connection:
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    LOGS.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    os.chmod(LOGS, 0o700)
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        profile TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT,
        exit_code INTEGER,
        unit TEXT NOT NULL,
        log_path TEXT NOT NULL,
        repo_ref TEXT NOT NULL DEFAULT 'mymarrchWFcam',
        source_sha TEXT NOT NULL DEFAULT '',
        details TEXT NOT NULL DEFAULT ''
    )""")
    # Migrate existing factory-state DB in place, keeping all past jobs.
    columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
    if "repo_ref" not in columns:
        db.execute("ALTER TABLE jobs ADD COLUMN repo_ref TEXT NOT NULL DEFAULT 'mymarrchWFcam'")
    if "source_sha" not in columns:
        db.execute("ALTER TABLE jobs ADD COLUMN source_sha TEXT NOT NULL DEFAULT ''")
    db.execute("""CREATE TABLE IF NOT EXISTS artifact_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL,
        profile TEXT NOT NULL,
        kind TEXT NOT NULL,
        action TEXT NOT NULL,
        bytes INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(job_id) REFERENCES jobs(id)
    )""")
    db.commit()
    return db

def record_status(job_id: str, status: str, *, exit_code: int | None = None, details: str = "") -> None:
    db = connect()
    try:
        if status == "running":
            db.execute("UPDATE jobs SET status=?, started_at=? WHERE id=? AND status='queued'",
                       (status, now(), job_id))
        elif status in ("success", "failed", "stopped", "interrupted"):
            db.execute("UPDATE jobs SET status=?, finished_at=?, exit_code=?, details=? WHERE id=?",
                       (status, now(), exit_code, details, job_id))
        else:
            db.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
        db.commit()
    finally:
        db.close()

def get_job(job_id: str) -> dict | None:
    db = connect()
    try:
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


def record_source_sha(job_id: str, sha: str) -> None:
    db = connect()
    try:
        db.execute("UPDATE jobs SET source_sha=? WHERE id=?", (sha, job_id))
        db.commit()
    finally:
        db.close()
