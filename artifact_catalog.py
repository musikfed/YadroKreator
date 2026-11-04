"""Per-job artifacts and explicit local deletion; never mutate Git/other projects."""
from __future__ import annotations
import json
import re
from pathlib import Path
from core import ROOT, DATA
from project_profiles import job_root
from artifact_checks import artifact_path, saved_report, report_path
from git_sources import workspace_for

JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
TERMINAL = {"success", "failed", "stopped", "interrupted"}
KIND_BY_PROFILE = {"t23n_sd": "sd_image", "t23n_helper_sd": "sd_image", "irila_preflight": "audit_json"}

def _guard_job(job: dict):
    if (not JOB_ID.fullmatch(str(job.get("id",""))) or
            job.get("profile") not in KIND_BY_PROFILE):
        raise ValueError("Unknown or invalid build job")
    return job_root(job["id"], job["profile"], root=ROOT)

def expected_path(job: dict, *, root: Path=ROOT) -> Path | None:
    """Only factory-owned outputs; NOT Git-tracked Thingino baseline or shared out/."""
    if job["profile"] == "irila_preflight":
        return job_root(job["id"], "irila_preflight", root=root) / "irila-source-audit.json"
    if job["profile"] in ("t23n_sd", "t23n_helper_sd"):
        if job.get("status") == "success":
            try:
                return artifact_path(job, root)
            except (FileNotFoundError, ValueError, OSError):
                return None
        # Failed/cancelled builds may leave a large partial disk image. Offer
        # explicit CLEANUP ONLY, never validation/download/promotion.
        if job.get("status") in TERMINAL:
            work=workspace_for(job["id"],root,profile=job["profile"])
            for relative in ("out/private-sd/thingino-t23-sd.bin",
                             "out/candidate-sd/thingino-t23-sd.bin"):
                candidate=work/relative
                if safe_owned(candidate,job,root=root) and candidate.is_file():
                    return candidate
        return None
    raise ValueError("Unsupported profile")

def safe_owned(path: Path, job: dict, *, root: Path=ROOT) -> bool:
    """Guard parents and expected location; no symlink traversal or arbitrary paths."""
    base = job_root(job["id"], job["profile"], root=root)
    root = root.absolute()
    if not base.absolute().is_relative_to(root):
        return False
    if not path.absolute().is_relative_to(base.absolute()):
        return False
    for part in (path, *path.parents):
        if part == root.parent:
            break
        if part.is_symlink():
            return False
        if part == root:
            break
    try:
        return path.resolve().is_relative_to(base.resolve())
    except (OSError, RuntimeError):
        return False

def classify(job: dict, deleted=False, *, root: Path=ROOT, data: Path=DATA) -> dict:
    _guard_job(job)
    mode=KIND_BY_PROFILE[job["profile"]]
    result=dict(job_id=job["id"],profile=job["profile"],kind=mode,
                status=job["status"],exit_code=job.get("exit_code"),
                details=(job.get("details") or "")[:300],
                source_sha=job.get("source_sha") or "",
                base_source_sha=job.get("base_source_sha") or "",
                created_at=job.get("created_at"),available=False,deleted=deleted,
                bytes=0,name="",validation=None)
    if job["status"] != "success":
        if job["status"] in TERMINAL:
            # Partial results: show size and explicit cleanup, but NEVER a
            # valid image, nor a button to download or verify.
            partial=expected_path(job,root=root)
            if partial is not None and safe_owned(partial,job,root=root) and partial.is_file():
                result.update(partial=True,cleanup_bytes=partial.stat().st_size,name=partial.name)
        return result
    path=expected_path(job,root=root)
    if path is None or not safe_owned(path,job,root=root) or not path.is_file():
        return result
    if job["profile"] == "irila_preflight":
        try:
            report=json.loads(path.read_text(encoding="utf-8"))
            if (report.get("profile") != "irila_preflight" or
                    report.get("source_sha") != job.get("source_sha") or path.stat().st_size>16384):
                return result
        except (OSError,ValueError,TypeError):
            return result
        result["validation"]={"verified":True,"scope":"Source audit JSON only; not an IMG"}
    else:
        report=saved_report(job,root,data)
        result["validation"]=report
    result.update(available=True,bytes=path.stat().st_size,name=path.name)
    return result

def purge_file(job: dict, *, root: Path=ROOT, data: Path=DATA) -> tuple[int,str]:
    """Remove only output of one finished job; no recursive deletion and no log deletion."""
    _guard_job(job)
    if job["status"] not in TERMINAL:
        raise ValueError("Active build outputs cannot be removed")
    path=expected_path(job,root=root)
    if path is None or not safe_owned(path,job,root=root) or not path.is_file():
        raise FileNotFoundError("No owned finished artifact found")
    nbytes=path.stat().st_size
    # A hard-linked artifact should not be assumed to be private.
    if path.stat().st_nlink > 1:
        raise ValueError("Hard-linked artifact cannot be deleted automatically")
    path.unlink()
    if job["profile"] == "t23n_sd":
        for other in (path.with_name(path.name+".sha256"),
                      report_path(job["id"], data, profile=job["profile"])):
            if other.is_file() and not other.is_symlink() and (
                other.parent==path.parent or other.parent==report_path(job["id"],data,profile=job["profile"]).parent
            ):
                other.unlink()
    return nbytes,KIND_BY_PROFILE[job["profile"]]
