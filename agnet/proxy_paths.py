"""Helpers for generating URLs when the app is mounted below a proxy prefix."""

from __future__ import annotations

from urllib.parse import urlsplit


def public_prefix(public_base: str = "", gateway_prefix: str = "") -> str:
    """Return only the URL path prefix (for example ``/agent``)."""
    value = (public_base or "").strip()
    if value:
        parsed = urlsplit(value)
        value = parsed.path if parsed.scheme or parsed.netloc else value
    else:
        value = (gateway_prefix or "").strip()
    value = "/" + value.strip("/")
    return "" if value == "/" else value


def with_public_prefix(path: str, public_base: str = "", gateway_prefix: str = "") -> str:
    """Prefix an internal absolute path, while leaving full URLs untouched."""
    if not path or not path.startswith("/") or path.startswith("//"):
        return path
    prefix = public_prefix(public_base, gateway_prefix)
    if not prefix or path == prefix or path.startswith(prefix + "/"):
        return path
    return prefix + path
