"""Explicit GitHub project registry, independent of factory job history.

A branch added for the established WIFICAM T23N recipe is buildable.
A newly registered repository is DISPLAY/INVENTORY ONLY until an audited
compiler adapter exists. Never execute arbitrary GitHub build scripts.
"""
from __future__ import annotations
from datetime import datetime, timezone
from contextlib import contextmanager
from functools import wraps
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from core import DATA
from project_contract import validate_contract, read_contract, MODES

SCHEMA = "peginelab.factory.project-registry.v1"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,100}\Z")
SLUG = re.compile(r"[a-z][a-z0-9-]{1,31}\Z")
RESERVED = {"overview", "builds", "irila", "helper", "artifacts", "system",
            "wificam", "t23n", "factory"}
DEFAULT_BRANCHES = ("mymarrchWFcam", "main")
MAX_PROJECTS = 20
MAX_BRANCHES = 25


def validate_ref(value: object) -> str:
    if (not isinstance(value, str) or not BRANCH.fullmatch(value)
            or value.endswith(("/", ".", ".lock")) or value.startswith(".")
            or ".." in value or "//" in value or "/." in value or ".lock/" in value
            or value.startswith(("refs/", "origin/"))):
        raise ValueError("Invalid Git branch; use a normal branch name without Git ref metacharacters")
    return value


def validate_repo(value: object) -> str:
    """GitHub owner is fixed. No arbitrary domains, local files, or URLs."""
    if not isinstance(value, str):
        raise ValueError("Repository must be musikfed/repository")
    text = value.strip()
    if text.startswith("https://github.com/"):
        parsed = urlsplit(text)
        if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("Only HTTPS GitHub repositories are supported")
        text = parsed.path.strip("/")
    if text.endswith(".git"):
        text = text[:-4]
    parts = text.split("/")
    if len(parts) != 2 or parts[0] != "musikfed" or not NAME.fullmatch(parts[1]):
        raise ValueError("Only repos under musikfed with safe names are accepted")
    return parts[1]


def validate_slug(value: object) -> str:
    if not isinstance(value, str) or not SLUG.fullmatch(value) or value in RESERVED:
        raise ValueError("Invalid or reserved project slug")
    return value


def registry_path(data: Path = DATA) -> Path:
    return Path(data) / "registered-projects.json"


def load(data: Path = DATA) -> dict:
    path = registry_path(data)
    if path.is_symlink():
        raise ValueError("Project registry symlink refused")
    if not path.is_file():
        return {"schema": SCHEMA, "branches": [], "projects": []}
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("Unexpected project registry schema")
    branches = record.get("branches")
    projects = record.get("projects")
    if not isinstance(branches, list) or not isinstance(projects, list) or len(branches) > MAX_BRANCHES or len(projects) > MAX_PROJECTS:
        raise ValueError("Invalid registry collections")
    for b in branches:
        validate_ref(b)
    if len(set(branches)) != len(branches):
        raise ValueError("Duplicate branches")
    slugs = []
    for p in projects:
        if not isinstance(p, dict):
            raise ValueError("Invalid project descriptor")
        slugs.append(validate_slug(p.get("slug")))
        validate_repo(p.get("repository"))
        validate_ref(p.get("branch"))
        if not isinstance(p.get("title"), str) or not 2 <= len(p["title"]) <= 70:
            raise ValueError("Invalid project title")
        if p.get("build_mode") not in ("pending_adapter", "observe"):
            raise ValueError("Invalid project registry mode")
        if p.get("mode", "build") not in MODES:
            raise ValueError("Unknown project mode")
        if p.get("mode", "build") == "build" and p.get("build_mode") != "pending_adapter":
            raise ValueError("Unreviewed builds cannot be enabled from registry")
        if p.get("mode") == "observe" and p.get("build_mode") != "observe":
            raise ValueError("Observed projects cannot be marked buildable")
    if len(set(slugs)) != len(slugs):
        raise ValueError("Duplicate project slug")
    return record


def allowed_branches(data: Path = DATA) -> tuple[str, ...]:
    return (*DEFAULT_BRANCHES, *(name for name in load(data)["branches"]
                                if name not in DEFAULT_BRANCHES))


