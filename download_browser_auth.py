"""Browser-only login to download private WIFICAM SD images.

Purpose: remove the need to copy an SSH one-time token for every download.
The dashboard still has no global login. Private-image export requires one
persistent browser login; the password is configured once in the web UI.

IMPORTANT: Enrolment is trust-on-first-use: host the dashboard ONLY on a
trusted private LAN/VPN, preferably behind TLS. HTTP alone does not protect
passwords, cookies or image contents against on-path capture. Never expose
TCP/62404 to the public Internet.
"""
from __future__ import annotations
import fcntl
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from core import DATA

AUTH_FILE = DATA / "download-browser-auth.json"
LOCK_FILE = DATA / "download-browser-auth.lock"
COOKIE = "peginelab_sd_access"
TTL = 30 * 24 * 3600
BLOCK_TIME = 600
MAX_ATTEMPTS = 5
ROUNDS = 450000


def trusted_network(ip: str | None) -> bool:
    """Only accept a direct private/loopback peer, never X-Forwarded-For."""
    try:
        address = ipaddress.ip_address(ip or "")
        if isinstance(address, ipaddress.IPv6Address):
            return address.is_loopback
        return address.is_loopback or any(address in net for net in (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
        ))
    except ValueError:
        return False


@contextmanager
def locked():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    with LOCK_FILE.open("a+b") as lock:
        os.chmod(LOCK_FILE, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _load() -> dict | None:
    try:
        obj = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


def _save(state: dict) -> None:
    """Never log or publish salt, hashes or signing key."""
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=DATA, prefix=".sd-auth-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(state, file)
        os.replace(tmp, AUTH_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ROUNDS
    ).hex()


def _serializer(state: dict) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        bytes.fromhex(state["key"]), salt="peginelab-sd-download-only"
    )


def configured() -> bool:
    return _load() is not None


def authorized(cookie: str | None) -> bool:
    if not cookie:
        return False
    state = _load()
    if not state:
        return False
    try:
        body = _serializer(state).loads(cookie, max_age=TTL)
        return (isinstance(body, dict) and
                hmac.compare_digest(str(body.get("version", "")),
                                    state["version"]))
    except (ValueError, KeyError, BadSignature, SignatureExpired):
        return False


def initialize(password: str) -> str:
    """One-time local browser password setup, not per-download SSH codes."""
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("Пароль для скачивания должен содержать 12–128 символов")
    with locked():
        if _load() is not None:
            raise ValueError("Пароль уже создан. Войдите с существующим паролем")
        salt = secrets.token_hex(16)
        state = {
            "salt": salt,
            "digest": _digest(password, salt),
            "key": secrets.token_hex(32),
            "version": secrets.token_hex(16),
            "failed": 0,
            "blocked_until": 0,
        }
        _save(state)
        return _serializer(state).dumps({"version": state["version"]})


def login(password: str) -> str:
    if not isinstance(password, str) or len(password) > 128:
        raise ValueError("Неверный пароль")
    with locked():
        state = _load()
        if state is None:
            raise ValueError("Сначала создайте пароль скачивания")
        now = int(time.time())
        if state.get("blocked_until", 0) > now:
            raise ValueError("Слишком много попыток. Повторите через 10 минут")
        expected = _digest(password, state["salt"])
        if not hmac.compare_digest(expected, state["digest"]):
            state["failed"] = int(state.get("failed", 0)) + 1
            if state["failed"] >= MAX_ATTEMPTS:
                state["failed"] = 0
                state["blocked_until"] = now + BLOCK_TIME
            _save(state)
            raise ValueError("Неверный пароль")
        state["failed"] = 0
        state["blocked_until"] = 0
        _save(state)
        return _serializer(state).dumps({"version": state["version"]})
