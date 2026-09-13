from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import analytics_db
import storage


def _counts(db_path: Path, user_id: int) -> tuple[int, int, int, int]:
    connection = sqlite3.connect(db_path)
    values = tuple(
        connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        for table in ("messages", "interactions", "feedback", "error_log")
    )
    connection.close()
    return values


def _save_failed_turn(user_id: int, mode: str, question: str) -> tuple[int, int, int]:
    interaction_id = analytics_db.log_interaction(
        "session-test",
        question,
        "回答",
        "测试",
        "test",
        "test",
        1,
        1,
        1,
        "failed",
        [],
        user_id,
        agent_mode=mode,
    )
    analytics_db.log_feedback(
        interaction_id, "session-test", "bad", "测试反馈", user_id
    )
    analytics_db.log_error(
        "session-test",
        question,
        "model_request",
        "测试错误",
        "trace",
        user_id,
        interaction_id=interaction_id,
        agent_mode=mode,
    )
    question_id = storage.save_message(
        user_id, {"role": "user", "content": question}, agent_mode=mode
    )
    answer_id = storage.save_message(
        user_id,
        {
            "role": "assistant",
            "content": "回答",
            "parent_message_id": question_id,
            "interaction_id": interaction_id,
        },
        agent_mode=mode,
    )
    return question_id, answer_id, interaction_id


def test_delete_turn_removes_owned_analytics_and_preserves_other_user() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "assistant.db"
        with patch.object(storage, "DB_FILE", db_path), patch.object(
            analytics_db, "DB_PATH", str(db_path)
        ):
            storage.init_db()
            analytics_db.init_db()
            user_a, _ = storage.create_user("cleanup_a", "strong-password")
            user_b, _ = storage.create_user("cleanup_b", "strong-password")
            assert user_a and user_b
            question_id, answer_id, _ = _save_failed_turn(
                user_a, "assistant", "相同问题"
            )
            _save_failed_turn(user_b, "assistant", "相同问题")

            assert storage.delete_answer_turn(user_a, answer_id) == (
                question_id,
                answer_id,
            )
            assert _counts(db_path, user_a) == (0, 0, 0, 0)
            assert _counts(db_path, user_b) == (2, 1, 1, 1)


def test_clear_mode_is_transactional_and_cleans_legacy_errors() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "assistant.db"
        with patch.object(storage, "DB_FILE", db_path), patch.object(
            analytics_db, "DB_PATH", str(db_path)
        ):
            storage.init_db()
            analytics_db.init_db()
            user_id, _ = storage.create_user("cleanup_modes", "strong-password")
            assert user_id
            _save_failed_turn(user_id, "assistant", "助教问题")
            _save_failed_turn(user_id, "teaching_exam", "教研问题")
            connection = sqlite3.connect(db_path)
            connection.execute(
                """INSERT INTO error_log
                   (session_id, timestamp, question, error_type, error_message,
                    traceback, user_id, interaction_id, agent_mode)
                   VALUES ('legacy', datetime('now'), '旧问题', 'legacy', '旧错误',
                           '', ?, NULL, NULL)""",
                (user_id,),
            )
            connection.execute(
                """INSERT INTO feedback
                   (interaction_id, session_id, timestamp, rating, comment, user_id)
                   VALUES (NULL, 'legacy', datetime('now'), 'bad', '旧反馈', ?)""",
                (user_id,),
            )
            connection.commit()
            connection.close()

            storage.clear_messages(user_id, agent_mode="assistant")

            assert [
                row["content"]
                for row in storage.load_messages(
                    user_id, agent_mode="teaching_exam"
                )
            ] == ["教研问题", "回答"]
            connection = sqlite3.connect(db_path)
            interaction_modes = connection.execute(
                "SELECT agent_mode FROM interactions WHERE user_id=?", (user_id,)
            ).fetchall()
            feedback_count = connection.execute(
                "SELECT COUNT(*) FROM feedback WHERE user_id=?", (user_id,)
            ).fetchone()[0]
            error_modes = connection.execute(
                "SELECT agent_mode FROM error_log WHERE user_id=?", (user_id,)
            ).fetchall()
            connection.close()
            assert interaction_modes == [("teaching_exam",)]
            assert feedback_count == 1
            assert error_modes == [("teaching_exam",)]
