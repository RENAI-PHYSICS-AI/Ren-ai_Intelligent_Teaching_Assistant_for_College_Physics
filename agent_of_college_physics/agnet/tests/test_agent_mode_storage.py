from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import analytics_db
import storage


class AgentModeStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "assistant.db"
        self.storage_patch = patch.object(storage, "DB_FILE", self.db_path)
        self.storage_patch.start()
        storage.init_db()
        self.user_id, _ = storage.create_user("mode_user", "mode-password")
        assert self.user_id is not None

    def tearDown(self) -> None:
        self.storage_patch.stop()
        self.temp_dir.cleanup()

    def save(
        self,
        role: str,
        content: str,
        *,
        mode: str = "assistant",
        parent_message_id: int | None = None,
        images: list[dict] | None = None,
    ) -> int:
        return storage.save_message(
            self.user_id,
            {
                "role": role,
                "content": content,
                "parent_message_id": parent_message_id,
                "images": images or [],
            },
            agent_mode=mode,
        )

    def test_legacy_messages_migrate_to_default_mode_and_composite_index(self) -> None:
        self.db_path.unlink()
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """CREATE TABLE messages (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL,
                   role TEXT NOT NULL,
                   content TEXT NOT NULL,
                   images_json TEXT NOT NULL DEFAULT '[]',
                   visualizations_json TEXT NOT NULL DEFAULT '[]',
                   interaction_id INTEGER,
                   parent_message_id INTEGER,
                   created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        connection.execute(
            "INSERT INTO messages(user_id, role, content) VALUES (7, 'user', '旧消息')"
        )
        connection.commit()
        connection.close()

        storage.init_db()

        connection = sqlite3.connect(self.db_path)
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(messages)")
        }
        legacy_mode = connection.execute(
            "SELECT agent_mode FROM messages WHERE user_id=7"
        ).fetchone()[0]
        index_columns = [
            row[2]
            for row in connection.execute(
                "PRAGMA index_info(idx_messages_user_mode_id)"
            )
        ]
        connection.close()

        self.assertEqual(columns["agent_mode"][3], 1)
        self.assertEqual(columns["agent_mode"][4], "'assistant'")
        self.assertEqual(legacy_mode, "assistant")
        self.assertEqual(index_columns, ["user_id", "agent_mode", "id"])
        self.assertEqual(
            [item["content"] for item in storage.load_messages(7)],
            ["旧消息"],
        )

    def test_default_calls_remain_assistant_compatible(self) -> None:
        message_id = storage.save_message(
            self.user_id,
            {"role": "user", "content": "默认模式", "images": []},
        )
        loaded = storage.load_messages(self.user_id)
        page, has_more = storage.load_messages_page(self.user_id, limit=8)

        self.assertEqual([item["id"] for item in loaded], [message_id])
        self.assertEqual(loaded[0]["agent_mode"], "assistant")
        self.assertEqual([item["id"] for item in page], [message_id])
        self.assertFalse(has_more)

    def test_load_page_and_context_are_isolated_between_modes(self) -> None:
        assistant_q1 = self.save("user", "助教问题一")
        teaching_q1 = self.save("user", "教研问题一", mode="teaching_exam")
        assistant_a1 = self.save(
            "assistant", "助教回答一", parent_message_id=assistant_q1
        )
        teaching_a1 = self.save(
            "assistant",
            "教研回答一",
            mode="teaching_exam",
            parent_message_id=teaching_q1,
        )
        assistant_q2 = self.save("user", "助教问题二")
        assistant_a2 = self.save(
            "assistant", "助教回答二", parent_message_id=assistant_q2
        )
        teaching_q2 = self.save("user", "教研问题二", mode="teaching_exam")
        teaching_a2 = self.save(
            "assistant",
            "教研回答二",
            mode="teaching_exam",
            parent_message_id=teaching_q2,
        )

        assistant_page, assistant_more = storage.load_messages_page(
            self.user_id, limit=2
        )
        older_assistant, older_more = storage.load_messages_page(
            self.user_id, before_id=assistant_q2, limit=2
        )
        teaching_page, teaching_more = storage.load_messages_page(
            self.user_id, limit=2, agent_mode="teaching_exam"
        )

        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_id)],
            [assistant_q1, assistant_a1, assistant_q2, assistant_a2],
        )
        self.assertEqual(
            [item["id"] for item in storage.load_messages(
                self.user_id, agent_mode="teaching_exam"
            )],
            [teaching_q1, teaching_a1, teaching_q2, teaching_a2],
        )
        self.assertEqual(
            [item["id"] for item in assistant_page],
            [assistant_q2, assistant_a2],
        )
        self.assertTrue(assistant_more)
        self.assertEqual(
            [item["id"] for item in older_assistant],
            [assistant_q1, assistant_a1],
        )
        self.assertFalse(older_more)
        self.assertEqual(
            [item["id"] for item in teaching_page],
            [teaching_q2, teaching_a2],
        )
        self.assertTrue(teaching_more)
        self.assertEqual(
            [item["content"] for item in storage.load_context_messages(self.user_id)],
            ["助教问题一", "助教回答一", "助教问题二", "助教回答二"],
        )
        self.assertEqual(
            [
                item["content"]
                for item in storage.load_context_messages(
                    self.user_id, agent_mode="teaching_exam"
                )
            ],
            ["教研问题一", "教研回答一", "教研问题二", "教研回答二"],
        )

    def test_delete_and_clear_never_cross_agent_mode(self) -> None:
        unanswered = self.save("user", "助教未回答")
        teaching_stray = self.save(
            "assistant", "另一模式的相邻回答", mode="teaching_exam"
        )
        self.assertTrue(storage.delete_unanswered_question(self.user_id, unanswered))

        assistant_q = self.save("user", "助教问题")
        assistant_a = self.save(
            "assistant", "助教回答", parent_message_id=assistant_q
        )
        teaching_q = self.save("user", "教研问题", mode="teaching_exam")
        teaching_a = self.save(
            "assistant",
            "教研回答",
            mode="teaching_exam",
            parent_message_id=teaching_q,
        )

        self.assertEqual(storage.delete_answer_turn(self.user_id, teaching_a), ())
        self.assertEqual(
            storage.delete_answer_turn(
                self.user_id, teaching_a, agent_mode="teaching_exam"
            ),
            (teaching_q, teaching_a),
        )
        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_id)],
            [assistant_q, assistant_a],
        )

        teaching_left = self.save("user", "保留的教研消息", mode="teaching_exam")
        self.assertFalse(storage.delete_message(self.user_id, teaching_left))
        storage.clear_messages(self.user_id)
        self.assertEqual(storage.load_messages(self.user_id), [])
        self.assertEqual(
            [
                item["id"]
                for item in storage.load_messages(
                    self.user_id, agent_mode="teaching_exam"
                )
            ],
            [teaching_stray, teaching_left],
        )
        self.assertTrue(
            storage.delete_message(
                self.user_id, teaching_left, agent_mode="teaching_exam"
            )
        )


class AgentModeAnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "assistant.db"
        self.storage_patch = patch.object(storage, "DB_FILE", self.db_path)
        self.analytics_patch = patch.object(analytics_db, "DB_PATH", str(self.db_path))
        self.storage_patch.start()
        self.analytics_patch.start()
        storage.init_db()
        analytics_db.init_db()
        self.user_id, _ = storage.create_user("analytics_mode", "mode-password")
        assert self.user_id is not None

    def tearDown(self) -> None:
        self.analytics_patch.stop()
        self.storage_patch.stop()
        self.temp_dir.cleanup()

    def test_get_user_by_id_returns_current_active_state(self) -> None:
        self.assertEqual(analytics_db.get_user_by_id(self.user_id)["is_active"], 1)
        connection = sqlite3.connect(self.db_path)
        connection.execute("UPDATE users SET is_active=0 WHERE id=?", (self.user_id,))
        connection.commit()
        connection.close()
        self.assertEqual(analytics_db.get_user_by_id(self.user_id)["is_active"], 0)

    def test_legacy_interactions_migrate_to_default_mode(self) -> None:
        self.db_path.unlink()
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            """CREATE TABLE interactions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   session_id TEXT NOT NULL,
                   timestamp TEXT NOT NULL,
                   question TEXT NOT NULL,
                   answer TEXT,
                   chapter TEXT,
                   provider TEXT,
                   model TEXT,
                   tokens_input INTEGER DEFAULT 0,
                   tokens_output INTEGER DEFAULT 0,
                   response_time_ms INTEGER DEFAULT 0,
                   error TEXT,
                   feedback TEXT,
                   rag_chunks_used TEXT,
                   question_length INTEGER DEFAULT 0,
                   answer_length INTEGER DEFAULT 0
               )"""
        )
        connection.execute(
            """INSERT INTO interactions(session_id, timestamp, question)
               VALUES ('legacy', '2026-01-01', '旧分析记录')"""
        )
        connection.commit()
        connection.close()

        analytics_db.init_db()

        connection = sqlite3.connect(self.db_path)
        column = next(
            row for row in connection.execute("PRAGMA table_info(interactions)")
            if row[1] == "agent_mode"
        )
        mode = connection.execute(
            "SELECT agent_mode FROM interactions WHERE session_id='legacy'"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(column[3], 1)
        self.assertEqual(column[4], "'assistant'")
        self.assertEqual(mode, "assistant")

    def test_log_interaction_defaults_and_accepts_explicit_mode(self) -> None:
        session_id = analytics_db.start_session(self.user_id)
        analytics_db.log_interaction(
            session_id, "默认问题", "默认回答", "章节", "local", "model",
            1, 2, 3, user_id=self.user_id,
        )
        analytics_db.log_interaction(
            session_id, "教研问题", "教研回答", "章节", "local", "model",
            1, 2, 3, user_id=self.user_id, agent_mode="teaching_exam",
        )
        connection = sqlite3.connect(self.db_path)
        rows = connection.execute(
            "SELECT question, agent_mode FROM interactions ORDER BY id"
        ).fetchall()
        connection.close()
        self.assertEqual(rows, [("默认问题", "assistant"), ("教研问题", "teaching_exam")])

    def test_legacy_interaction_migration_pairs_questions_within_each_mode(self) -> None:
        assistant_q = storage.save_message(
            self.user_id, {"role": "user", "content": "助教问题"}
        )
        teaching_q = storage.save_message(
            self.user_id,
            {"role": "user", "content": "教研问题"},
            agent_mode="teaching_exam",
        )
        storage.save_message(
            self.user_id,
            {"role": "assistant", "content": "助教回答", "parent_message_id": assistant_q},
        )
        storage.save_message(
            self.user_id,
            {"role": "assistant", "content": "教研回答", "parent_message_id": teaching_q},
            agent_mode="teaching_exam",
        )

        analytics_db.init_db()

        connection = sqlite3.connect(self.db_path)
        rows = connection.execute(
            """SELECT agent_mode, question, answer FROM interactions
               WHERE provider='legacy' ORDER BY agent_mode"""
        ).fetchall()
        connection.close()
        self.assertEqual(
            rows,
            [
                ("assistant", "助教问题", "助教回答"),
                ("teaching_exam", "教研问题", "教研回答"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
