"""Short-lived signed tokens for administrator single sign-on."""

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time


def load_or_create_local_secret(path: str | Path) -> str:
    """Return a persistent local signing secret without exposing it in source config."""
    secret_path = Path(path)
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    try:
        with secret_path.open("x", encoding="utf-8") as handle:
            handle.write(value)
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
        return value
    except FileExistsError:
        return secret_path.read_text(encoding="utf-8").strip()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def issue_token(secret: str, username: str, purpose: str, ttl_seconds: int) -> str:
    if not secret:
        raise ValueError("Administrator secret is not configured.")
    now = int(time.time())
    payload = {
        "sub": username,
        "purpose": purpose,
        "iat": now,
        "exp": now + int(ttl_seconds),
        "nonce": secrets.token_urlsafe(18),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_token(secret: str, token: str, purpose: str) -> dict | None:
    if not secret or not token:
        return None
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_decode(supplied_signature), expected_signature):
            return None
        payload = json.loads(_decode(encoded).decode("utf-8"))
        now = int(time.time())
        if payload.get("purpose") != purpose or int(payload.get("exp", 0)) < now:
            return None
        if int(payload.get("iat", 0)) > now + 30:
            return None
        if not payload.get("sub") or not payload.get("nonce"):
            return None
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
