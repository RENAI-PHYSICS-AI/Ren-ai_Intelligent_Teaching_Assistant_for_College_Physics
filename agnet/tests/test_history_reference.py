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


class HistoryReferenceStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "assistant.db"
        self.db_patch = patch.object(storage, "DB_FILE", self.db_path)
        self.db_patch.start()
        storage.init_db()
        self.user_a, _ = storage.create_user("reference_a", "password-a")
        self.user_b, _ = storage.create_user("reference_b", "password-b")
        assert self.user_a is not None
        assert self.user_b is not None

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def test_reference_round_trips_with_preview(self) -> None:
        answer_id = storage.save_message(
            self.user_a,
            {"role": "assistant", "content": "这是需要继续讨论的历史回答。"},
            agent_mode="teaching_exam",
        )
        question_id = storage.save_message(
            self.user_a,
            {
                "role": "user",
                "content": "请依据这条回答继续修改。",
                "quoted_message_id": answer_id,
            },
            agent_mode="teaching_exam",
        )

        messages = storage.load_messages(
            self.user_a, agent_mode="teaching_exam"
        )
        quoted = next(item for item in messages if item["id"] == question_id)
        self.assertEqual(quoted["quoted_message_id"], answer_id)
        self.assertIn("历史回答", quoted["_quoted_preview"])

        page, has_more = storage.load_messages_page(
            self.user_a, agent_mode="teaching_exam"
        )
        self.assertFalse(has_more)
        quoted_page = next(item for item in page if item["id"] == question_id)
        self.assertEqual(quoted_page["quoted_message_id"], answer_id)
        self.assertIn("继续讨论", quoted_page["_quoted_preview"])

    def test_reference_loader_enforces_owner_role_and_mode(self) -> None:
        answer_id = storage.save_message(
            self.user_a,
            {
                "role": "assistant",
                "content": "```latex answer.tex\n\\documentclass{article}\n```",
                "artifacts": [
                    {
                        "name": "answer.tex",
                        "mime": "application/x-tex",
                        "data": b"\\documentclass{article}",
                    }
                ],
            },
            agent_mode="teaching_exam",
        )

        reference = storage.load_message_reference(
            self.user_a,
            answer_id,
            agent_mode="teaching_exam",
            include_artifacts=True,
        )
        self.assertIsNotNone(reference)
        assert reference is not None
        self.assertEqual(reference["id"], answer_id)
        self.assertEqual(reference["artifacts"][0]["name"], "answer.tex")
        self.assertIsNone(
            storage.load_message_reference(
                self.user_b, answer_id, agent_mode="teaching_exam"
            )
        )
        self.assertIsNone(
            storage.load_message_reference(
                self.user_a, answer_id, agent_mode="assistant"
            )
        )

    def test_foreign_or_non_assistant_reference_is_not_persisted(self) -> None:
        foreign_answer = storage.save_message(
            self.user_b,
            {"role": "assistant", "content": "其他用户回答"},
        )
        own_question = storage.save_message(
            self.user_a,
            {"role": "user", "content": "原问题"},
        )
        for reference_id in (foreign_answer, own_question, 999999):
            message_id = storage.save_message(
                self.user_a,
                {
                    "role": "user",
                    "content": "不能引用越权消息",
                    "quoted_message_id": reference_id,
                },
            )
            row = next(
                item
                for item in storage.load_messages(self.user_a)
                if item["id"] == message_id
            )
            self.assertIsNone(row["quoted_message_id"])


def test_history_reference_ui_and_direct_pdf_path_are_wired() -> None:
    source = (APP_DIR / "app.py").read_text(encoding="utf-8")
    assert '"↩ 引用回答"' in source
    assert "resolve_selected_reference(" in source
    assert "reference_model_context(quoted_reference)" in source
    assert "if artifact_delivery_requested:" in source
    assert "reference_compilation_input(quoted_reference)" in source
    assert "artifact_file_requested and not artifact_revision_requested" in source
    assert "and quoted_reference is None" in source
    assert "source_material_artifact_revision_requested(question)" in source
    assert "reset_history_view()" in source
    assert '"tex_compile"' in source


if __name__ == "__main__":
    unittest.main()
