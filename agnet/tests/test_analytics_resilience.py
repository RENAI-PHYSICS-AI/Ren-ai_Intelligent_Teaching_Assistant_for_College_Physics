from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import analytics_db


def _utf8_size(value: str | None) -> int:
    return len((value or "").encode("utf-8"))


@pytest.mark.parametrize(
    ("write", "expected"),
    [
        (
            lambda: analytics_db.log_interaction(
                "session", "question", "answer", "chapter", "provider", "model",
                1, 1, 1,
            ),
            None,
        ),
        (
            lambda: analytics_db.log_error(
                "session", "question", "model_request", "failure"
            ),
            False,
        ),
        (
            lambda: analytics_db.log_feedback(
                None, "session", "opinion", "feedback"
            ),
            False,
        ),
    ],
)
def test_locked_analytics_writes_rollback_close_and_degrade(write, expected) -> None:
    connection = MagicMock()
    connection.execute.side_effect = sqlite3.OperationalError("database is locked")

    with patch.object(analytics_db, "_get_conn", return_value=connection):
        assert write() == expected

    connection.rollback.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_full_commit_failure_closes_connection_and_does_not_break_session() -> None:
    connection = MagicMock()
    connection.commit.side_effect = sqlite3.OperationalError(
        "database or disk is full"
    )

    with patch.object(analytics_db, "_get_conn", return_value=connection):
        session_id = analytics_db.start_session()

    assert session_id.startswith("ses_")
    connection.execute.assert_called_once()
    connection.rollback.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_nonrecoverable_sqlite_error_is_not_hidden_and_connection_is_closed() -> None:
    connection = MagicMock()
    connection.execute.side_effect = sqlite3.OperationalError("no such table: feedback")

    with patch.object(analytics_db, "_get_conn", return_value=connection):
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            analytics_db.log_feedback(None, "session", "opinion", "feedback")

    connection.rollback.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_anonymous_payloads_are_utf8_bounded_and_keep_original_lengths(tmp_path) -> None:
    db_path = tmp_path / "assistant.db"
    question = "匿名问题🙂" * 2_000
    answer = "匿名回答🙂" * 7_000
    interaction_error = "模型错误🙂" * 2_000
    traceback_text = "匿名堆栈🙂" * 4_000
    feedback_text = "匿名反馈🙂" * 2_000
    rag_chunks = [{"text": "检索片段🙂" * 5_000}]
    timing = {"阶段🙂" * 4_000: 1.25}

    with patch.object(analytics_db, "DB_PATH", str(db_path)):
        analytics_db.init_db()
        session_id = analytics_db.start_session()
        interaction_id = analytics_db.log_interaction(
            session_id,
            question,
            answer,
            "章节",
            "provider",
            "model",
            1,
            1,
            1,
            error=interaction_error,
            rag_chunks=rag_chunks,
            request_timing=timing,
        )
        assert interaction_id is not None
        assert analytics_db.log_error(
            session_id,
            question,
            "model_request",
            interaction_error,
            traceback_text,
        )
        assert analytics_db.log_feedback(
            interaction_id,
            session_id,
            "opinion",
            feedback_text,
        )

    connection = sqlite3.connect(db_path)
    interaction = connection.execute(
        """SELECT question, answer, error, rag_chunks_used, timing_details,
                  question_length, answer_length
           FROM interactions WHERE id=?""",
        (interaction_id,),
    ).fetchone()
    error = connection.execute(
        "SELECT question, error_message, traceback FROM error_log"
    ).fetchone()
    feedback = connection.execute("SELECT comment FROM feedback").fetchone()[0]
    connection.close()

    assert _utf8_size(interaction[0]) <= analytics_db.ANONYMOUS_QUESTION_MAX_BYTES
    assert _utf8_size(interaction[1]) <= analytics_db.ANONYMOUS_ANSWER_MAX_BYTES
    assert _utf8_size(interaction[2]) <= analytics_db.ANONYMOUS_ERROR_MESSAGE_MAX_BYTES
    assert interaction[0].endswith(analytics_db._TRUNCATION_SUFFIX)
    assert interaction[1].endswith(analytics_db._TRUNCATION_SUFFIX)
    assert interaction[5] == len(question)
    assert interaction[6] == len(answer)
    assert json.loads(interaction[3])["truncated"] is True
    assert json.loads(interaction[4])["truncated"] is True
    assert _utf8_size(error[0]) <= analytics_db.ANONYMOUS_QUESTION_MAX_BYTES
    assert _utf8_size(error[1]) <= analytics_db.ANONYMOUS_ERROR_MESSAGE_MAX_BYTES
    assert _utf8_size(error[2]) <= analytics_db.ANONYMOUS_TRACEBACK_MAX_BYTES
    assert _utf8_size(feedback) <= analytics_db.ANONYMOUS_FEEDBACK_MAX_BYTES


def test_authenticated_payloads_also_have_finite_persistence_caps(tmp_path) -> None:
    db_path = tmp_path / "assistant.db"
    question = "注册问题🙂" * 30_000
    answer = "注册回答🙂" * 100_000
    error_message = "注册错误🙂" * 10_000
    traceback_text = "注册堆栈🙂" * 30_000

    with patch.object(analytics_db, "DB_PATH", str(db_path)):
        analytics_db.init_db()
        interaction_id = analytics_db.log_interaction(
            "registered-session",
            question,
            answer,
            "章节",
            "provider",
            "model",
            1,
            1,
            1,
            error=error_message,
            user_id=42,
        )
        assert interaction_id is not None
        assert analytics_db.log_error(
            "registered-session",
            question,
            "model_request",
            error_message,
            traceback_text,
            user_id=42,
            interaction_id=interaction_id,
        )

    connection = sqlite3.connect(db_path)
    interaction = connection.execute(
        "SELECT question, answer, error FROM interactions WHERE id=?",
        (interaction_id,),
    ).fetchone()
    error = connection.execute(
        "SELECT question, error_message, traceback FROM error_log"
    ).fetchone()
    connection.close()

    assert _utf8_size(interaction[0]) <= analytics_db.AUTHENTICATED_QUESTION_MAX_BYTES
    assert _utf8_size(interaction[1]) <= analytics_db.AUTHENTICATED_ANSWER_MAX_BYTES
    assert _utf8_size(interaction[2]) <= analytics_db.AUTHENTICATED_ERROR_MESSAGE_MAX_BYTES
    assert _utf8_size(error[0]) <= analytics_db.AUTHENTICATED_QUESTION_MAX_BYTES
    assert _utf8_size(error[1]) <= analytics_db.AUTHENTICATED_ERROR_MESSAGE_MAX_BYTES
    assert _utf8_size(error[2]) <= analytics_db.AUTHENTICATED_TRACEBACK_MAX_BYTES
    assert _utf8_size(interaction[0]) > analytics_db.ANONYMOUS_QUESTION_MAX_BYTES
    assert _utf8_size(interaction[1]) > analytics_db.ANONYMOUS_ANSWER_MAX_BYTES
