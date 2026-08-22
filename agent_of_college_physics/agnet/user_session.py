"""Signed, revocable-by-account-status browser sessions for student login."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import admin_auth


USER_SESSION_COOKIE = "physics_user_session"
DEFAULT_USER_SESSION_SECONDS = 7 * 24 * 60 * 60
MIN_USER_SESSION_SECONDS = 60 * 60
MAX_USER_SESSION_SECONDS = 30 * 24 * 60 * 60


def configured_session_seconds(raw_value: str | int | None) -> int:
    """Return a bounded persistent-login duration (one hour to thirty days)."""
    try:
        seconds = int(raw_value or DEFAULT_USER_SESSION_SECONDS)
    except (TypeError, ValueError):
        seconds = DEFAULT_USER_SESSION_SECONDS
    return max(MIN_USER_SESSION_SECONDS, min(seconds, MAX_USER_SESSION_SECONDS))


def issue_login_ticket(secret: str, username: str, ttl_seconds: int = 60) -> str:
    return admin_auth.issue_token(secret, username, "user-login", ttl_seconds)


def issue_logout_ticket(secret: str, username: str, ttl_seconds: int = 60) -> str:
    return admin_auth.issue_token(secret, username, "user-logout", ttl_seconds)


def issue_session(secret: str, username: str, ttl_seconds: int) -> str:
    return admin_auth.issue_token(secret, username, "user-session", ttl_seconds)


def verify_login_ticket(secret: str, ticket: str) -> dict | None:
    return admin_auth.verify_token(secret, ticket, "user-login")


def verify_logout_ticket(secret: str, ticket: str) -> dict | None:
    return admin_auth.verify_token(secret, ticket, "user-logout")


def resolve_session(
    secret: str,
    token: str,
    account_lookup: Callable[[str], Mapping | None],
) -> dict | None:
    """Resolve a signed token to a currently active local account."""
    payload = admin_auth.verify_token(secret, token, "user-session")
    if not payload:
        return None
    account = account_lookup(str(payload["sub"]))
    if not account or not account.get("is_active"):
        return None
    if str(account.get("username", "")).casefold() != str(payload["sub"]).casefold():
        return None
    return dict(account)
