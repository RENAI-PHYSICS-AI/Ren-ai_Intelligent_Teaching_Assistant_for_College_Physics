from __future__ import annotations

import sys
from pathlib import Path

import pytest


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import storage


@pytest.fixture
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "DB_FILE", tmp_path / "assistant.db")
    monkeypatch.setattr(storage, "DATABASE_MIN_FREE_BYTES", 0)
    storage.init_db()


def _create_user(username: str) -> int:
    user_id, message = storage.create_user(
        username, "strong-password", client_key=f"client-{username}"
    )
    assert user_id is not None, message
    return user_id


def _message(content: str, *, with_attachment: bool = False) -> dict:
    images = []
    if with_attachment:
        images = [{"name": "sample.bin", "mime": "application/octet-stream", "data": b"abc"}]
    return {
        "role": "user",
        "content": content,
        "images": images,
        "visualizations": [],
    }


def _usage(scope: str) -> dict[str, int | str] | None:
    with storage._connect() as connection:
        row = connection.execute(
            "SELECT * FROM storage_usage WHERE scope=?", (scope,)
        ).fetchone()
    return dict(row) if row is not None else None


def _message_bytes(message_id: int) -> int:
    with storage._connect() as connection:
        row = connection.execute(
            f"SELECT {storage._MESSAGE_STORED_BYTES_SQL} AS stored_bytes "
            "FROM messages WHERE id=?",
            (message_id,),
        ).fetchone()
    assert row is not None
    return int(row["stored_bytes"])


def test_insert_trigger_tracks_user_and_global_usage(isolated_storage: None) -> None:
    user_id = _create_user("ledger_insert")
    message_id = storage.save_message(
        user_id, _message("物理", with_attachment=True)
    )
    expected_bytes = _message_bytes(message_id)

    for scope in (f"user:{user_id}", "global"):
        usage = _usage(scope)
        assert usage is not None
        assert usage["stored_bytes"] == expected_bytes
        assert usage["daily_bytes"] == expected_bytes
        assert usage["daily_count"] == 1
        assert usage["daily_blob_count"] == 1


def test_delete_and_user_cascade_reduce_usage_ledger(isolated_storage: None) -> None:
    user_a = _create_user("ledger_delete_a")
    user_b = _create_user("ledger_delete_b")
    first_a = storage.save_message(user_a, _message("first-a"))
    second_a = storage.save_message(
        user_a, _message("second-a", with_attachment=True)
    )
    only_b = storage.save_message(user_b, _message("only-b"))
    second_a_bytes = _message_bytes(second_a)
    only_b_bytes = _message_bytes(only_b)

    assert storage.delete_message(user_a, first_a)
    user_usage = _usage(f"user:{user_a}")
    global_usage = _usage("global")
    assert user_usage is not None and global_usage is not None
    assert user_usage["stored_bytes"] == second_a_bytes
    assert user_usage["daily_count"] == 1
    assert user_usage["daily_blob_count"] == 1
    assert global_usage["stored_bytes"] == second_a_bytes + only_b_bytes
    assert global_usage["daily_count"] == 2

    with storage._connect() as connection:
        connection.execute("DELETE FROM users WHERE id=?", (user_a,))

    cascaded_usage = _usage(f"user:{user_a}")
    global_usage = _usage("global")
    assert cascaded_usage is not None and global_usage is not None
    assert cascaded_usage["stored_bytes"] == 0
    assert cascaded_usage["daily_bytes"] == 0
    assert cascaded_usage["daily_count"] == 0
    assert cascaded_usage["daily_blob_count"] == 0
    assert global_usage["stored_bytes"] == only_b_bytes
    assert global_usage["daily_bytes"] == only_b_bytes
    assert global_usage["daily_count"] == 1


def test_global_daily_byte_quota_rejects_without_changing_ledger(
    isolated_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_a = _create_user("global_quota_a")
    user_b = _create_user("global_quota_b")
    first_id = storage.save_message(user_a, _message("first"))
    first_bytes = _message_bytes(first_id)
    monkeypatch.setattr(
        storage, "GLOBAL_MESSAGE_DAILY_STORED_BYTES", first_bytes + 1
    )

    with pytest.raises(ValueError, match="服务器今日保存容量"):
        storage.save_message(user_b, _message("second"))

    usage = _usage("global")
    assert usage is not None
    assert usage["stored_bytes"] == first_bytes
    assert usage["daily_bytes"] == first_bytes
    assert usage["daily_count"] == 1


def test_user_daily_message_count_quota_uses_ledger(
    isolated_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = _create_user("message_count_quota")
    monkeypatch.setattr(storage, "USER_MESSAGE_DAILY_LIMIT", 1)
    storage.save_message(user_id, _message("first"))

    with pytest.raises(ValueError, match="消息次数"):
        storage.save_message(user_id, _message("second"))

    usage = _usage(f"user:{user_id}")
    assert usage is not None
    assert usage["daily_count"] == 1


def test_content_and_visualization_size_limits_are_enforced_before_insert(
    isolated_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = _create_user("message_field_limits")
    monkeypatch.setattr(storage, "MESSAGE_MAX_CONTENT_BYTES", 5)
    with pytest.raises(ValueError, match="消息正文"):
        storage.save_message(user_id, _message("物理"))

    monkeypatch.setattr(storage, "MESSAGE_MAX_CONTENT_BYTES", 100)
    monkeypatch.setattr(storage, "MESSAGE_MAX_VISUALIZATION_BYTES", 8)
    oversized_visualization = _message("ok")
    oversized_visualization["visualizations"] = [{"x": 1}]
    with pytest.raises(ValueError, match="可视化数据"):
        storage.save_message(user_id, oversized_visualization)

    with storage._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