def git_ref_sha(repo: str, branch: str) -> str | None:
    """Read-only SHA lookup for trusted source, no checkout or arbitrary URL."""
    repo = validate_repo(f"musikfed/{repo}")
    branch = validate_ref(branch)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/bin/false")
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--exit-code", "--heads",
             f"https://github.com/musikfed/{repo}.git", "refs/heads/" + branch],
            check=False, capture_output=True, text=True, timeout=15, env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if (len(parts) == 2 and parts[1] == "refs/heads/" + branch
                and re.fullmatch(r"[a-fA-F0-9]{40}", parts[0])):
            return parts[0].lower()
    return None


def git_ref_exists(repo: str, branch: str) -> bool:
    return git_ref_sha(repo, branch) is not None


def _save(record: dict, data: Path) -> None:
    data = Path(data)
    if data.is_symlink():
        raise ValueError("Registry directory symlink refused")
    data.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = registry_path(data)
    if path.is_symlink():
        raise ValueError("Registry symlink refused")
    temp = data / ("registered-projects.json." + os.urandom(8).hex() + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(record, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def _registration_lock(data: Path):
    """Prevent two operators losing each other's registry updates."""
    data = Path(data)
    if data.is_symlink():
        raise ValueError("Project registry directory symlink refused")
    data.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = data / ".registered-projects.lock"
    if lock.is_symlink():
        raise ValueError("Project registry lock symlink refused")
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "r+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _serialized_registration(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with _registration_lock(kwargs.get("data", DATA)):
            return func(*args, **kwargs)
    return wrapper


@_serialized_registration
def add_branch(branch: str, *, data: Path = DATA, verify=git_ref_exists) -> dict:
    branch = validate_ref(branch)
    record = load(data)
    if branch in DEFAULT_BRANCHES or branch in record["branches"]:
        return record
    if len(record["branches"]) >= MAX_BRANCHES:
        raise ValueError("Maximum registered branch count reached")
    if not verify("wificam_T23N", branch):
        raise ValueError("Branch was not confirmed on GitHub (check exact name/network)")
    record["branches"].append(branch)
    _save(record, data)
    return record


@_serialized_registration
def add_project(slug: str, title: str, repository: str, branch: str, *,
                data: Path = DATA, mode: str = "observe", verify=git_ref_exists,
                source_sha: str | None = None, manifest: dict | None = None) -> dict:
    """Manual opt-in: monitor any selected repo; build only with a valid contract.

    Even a valid build contract remains pending_adapter: it cannot grant itself
    any executable permission or add a new factory build profile.
    """
    slug = validate_slug(slug)
    repo = validate_repo(repository)
    branch = validate_ref(branch)
    title = title.strip() if isinstance(title, str) else ""
    if not 2 <= len(title) <= 70 or any(ord(char) < 32 for char in title):
        raise ValueError("Project name must contain 2–70 printable characters")
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError("Choose project mode build or observe")
    record = load(data)
    if len(record["projects"]) >= MAX_PROJECTS:
        raise ValueError("Project registry is full")
    if any(p["slug"] == slug for p in record["projects"]):
        raise ValueError("Project already exists")
    if not verify(repo, branch):
        raise ValueError("GitHub branch not found; no project was registered")
    contract = None
    if mode == "build":
        pinned_sha = source_sha or git_ref_sha(repo, branch)
        if not pinned_sha:
            raise ValueError("Cannot confirm SHA for build contract; no project added")
        doc = manifest if manifest is not None else read_contract(
            f"musikfed/{repo}", branch, pinned_sha)
        doc = validate_contract(doc, repo=f"musikfed/{repo}",
                                branch=branch, mode="build")
        contract = {
            "schema": doc["schema"], "source_sha": pinned_sha,
            "adapter": doc["pipeline"]["adapter"],
            "entrypoint": doc["pipeline"].get("entrypoint"),
            "platform": doc.get("platform", {}),
            "outputs": doc["outputs"], "targets": doc.get("targets", []),
            "docs": doc.get("docs", []),
        }
    elif manifest is not None:
        doc=validate_contract(manifest,repo=f"musikfed/{repo}",
                              branch=branch, mode="observe")
        contract={"schema":doc["schema"],"platform":doc.get("platform",{}),
                  "monitoring":doc.get("monitoring",{}),
                  "docs":doc.get("docs", [])}
    record["projects"].append({
        "slug": slug, "title": title,
        "repository": f"musikfed/{repo}",
        "branch": branch, "mode":mode,
        "build_mode": "pending_adapter" if mode=="build" else "observe",
        "contract": contract,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    _save(record, data)
    return record
