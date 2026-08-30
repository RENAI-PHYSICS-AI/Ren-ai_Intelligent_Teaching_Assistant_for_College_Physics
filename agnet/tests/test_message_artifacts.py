from __future__ import annotations

import io
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import storage


class MessageArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "assistant.db"
        self.storage_patch = patch.object(storage, "DB_FILE", self.db_path)
        self.storage_patch.start()
        storage.init_db()
        self.user_id, _ = storage.create_user("artifact_user", "artifact-password")
        self.other_user_id, _ = storage.create_user("artifact_other", "other-password")
        assert self.user_id is not None
        assert self.other_user_id is not None

    def tearDown(self) -> None:
        self.storage_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def artifacts() -> list[dict]:
        return [
            {
                "name": "main.tex",
                "mime": "text/x-tex",
                "data": b"\\documentclass{article}\n\\begin{document}Test\\end{document}\n",
            },
            {
                "name": "main.pdf",
                "mime": "application/pdf",
                "data": b"%PDF-1.7\nmock-pdf\n%%EOF\n",
            },
        ]

    def save_artifact_message(self, *, mode: str = "teaching_exam") -> int:
        return storage.save_message(
            self.user_id,
            {
                "role": "assistant",
                "content": "试卷已经生成。",
                "artifacts": self.artifacts(),
            },
            agent_mode=mode,
        )

    def test_legacy_table_migrates_artifacts_column_with_empty_default(self) -> None:
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
            "INSERT INTO messages(user_id, role, content) VALUES (9, 'user', '旧消息')"
        )
        connection.commit()
        connection.close()

        storage.init_db()

        connection = sqlite3.connect(self.db_path)
        column = next(
            row for row in connection.execute("PRAGMA table_info(messages)")
            if row[1] == "artifacts_json"
        )
        raw = connection.execute(
            "SELECT artifacts_json FROM messages WHERE user_id=9"
        ).fetchone()[0]
        connection.close()
        self.assertEqual(column[3], 1)
        self.assertEqual(column[4], "'[]'")
        self.assertEqual(raw, "[]")

    def test_round_trip_page_is_lazy_and_loader_checks_ownership_and_mode(self) -> None:
        message_id = self.save_artifact_message()

        loaded = storage.load_messages(
            self.user_id, agent_mode="teaching_exam"
        )[0]
        self.assertEqual(loaded["artifacts"], self.artifacts())

        with patch.object(
            storage, "_deserialize_artifacts", side_effect=AssertionError("decoded")
        ):
            page, has_more = storage.load_messages_page(
                self.user_id, agent_mode="teaching_exam"
            )
        self.assertFalse(has_more)
        self.assertEqual(page[0]["artifacts"], [])
        self.assertTrue(page[0]["_has_artifacts"])

        self.assertEqual(
            storage.load_message_artifacts(
                self.user_id, message_id, agent_mode="teaching_exam"
            ),
            self.artifacts(),
        )
        self.assertEqual(
            storage.load_message_artifacts(
                self.other_user_id, message_id, agent_mode="teaching_exam"
            ),
            [],
        )
        self.assertEqual(
            storage.load_message_artifacts(self.user_id, message_id),
            [],
        )

    def test_context_injects_only_assistant_tex_when_explicitly_enabled(self) -> None:
        storage.save_message(
            self.user_id,
            {
                "role": "user",
                "content": "请出题",
                "artifacts": [{
                    "name": "ignored.tex",
                    "mime": "text/x-tex",
                    "data": b"USER_TEX_MUST_NOT_BE_INJECTED",
                }],
            },
            agent_mode="teaching_exam",
        )
        self.save_artifact_message()

        plain = storage.load_context_messages(
            self.user_id, agent_mode="teaching_exam"
        )
        enriched = storage.load_context_messages(
            self.user_id,
            agent_mode="teaching_exam",
            include_artifacts=True,
        )

        self.assertNotIn("documentclass", plain[-1]["content"])
        self.assertIn("main.tex", enriched[-1]["content"])
        self.assertIn("\\documentclass", enriched[-1]["content"])
        self.assertNotIn("%PDF-", enriched[-1]["content"])
        self.assertNotIn("USER_TEX_MUST_NOT_BE_INJECTED", enriched[0]["content"])

    def test_structured_exam_four_files_save_and_lazy_reload(self) -> None:
        artifacts = [
            {
                "name": "main.tex",
                "mime": "application/x-tex",
                "data": b"\\documentclass{article}\n\\begin{document}Paper\\end{document}\n",
            },
            {
                "name": "main.pdf",
                "mime": "application/pdf",
                "data": b"%PDF-1.7\nmain\n%%EOF\n",
            },
            {
                "name": "answer.tex",
                "mime": "application/x-tex",
                "data": b"\\documentclass{article}\n\\begin{document}Answer\\end{document}\n",
            },
            {
                "name": "answer.pdf",
                "mime": "application/pdf",
                "data": b"%PDF-1.7\nanswer\n%%EOF\n",
            },
        ]
        message_id = storage.save_message(
            self.user_id,
            {"role": "assistant", "content": "结构化试卷已生成。", "artifacts": artifacts},
            agent_mode="teaching_exam",
        )

        page, _ = storage.load_messages_page(
            self.user_id, agent_mode="teaching_exam"
        )
        self.assertEqual(page[0]["artifacts"], [])
        self.assertTrue(page[0]["_has_artifacts"])
        self.assertEqual(
            storage.load_message_artifacts(
                self.user_id, message_id, agent_mode="teaching_exam"
            ),
            artifacts,
        )

    def test_complete_zip_package_round_trips_with_exam_artifacts(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("main.tex", "\\documentclass{article}")
            archive.writestr("fig/diagram.png", b"diagram")
        package = {
            "name": "大学物理试卷完整包.zip",
            "mime": "application/zip",
            "data": buffer.getvalue(),
        }
        message_id = storage.save_message(
            self.user_id,
            {"role": "assistant", "content": "含图试卷已生成。", "artifacts": [package]},
            agent_mode="teaching_exam",
        )
        self.assertEqual(
            storage.load_message_artifacts(
                self.user_id, message_id, agent_mode="teaching_exam"
            ),
            [package],
        )

    def test_rejects_unsafe_types_names_formats_and_size_limits(self) -> None:
        base = {"role": "assistant", "content": "x"}
        invalid_artifacts = [
            {"name": "../main.tex", "mime": "text/x-tex", "data": b"x"},
            {"name": "main.html", "mime": "text/html", "data": b"x"},
            {"name": "main.tex", "mime": "text/html", "data": b"x"},
            {"name": "main.pdf", "mime": "application/pdf", "data": b"not pdf"},
            {"name": "bundle.zip", "mime": "application/zip", "data": b"not zip"},
            {"name": "main.tex", "mime": "text/x-tex", "data": "not bytes"},
        ]
        for artifact in invalid_artifacts:
            with self.subTest(artifact=artifact), self.assertRaises(ValueError):
                storage.save_message(
                    self.user_id,
                    {**base, "artifacts": [artifact]},
                    agent_mode="teaching_exam",
                )

        with patch.object(storage, "ARTIFACT_MAX_ITEM_BYTES", 3):
            with self.assertRaises(ValueError):
                storage.save_message(
                    self.user_id,
                    {
                        **base,
                        "artifacts": [{
                            "name": "main.tex", "mime": "text/x-tex", "data": b"1234"
                        }],
                    },
                    agent_mode="teaching_exam",
                )
        with (
            patch.object(storage, "ARTIFACT_MAX_ITEM_BYTES", 10),
            patch.object(storage, "ARTIFACT_MAX_TOTAL_BYTES", 5),
        ):
            with self.assertRaises(ValueError):
                storage.save_message(
                    self.user_id,
                    {
                        **base,
                        "artifacts": [
                            {"name": "a.tex", "mime": "text/x-tex", "data": b"123"},
                            {"name": "b.tex", "mime": "text/x-tex", "data": b"456"},
                        ],
                    },
                    agent_mode="teaching_exam",
                )

    def test_markdown_lists_names_without_embedding_payloads(self) -> None:
        exported = storage.messages_to_markdown(
            [{
                "role": "assistant",
                "content": "生成完成。",
                "artifacts": self.artifacts(),
            }],
            "teacher",
        )
        self.assertIn("生成文件：main.tex", exported)
        self.assertIn("生成文件：main.pdf", exported)
        self.assertNotIn("mock-pdf", exported)
        self.assertNotIn("documentclass", exported)


if __name__ == "__main__":
    unittest.main()
