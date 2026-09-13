from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import storage


def test_login_failures_are_bounded_per_client_and_identifier() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ), patch.object(storage, "LOGIN_FAILURE_LIMIT", 2), patch.object(
        storage, "LOGIN_LOCK_SECONDS", 60
    ), patch.object(storage.time, "time", return_value=1_000.0):
        storage.init_db()
        user_id, _ = storage.create_user("limited_user", "correct-password")
        assert user_id is not None

        assert storage.authenticate("limited_user", "wrong", "client-a") == (
            None,
            None,
        )
        assert storage.authenticate("limited_user", "wrong", "client-a") == (
            None,
            None,
        )
        with pytest.raises(storage.LoginRateLimited) as limited:
            storage.authenticate("limited_user", "correct-password", "client-a")
        assert limited.value.retry_after_seconds == 60

        assert storage.authenticate(
            "limited_user", "correct-password", "client-b"
        ) == (user_id, "limited_user")

        with patch.object(storage.time, "time", return_value=1_061.0):
            assert storage.authenticate(
                "limited_user", "correct-password", "client-a"
            ) == (user_id, "limited_user")


def test_rotating_identifiers_still_hits_the_client_bucket() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ), patch.object(storage, "LOGIN_CLIENT_FAILURE_LIMIT", 2), patch.object(
        storage, "LOGIN_LOCK_SECONDS", 60
    ), patch.object(storage.time, "time", return_value=2_000.0):
        storage.init_db()
        assert storage.authenticate("missing-one", "wrong", "client-a") == (None, None)
        assert storage.authenticate("missing-two", "wrong", "client-a") == (None, None)
        with pytest.raises(storage.LoginRateLimited):
            storage.authenticate("missing-three", "wrong", "client-a")


def test_username_and_employee_alias_share_the_account_bucket() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ), patch.object(storage, "LOGIN_FAILURE_LIMIT", 10), patch.object(
        storage, "LOGIN_ACCOUNT_FAILURE_LIMIT", 2
    ), patch.object(storage, "LOGIN_LOCK_SECONDS", 60), patch.object(
        storage.time, "time", return_value=3_000.0
    ):
        storage.init_db()
        user_id, _ = storage.create_user("teacher-user", "correct-password")
        assert user_id is not None
        with storage._connect() as connection:
            connection.execute(
                """UPDATE users SET identity_verified=1, identity_type='teacher',
                          institutional_id='243120', real_name='教师',
                          teacher_approval_status='approved'
                   WHERE id=?""",
                (user_id,),
            )

        assert storage.authenticate("teacher-user", "wrong", "client-a") == (None, None)
        assert storage.authenticate("243120", "wrong", "client-b") == (None, None)
        with pytest.raises(storage.LoginRateLimited):
            storage.authenticate("teacher-user", "correct-password", "client-c")


@pytest.mark.parametrize("login_name", ["limited_user", "missing_user"])
def test_oversized_password_skips_pbkdf_but_counts_as_failed_login(
    login_name: str,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ), patch.object(storage, "LOGIN_FAILURE_LIMIT", 2), patch.object(
        storage, "LOGIN_LOCK_SECONDS", 60
    ), patch.object(storage.time, "time", return_value=3_500.0):
        storage.init_db()
        user_id, _ = storage.create_user("limited_user", "correct-password")
        assert user_id is not None
        oversized_password = "密" * 86  # 258 UTF-8 bytes.

        with patch.object(
            storage,
            "_password_hash",
            side_effect=AssertionError("oversized passwords must not reach PBKDF"),
        ) as password_hash:
            assert storage.authenticate(
                login_name, oversized_password, "oversized-client"
            ) == (None, None)
            assert storage.authenticate(
                login_name, oversized_password, "oversized-client"
            ) == (None, None)
            with pytest.raises(storage.LoginRateLimited):
                storage.authenticate(
                    login_name, oversized_password, "oversized-client"
                )
            password_hash.assert_not_called()


def test_password_limit_accepts_exactly_256_utf8_bytes() -> None:
    password = "密" * 85 + "a"
    assert len(password.encode("utf-8")) == storage.PASSWORD_MAX_UTF8_BYTES
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ):
        storage.init_db()
        user_id, _ = storage.create_user("boundary-user", password)
        assert user_id is not None
        assert storage.authenticate("boundary-user", password, "client-a") == (
            user_id,
            "boundary-user",
        )


def test_registration_is_rate_limited_before_expensive_duplicate_hashing() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ), patch.object(storage, "REGISTRATION_CLIENT_WINDOW_LIMIT", 2), patch.object(
        storage.time, "time", return_value=4_000.0
    ):
        storage.init_db()
        user_id, _ = storage.create_user(
            "existing-user", "correct-password", "client-a"
        )
        assert user_id is not None
        with patch.object(
            storage, "_password_hash", side_effect=AssertionError("must not hash duplicate")
        ):
            duplicate_id, duplicate_message = storage.create_user(
                "existing-user", "wrong-password", "client-a"
            )
        assert duplicate_id is None
        assert "已存在" in duplicate_message
        blocked_id, blocked_message = storage.create_user(
            "rotated-user", "correct-password", "client-a"
        )
        assert blocked_id is None
        assert "频繁" in blocked_message
