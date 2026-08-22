from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import storage


class DeleteHistoryTurnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(
            storage,
            "DB_FILE",
            Path(self.temp_dir.name) / "assistant.db",
        )
        self.db_patch.start()
        storage.init_db()
        self.user_a, _ = storage.create_user("user_a", "password-a")
        self.user_b, _ = storage.create_user("user_b", "password-b")
        assert self.user_a is not None
        assert self.user_b is not None

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def save(
        self,
        user_id: int,
        role: str,
        content: str,
        *,
        parent_message_id: int | None = None,
    ) -> int:
        return storage.save_message(
            user_id,
            {
                "role": role,
                "content": content,
                "parent_message_id": parent_message_id,
            },
        )

    def test_deletes_answer_and_preceding_question_for_same_user(self) -> None:
        question_id = self.save(self.user_a, "user", "A的问题")
        other_question_id = self.save(self.user_b, "user", "B的问题")
        other_answer_id = self.save(self.user_b, "assistant", "B的回答")
        answer_id = self.save(self.user_a, "assistant", "A的回答")

        self.assertEqual(
            storage.delete_answer_turn(self.user_a, answer_id),
            (question_id, answer_id),
        )
        self.assertEqual(storage.load_messages(self.user_a), [])
        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_b)],
            [other_question_id, other_answer_id],
        )

    def test_deletes_only_selected_turn_and_is_idempotent(self) -> None:
        first_question = self.save(self.user_a, "user", "第一问")
        first_answer = self.save(self.user_a, "assistant", "第一答")
        second_question = self.save(self.user_a, "user", "第二问")
        second_answer = self.save(self.user_a, "assistant", "第二答")

        self.assertEqual(
            storage.delete_answer_turn(self.user_a, second_answer),
            (second_question, second_answer),
        )
        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_a)],
            [first_question, first_answer],
        )
        self.assertEqual(storage.delete_answer_turn(self.user_a, second_answer), ())

    def test_rejects_cross_user_or_non_answer_target(self) -> None:
        question_id = self.save(self.user_a, "user", "问题")
        answer_id = self.save(self.user_a, "assistant", "回答")

        self.assertEqual(storage.delete_answer_turn(self.user_b, answer_id), ())
        self.assertEqual(storage.delete_answer_turn(self.user_a, question_id), ())
        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_a)],
            [question_id, answer_id],
        )

    def test_explicit_parent_link_is_safe_for_interleaved_tabs(self) -> None:
        first_question = self.save(self.user_a, "user", "标签页一问题")
        second_question = self.save(self.user_a, "user", "标签页二问题")
        second_answer = self.save(
            self.user_a,
            "assistant",
            "标签页二回答",
            parent_message_id=second_question,
        )
        first_answer = self.save(
            self.user_a,
            "assistant",
            "标签页一回答",
            parent_message_id=first_question,
        )

        self.assertEqual(
            storage.delete_answer_turn(self.user_a, first_answer),
            (first_question, first_answer),
        )
        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_a)],
            [second_question, second_answer],
        )

    def test_deletes_unanswered_question_only(self) -> None:
        answered_question = self.save(self.user_a, "user", "已有回答的问题")
        answered_answer = self.save(
            self.user_a,
            "assistant",
            "已有回答",
            parent_message_id=answered_question,
        )
        unanswered_question = self.save(self.user_a, "user", "尚未回答的问题")

        self.assertTrue(
            storage.delete_unanswered_question(self.user_a, unanswered_question)
        )
        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_a)],
            [answered_question, answered_answer],
        )
        self.assertFalse(
            storage.delete_unanswered_question(self.user_a, unanswered_question)
        )

    def test_rejects_question_with_explicit_answer(self) -> None:
        question_id = self.save(self.user_a, "user", "问题")
        answer_id = self.save(
            self.user_a,
            "assistant",
            "回答",
            parent_message_id=question_id,
        )

        self.assertFalse(storage.delete_unanswered_question(self.user_a, question_id))
        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_a)],
            [question_id, answer_id],
        )

    def test_rejects_legacy_question_followed_by_answer_and_cross_user(self) -> None:
        question_id = self.save(self.user_a, "user", "旧问题")
        answer_id = self.save(self.user_a, "assistant", "旧回答")

        self.assertFalse(storage.delete_unanswered_question(self.user_a, question_id))
        self.assertFalse(storage.delete_unanswered_question(self.user_b, question_id))
        self.assertEqual(
            [item["id"] for item in storage.load_messages(self.user_a)],
            [question_id, answer_id],
        )


if __name__ == "__main__":
    unittest.main()
