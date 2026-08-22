from __future__ import annotations

import os
import sys
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import admin_api
import gateway
import user_session


def request_for(
    path: str,
    *,
    prefix: str = "/agent",
    proto: str = "https",
    cookie: str = "",
) -> Request:
    headers = [
        (b"x-forwarded-prefix", prefix.encode("ascii")),
        (b"x-forwarded-proto", proto.encode("ascii")),
    ]
    if cookie:
        headers.append((b"cookie", cookie.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8603),
        }
    )


class UserSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        admin_api._USED_USER_LOGIN_NONCES.clear()
        self.secret = "test-signing-secret-that-is-not-used-outside-tests"
        self.account = {
            "id": 12,
            "username": "student01",
            "role": "student",
            "is_active": 1,
        }

    def test_signed_session_resolves_only_active_matching_account(self) -> None:
        token = user_session.issue_session(self.secret, "student01", 3600)
        self.assertEqual(
            user_session.resolve_session(self.secret, token, lambda _: self.account)["id"],
            12,
        )
        inactive = dict(self.account, is_active=0)
        self.assertIsNone(
            user_session.resolve_session(self.secret, token, lambda _: inactive)
        )
        self.assertIsNone(
            user_session.resolve_session("different-secret", token, lambda _: self.account)
        )

    def test_session_duration_is_bounded(self) -> None:
        self.assertEqual(user_session.configured_session_seconds("bad"), 604800)
        self.assertEqual(user_session.configured_session_seconds(60), 3600)
        self.assertEqual(user_session.configured_session_seconds(99_999_999), 2_592_000)

    def test_login_ticket_sets_secure_httponly_cookie_and_prefixed_redirect(self) -> None:
        ticket = user_session.issue_login_ticket(self.secret, "student01")
        with (
            patch.object(admin_api, "_load_admin_token", return_value=self.secret),
            patch.object(
                admin_api.db, "get_user_by_username", return_value=self.account
            ),
            patch.dict(os.environ, {"PHYSICS_USER_SESSION_SECONDS": "7200"}),
        ):
            response = admin_api.user_login_session(
                request_for("/session-login"), ticket=ticket, mode="dark"
            )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/agent/?mode=dark")
        set_cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertIn("SameSite=strict", set_cookie)
        self.assertIn("Max-Age=7200", set_cookie)
        self.assertIn("Path=/agent", set_cookie)
        parsed = SimpleCookie()
        parsed.load(set_cookie)
        token = parsed[user_session.USER_SESSION_COOKIE].value
        resolved = user_session.resolve_session(
            self.secret, token, lambda _: self.account
        )
        self.assertEqual(resolved["username"], "student01")

        with (
            patch.object(admin_api, "_load_admin_token", return_value=self.secret),
            patch.object(
                admin_api.db, "get_user_by_username", return_value=self.account
            ),
        ):
            with self.assertRaises(HTTPException) as reused:
                admin_api.user_login_session(
                    request_for("/session-login"), ticket=ticket, mode="dark"
                )
        self.assertEqual(reused.exception.status_code, 401)

        with (
            patch.object(admin_api, "_load_admin_token", return_value=self.secret),
            patch.object(
                admin_api.db, "get_user_by_username", return_value=self.account
            ),
        ):
            idempotent = admin_api.user_login_session(
                request_for(
                    "/session-login",
                    cookie=f"{user_session.USER_SESSION_COOKIE}={token}",
                ),
                ticket=ticket,
                mode="dark",
            )
        self.assertEqual(idempotent.status_code, 303)
        self.assertEqual(idempotent.headers["location"], "/agent/?mode=dark")
        self.assertNotIn("set-cookie", idempotent.headers)

    def test_reused_login_ticket_rejects_a_different_user_session(self) -> None:
        ticket = user_session.issue_login_ticket(self.secret, "student01")
        other_session = user_session.issue_session(self.secret, "student02", 3600)
        other_account = dict(self.account, id=13, username="student02")

        def lookup(username: str):
            return self.account if username == "student01" else other_account

        with (
            patch.object(admin_api, "_load_admin_token", return_value=self.secret),
            patch.object(admin_api.db, "get_user_by_username", side_effect=lookup),
        ):
            first = admin_api.user_login_session(
                request_for("/session-login"), ticket=ticket, mode="system"
            )
            self.assertEqual(first.status_code, 303)
            with self.assertRaises(HTTPException) as reused:
                admin_api.user_login_session(
                    request_for(
                        "/session-login",
                        cookie=(
                            f"{user_session.USER_SESSION_COOKIE}={other_session}"
                        ),
                    ),
                    ticket=ticket,
                    mode="system",
                )
        self.assertEqual(reused.exception.status_code, 401)

    def test_logout_requires_ticket_and_expires_cookie(self) -> None:
        ticket = user_session.issue_logout_ticket(self.secret, "student01")
        with patch.object(admin_api, "_load_admin_token", return_value=self.secret):
            response = admin_api.user_logout_session(
                request_for("/session-logout"), ticket=ticket, mode="light"
            )
        self.assertEqual(response.headers["location"], "/agent/?mode=light")
        set_cookie = response.headers["set-cookie"]
        self.assertIn("Max-Age=0", set_cookie)
        self.assertIn("Secure", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("Path=/agent", set_cookie)

    def test_gateway_sends_session_endpoints_to_auth_service(self) -> None:
        from aiohttp.test_utils import make_mocked_request

        login_request = make_mocked_request(
            "GET", "/agent/session-login?ticket=abc", headers={"Host": "example"}
        )
        logout_request = make_mocked_request(
            "GET", "/agent/session-logout?ticket=xyz", headers={"Host": "example"}
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(login_request),
                f"{gateway.ADMIN_UPSTREAM}/session-login?ticket=abc",
            )
            self.assertEqual(
                gateway.upstream_url(logout_request),
                f"{gateway.ADMIN_UPSTREAM}/session-logout?ticket=xyz",
            )

    def test_login_redirect_uses_top_level_native_meta_refresh(self) -> None:
        app_source = (APP_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn('<meta http-equiv="refresh" content="0; url=', app_source)
        self.assertIn('target="_self"', app_source)
        self.assertNotIn("window.parent.location.replace", app_source)
        self.assertNotIn("st.link_button(button_label", app_source)


if __name__ == "__main__":
    unittest.main()
