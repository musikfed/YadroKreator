"""PegineLab Project Contract v1 is declarative and non-executable.

A contract describes a project, platform, expected outputs, and requested adapter.
The factory executes ONLY adapters it owns and reviews separately.
"""
from __future__ import annotations
import json
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

SCHEMA = "peginelab.project.v1"
MAX_BYTES = 32768
SAFE_PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\Z")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
SHA = re.compile(r"[a-f0-9]{40}\Z")
REPO = re.compile(r"musikfed/[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
ADAPTER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
MODES = {"build", "observe"}
OUTPUT_TYPES = {"img", "bin", "iso", "uimage", "kernel", "rootfs", "archive", "report", "other"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirect refused for project contract download")


def _path(value: object) -> str:
    if (not isinstance(value, str) or len(value) > 200 or
            not SAFE_PATH.fullmatch(value) or
            any(segment.startswith(".") for segment in value.split("/"))):
        raise ValueError("Contract paths must be repository-relative and without traversal")
    return value


def validate_contract(document: object, *, repo: str, branch: str, mode: str) -> dict:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError("Unsupported PegineLab project contract schema")
    if not REPO.fullmatch(repo) or mode not in MODES or not isinstance(branch, str) or not branch:
        raise ValueError("Invalid project source or mode")
    project = document.get("project")
    if not isinstance(project, dict):
        raise ValueError("Missing project description")
    if (project.get("repository") != repo or project.get("branch") != branch
            or project.get("mode") != mode):
        raise ValueError("Contract repository, branch and mode must match selected source")
    name = project.get("name")
    if not isinstance(name, str) or not 2 <= len(name) <= 70 or any(ord(c) < 32 for c in name):
        raise ValueError("Invalid project name")
    if len(json.dumps(document, ensure_ascii=False).encode("utf-8")) > MAX_BYTES:
        raise ValueError("Contract too large")
    platform = document.get("platform", {})
    if not isinstance(platform, dict):
        raise ValueError("Platform must be an object")
    for k in ("architecture", "board", "toolchain"):
        v = platform.get(k, "")
        if not isinstance(v, str) or len(v) > 120 or any(ord(c) < 32 for c in v):
            raise ValueError("Invalid platform field: " + k)
    targets = document.get("targets", [])
    if not isinstance(targets, list) or len(targets) > 8 or any(
        not isinstance(v, str) or not TOKEN.fullmatch(v) for v in targets
    ):
        raise ValueError("Invalid project targets")
    pipeline = document.get("pipeline")
    if mode == "build":
        if not isinstance(pipeline, dict):
            raise ValueError("Build projects require pipeline declaration")
        adapter = pipeline.get("adapter")
        if not isinstance(adapter, str) or not ADAPTER.fullmatch(adapter):
            raise ValueError("Build pipeline must request a named adapter")
        if pipeline.get("entrypoint") is not None:
            _path(pipeline["entrypoint"]) # Documentation only, never auto-executed.
        outputs = document.get("outputs")
        if not isinstance(outputs, list) or not outputs or len(outputs) > 24:
            raise ValueError("Build projects must declare expected output types and paths")
    else:
        if pipeline not in (None, {}):
            raise ValueError("Observed project cannot declare an executable pipeline")
        outputs = document.get("outputs", [])
        if not isinstance(outputs, list) or len(outputs) > 24:
            raise ValueError("Invalid observed project outputs")
    for output in outputs:
        if not isinstance(output, dict) or output.get("type") not in OUTPUT_TYPES:
            raise ValueError("Invalid output type")
        _path(output.get("path"))
    monitor = document.get("monitoring", {})
    if not isinstance(monitor, dict) or set(monitor) - {"signals", "notes"}:
        raise ValueError("Monitoring accepts only descriptive signals and notes")
    signals = monitor.get("signals", [])
    if not isinstance(signals, list) or len(signals) > 20 or any(
        not isinstance(v, str) or not TOKEN.fullmatch(v) for v in signals
    ):
        raise ValueError("Invalid monitoring signal names")
    extras = document.get("extensions", {})
    if not isinstance(extras, dict) or len(extras) > 20:
        raise ValueError("Extensions must be a small namespaced object")
    for key in extras:
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*\.[a-z][a-z0-9_-]*",key):
            raise ValueError("Extension keys must be namespaced, e.g. vendor.feature")
    if set(document) - {"schema", "project", "platform", "targets", "pipeline", "outputs",
                        "monitoring", "extensions", "description", "docs"}:
        raise ValueError("Unknown contract fields; use extensions for custom metadata")
    if "docs" in document:
        docs = document["docs"]
        if not isinstance(docs, list) or len(docs) > 20:
            raise ValueError("Invalid documentation list")
        for item in docs:
            _path(item)
    return dict(document)


def read_contract(repo: str, branch: str, sha: str) -> dict:
    """Read only pinned project manifest from a fixed GitHub host."""
    if not REPO.fullmatch(repo) or not SHA.fullmatch(sha):
        raise ValueError("Invalid pinned contract source")
    from project_registry import validate_ref
    validate_ref(branch)
    url=f"https://raw.githubusercontent.com/{repo}/{sha}/peginelab.project.json"
    request=Request(url,headers={"User-Agent":"PegineLab-YadroKreator/1.0",
                                 "Accept":"application/json"})
    try:
        with build_opener(NoRedirect()).open(request,timeout=10) as response:
            if response.geturl()!=url:
                raise ValueError("Unexpected contract URL")
            data=response.read(MAX_BYTES+1)
    except (HTTPError, URLError, OSError) as exc:
        raise ValueError("Cannot load peginelab.project.json from pinned GitHub commit") from exc
    if len(data)>MAX_BYTES:
        raise ValueError("Contract exceeds 32 KiB")
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Contract is not valid UTF-8 JSON") from exc
