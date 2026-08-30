from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_kb
import build_teacher_exam_kb
import config
from rag import KnowledgeBase


def chunk(chunk_id: str, text: str, *, relative_path: str = "") -> dict:
    return {
        "id": chunk_id,
        "source": f"{chunk_id}.md",
        "source_type": "测试资料",
        "page": 1,
        "chapter": "测试章节",
        "text": text,
        "relative_path": relative_path,
        "locator": "全文",
        "priority": 1.0,
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TeacherPrivateKnowledgeBaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_config_keeps_private_sources_and_index_outside_public_files(self) -> None:
        self.assertEqual(
            config.TEACHER_EXAM_MATERIALS_DIR,
            config.MATERIALS_DIR / "教师专用" / "教研考试",
        )
        self.assertEqual(
            config.TEACHER_EXAM_KB_FILE,
            config.KB_DIR / "private" / "teacher_exam.jsonl",
        )
        self.assertEqual(
            config.TEACHER_EXAM_KB_MANIFEST_FILE,
            config.KB_DIR / "private" / "teacher_exam.manifest.json",
        )
        self.assertNotEqual(config.TEACHER_EXAM_KB_FILE, config.KB_FILE)

    def test_combined_index_loads_base_and_private_and_skips_missing_files(self) -> None:
        base = self.root / "base.jsonl"
        private = self.root / "private.jsonl"
        missing = self.root / "missing.jsonl"
        write_jsonl(base, [chunk("base", "公开力学知识包含动量守恒和机械能守恒。")])
        write_jsonl(private, [chunk("private", "教师命题蓝图包含绝密评分细则和试卷结构。")])

        legacy = KnowledgeBase(base)
        self.assertEqual(legacy.path, base)
        self.assertEqual(legacy.paths, (base,))
        self.assertEqual([item.id for item in legacy.chunks], ["base"])
        self.assertFalse(legacy.search("绝密评分细则"))

        combined = KnowledgeBase([base, missing, private])
        self.assertEqual([item.id for item in combined.chunks], ["base", "private"])
        self.assertEqual(combined.search("动量守恒", top_k=1)[0][0].id, "base")
        self.assertEqual(combined.search("绝密评分细则", top_k=1)[0][0].id, "private")

        absent = KnowledgeBase([missing])
        self.assertEqual(absent.chunks, [])
        self.assertEqual(absent.chapters, [])
        self.assertEqual(absent.search("任意问题"), [])

    def test_public_builder_excludes_the_complete_teacher_tree(self) -> None:
        project_root = self.root / "project"
        materials = project_root / "教学素材"
        textbook_dir = materials / "教材"
        teacher_dir = materials / "教师专用"
        kb_dir = project_root / "agnet" / "knowledge_base"
        imports_dir = kb_dir / "imports"
        textbook_dir.mkdir(parents=True)
        imports_dir.mkdir(parents=True)
        teacher_exam_dir = teacher_dir / "教研考试"
        teacher_exam_dir.mkdir(parents=True)

        textbook = textbook_dir / "物理学.pdf"
        solution = textbook_dir / "物理学习题解答.pdf"
        textbook.write_bytes(b"test")
        solution.write_bytes(b"test")
        (materials / "公开资料.md").write_text(
            "公开教学资料讨论大学物理课堂中的动量守恒、机械能守恒和实验方法。",
            encoding="utf-8",
        )
        private_phrase = "教师绝密命题答案与评分细则不得进入面向学生的公共知识库索引。"
        (teacher_exam_dir / "命题资料.md").write_text(private_phrase, encoding="utf-8")

        with (
            patch.multiple(
                build_kb,
                PROJECT_ROOT=project_root,
                MATERIALS_DIR=materials,
                TEXTBOOK_DIR=textbook_dir,
                TEACHER_MATERIALS_DIR=teacher_dir,
                KB_DIR=kb_dir,
                KB_FILE=kb_dir / "chunks.jsonl",
                IMPORTED_KB_DIR=imports_dir,
            ),
            patch.object(
                build_kb,
                "find_primary_pdfs",
                return_value=(textbook.resolve(), solution.resolve()),
            ),
            patch.object(
                build_kb,
                "pdf_pages",
                return_value=["基准教材正文包含足够长度的大学物理课程知识和公式推导内容。"],
            ),
        ):
            manifest = build_kb.build()

        rows = read_jsonl(kb_dir / "chunks.jsonl")
        serialized = json.dumps(rows, ensure_ascii=False)
        self.assertNotIn(private_phrase, serialized)
        self.assertFalse(
            any(
                build_kb.is_teacher_private_relative_path(row.get("relative_path"))
                for row in rows
            )
        )
        self.assertEqual(manifest["files_scanned"], 3)
        self.assertEqual(
            manifest["excluded_materials"], ["教学素材/教师专用"]
        )

    def test_merge_imports_removes_legacy_private_rows(self) -> None:
        kb_dir = self.root / "knowledge_base"
        imports_dir = kb_dir / "imports"
        imports_dir.mkdir(parents=True)
        kb_file = kb_dir / "chunks.jsonl"
        write_jsonl(
            kb_file,
            [
                chunk("public", "公开课程知识内容足够长，可继续保留在公共索引中。", relative_path="公开.md"),
                chunk(
                    "private",
                    "旧索引中的教师命题资料必须在仅合并导入库时一并移除。",
                    relative_path="教师专用/教研考试/旧资料.md",
                ),
            ],
        )
        (kb_dir / "manifest.json").write_text("{}", encoding="utf-8")

        with patch.multiple(
            build_kb,
            KB_DIR=kb_dir,
            KB_FILE=kb_file,
            IMPORTED_KB_DIR=imports_dir,
        ):
            build_kb.merge_imports_only()

        self.assertEqual([row["id"] for row in read_jsonl(kb_file)], ["public"])

    def test_private_builder_scans_only_teacher_exam_directory(self) -> None:
        project_root = self.root / "project"
        materials = project_root / "教学素材"
        private_dir = materials / "教师专用" / "教研考试"
        private_dir.mkdir(parents=True)
        (materials / "学生公开资料.md").write_text(
            "学生公开资料包含公开练习题，不能被误认为教师私有命题资料。",
            encoding="utf-8",
        )
        private_phrase = (
            "教师命题蓝图包括课程目标权重、章节覆盖比例、试题难度分布、"
            "标准答案、评分细则和复核注意事项，仅供任课教师内部使用。"
        )
        (private_dir / "命题蓝图.md").write_text(private_phrase, encoding="utf-8")
        output = project_root / "agnet" / "knowledge_base" / "private" / "teacher_exam.jsonl"
        manifest_file = output.with_name("teacher_exam.manifest.json")

        with patch.multiple(
            build_teacher_exam_kb,
            PROJECT_ROOT=project_root,
            MATERIALS_DIR=materials,
            TEACHER_EXAM_MATERIALS_DIR=private_dir,
            TEACHER_EXAM_KB_FILE=output,
            TEACHER_EXAM_KB_MANIFEST_FILE=manifest_file,
        ):
            manifest = build_teacher_exam_kb.build()

        rows = read_jsonl(output)
        self.assertEqual(len(rows), 1)
        self.assertIn(private_phrase, rows[0]["text"])
        self.assertEqual(
            rows[0]["relative_path"], "教师专用/教研考试/命题蓝图.md"
        )
        self.assertNotIn("学生公开资料", json.dumps(rows, ensure_ascii=False))
        self.assertTrue(manifest["private"])
        self.assertEqual(manifest["files_scanned"], 1)
        self.assertEqual(manifest["chunks"], 1)
        self.assertEqual(
            json.loads(manifest_file.read_text(encoding="utf-8")), manifest
        )

    def test_private_builder_and_retriever_degrade_safely_when_sources_are_missing(self) -> None:
        project_root = self.root / "empty-project"
        materials = project_root / "教学素材"
        missing_private_dir = materials / "教师专用" / "教研考试"
        output = project_root / "agnet" / "knowledge_base" / "private" / "teacher_exam.jsonl"
        manifest_file = output.with_name("teacher_exam.manifest.json")

        with patch.multiple(
            build_teacher_exam_kb,
            PROJECT_ROOT=project_root,
            MATERIALS_DIR=materials,
            TEACHER_EXAM_MATERIALS_DIR=missing_private_dir,
            TEACHER_EXAM_KB_FILE=output,
            TEACHER_EXAM_KB_MANIFEST_FILE=manifest_file,
        ):
            manifest = build_teacher_exam_kb.build()

        self.assertTrue(output.is_file())
        self.assertEqual(output.read_text(encoding="utf-8"), "")
        self.assertEqual(manifest["files_scanned"], 0)
        self.assertEqual(manifest["chunks"], 0)
        self.assertEqual(KnowledgeBase(output).search("试题"), [])


if __name__ == "__main__":
    unittest.main()
