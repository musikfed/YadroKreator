"""Live build timing and conservative, history-based ETA.

The bar is not CPU/compiler progress: Buildroot has no total step counter.
When no relevant successful historical build exists, show an indeterminate bar.
Estimates use the median of up to five prior successful *same profile+branch*
builds, so cold-cache and network delays may invalidate the prediction.
"""
from __future__ import annotations
from datetime import datetime, timezone
from statistics import median


def seconds_between(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        return max(0, int((datetime.fromisoformat(b) -
                           datetime.fromisoformat(a)).total_seconds()))
    except (TypeError, ValueError):
        return None


def decorate_jobs(jobs: list[dict], *, current: str | None = None) -> None:
    now = current or datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Only finished successful jobs supply an ETA; failed/aborted builds are
    # not representative. Never show a fixed fake progress percentage.
    for job in jobs:
        started = job.get("started_at")
        finished = job.get("finished_at")
        active = job.get("status") in ("queued", "running", "stopping")
        job["elapsed_seconds"] = seconds_between(started, now if active else finished)
        job["duration_seconds"] = seconds_between(started, finished)
        sample = [
            prev["duration_seconds"] for prev in jobs
            if prev["id"] != job["id"] and
            prev.get("status") == "success" and
            prev.get("profile") == job.get("profile") and
            prev.get("repo_ref") == job.get("repo_ref") and
            prev.get("duration_seconds") is not None and
            prev["duration_seconds"] > 0
        ][:5]
        job["estimate_seconds"] = int(median(sample)) if sample else None
        job["estimate_samples"] = len(sample)
        job["eta_seconds"] = None
        job["progress_percent"] = 100 if job.get("status") == "success" else None
        if job["status"] == "running" and job["elapsed_seconds"] is not None and sample:
            estimate = job["estimate_seconds"]
            # Never claim completion on time alone. A timed-out estimate
            # stays at 95% until the worker actually reports success.
            job["progress_percent"] = min(95, max(1, int(95 *
                job["elapsed_seconds"] / estimate)))
            if job["elapsed_seconds"] < estimate:
                job["eta_seconds"] = estimate - job["elapsed_seconds"]
