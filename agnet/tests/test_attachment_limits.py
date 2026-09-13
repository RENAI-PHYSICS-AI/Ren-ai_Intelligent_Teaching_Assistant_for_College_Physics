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


def _message(images: list[dict]) -> dict:
    return {"role": "user", "content": "附件测试", "images": images}


def _attachment(name: str, size: int) -> dict:
    return {"name": name, "mime": "image/png", "data": b"x" * size}


def test_storage_rechecks_attachment_count_item_and_total_bytes() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ), patch.object(storage, "UPLOAD_MAX_COUNT", 2), patch.object(
        storage, "UPLOAD_MAX_ITEM_BYTES", 8
    ), patch.object(storage, "UPLOAD_MAX_TOTAL_BYTES", 10):
        storage.init_db()
        user_id, _ = storage.create_user("attachment_user", "strong-password")
        assert user_id is not None

        with pytest.raises(ValueError, match="最多上传"):
            storage.save_message(
                user_id,
                _message([_attachment("a.png", 1)] * 3),
            )
        with pytest.raises(ValueError, match="单个附件"):
            storage.save_message(user_id, _message([_attachment("a.png", 9)]))
        with pytest.raises(ValueError, match="总大小"):
            storage.save_message(
                user_id,
                _message([_attachment("a.png", 6), _attachment("b.png", 6)]),
            )

        message_id = storage.save_message(
            user_id,
            _message([_attachment("a.png", 5), _attachment("b.png", 5)]),
        )
        assert storage.load_message_images(user_id, message_id) == [
            _attachment("a.png", 5),
            _attachment("b.png", 5),
        ]


def test_chat_input_preflights_count_and_aggregate_size() -> None:
    source = (APP_DIR / "app.py").read_text(encoding="utf-8")
    assert "len(uploaded_files) > UPLOAD_MAX_COUNT" in source
    assert "total_upload_bytes > UPLOAD_MAX_TOTAL_BYTES" in source
    assert "len(payload) > UPLOAD_MAX_ITEM_BYTES" in source


def test_persisted_blob_quota_is_checked_atomically_per_user() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ), patch.object(storage, "USER_BLOB_DAILY_STORED_BYTES", 500), patch.object(
        storage, "USER_BLOB_TOTAL_STORED_BYTES", 10_000
    ), patch.object(storage, "USER_BLOB_DAILY_MESSAGE_LIMIT", 10):
        storage.init_db()
        user_id, _ = storage.create_user("quota_user", "strong-password")
        assert user_id is not None
        storage.save_message(user_id, _message([_attachment("a.png", 200)]))
        with pytest.raises(ValueError, match="今日保存"):
            storage.save_message(user_id, _message([_attachment("b.png", 200)]))
