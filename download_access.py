"""Short-lived, single-use authorization for downloading private SD images.

The web UI intentionally has NO password. A Wi-Fi-configured firmware image
contains secrets, so it is NEVER exposed through an unauthenticated GET.
Only someone with an SSH/shell session on Huananzhi can issue a one-time token.
No token appears in URLs, logs, browser history or database records.
"""
from __future__ import annotations
import fcntl
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from core import DATA, get_job, ROOT
from artifact_checks import artifact_path, saved_report

STORE = DATA / "download-access.json"
LOCK = DATA / "download-access.lock"
LIFETIME = 600  # seconds; token is consumed on FIRST authorized download


@contextmanager
def locked():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOCK.open("a+b") as f:
        os.chmod(LOCK, 0o600)
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def issue(job_id: str) -> str:
    """Called from an authenticated local shell, NEVER exposed over HTTP."""
    job = get_job(job_id)
    if not job or job.get("status") != "success":
        raise ValueError("No successful build for this ID")
    artifact_path(job, ROOT)
    validated = saved_report(job, ROOT, DATA)
    if not validated or validated.get("verified") is not True:
        raise ValueError("Run the SD preflight verification in the panel first")
    token = secrets.token_urlsafe(32)
    record = {
        "job": job_id,
        "digest": hashlib.sha256(token.encode()).hexdigest(),
        "expires": int(time.time()) + LIFETIME,
    }
    with locked():
        # One active ticket per station, never store plaintext bearer secrets.
        with STORE.open("w", encoding="utf-8") as f:
            os.chmod(STORE, 0o600)
            json.dump(record, f)
    return token


def consume(job_id: str, token: str) -> bool:
    if not isinstance(token, str) or len(token) > 128 or len(token) < 30:
        return False
    with locked():
        try:
            record = json.loads(STORE.read_text())
        except (OSError, ValueError):
            return False
        correct = (
            record.get("job") == job_id
            and int(record.get("expires", 0)) >= int(time.time())
            and hmac.compare_digest(
                record.get("digest", ""),
                hashlib.sha256(token.encode()).hexdigest()
            )
        )
        if correct:
            # Atomic single-use: no retry allowed even if interrupted.
            STORE.unlink(missing_ok=True)
        return correct


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "issue":
        print("Usage: python3 download_access.py issue <32-character-job-id>",
              file=sys.stderr)
        return 2
    try:
        token = issue(argv[2])
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("One-time download token (10 minutes; not a URL):")
    print(token)
    print("Paste it into the YadroKreator Download button. Do not share it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
