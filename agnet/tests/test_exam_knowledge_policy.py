from __future__ import annotations

import json
import runpy
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_kb
import build_teacher_exam_kb
import teacher_exam


EXPECTED_CHAPTERS = [
    "第1章 质点运动、时间、空间",
    "第2章 力、动量、能量",
    "第3章 刚体的定轴转动",
    "第4章 气体动理论",
    "第5章 热力学基础",
    "第6章 静电场",
    "第7章 恒定磁场",
    "第8章 电磁感应、电磁场",
    "第9章 振动学基础",
    "第10章 波动学基础",
    "第11章 波动光学",
    "第12章 波和粒子",
]


class ExamKnowledgePolicyTests(unittest.TestCase):
    def test_textbook_chapter_system_is_the_real_twelve_chapter_catalog(self) -> None:
        self.assertEqual(build_kb.CHAPTERS, EXPECTED_CHAPTERS)
        cases = {
            "质点的位移速度和加速度": EXPECTED_CHAPTERS[0],
            "牛顿定律、动量与机械能守恒": EXPECTED_CHAPTERS[1],
            "刚体转动惯量与力矩": EXPECTED_CHAPTERS[2],
            "卡诺循环和热力学第二定律": EXPECTED_CHAPTERS[4],
            "洛伦兹力和霍尔效应": EXPECTED_CHAPTERS[6],
            "法拉第电磁感应与楞次定律": EXPECTED_CHAPTERS[7],
            "简谐振动和受迫共振": EXPECTED_CHAPTERS[8],
            "声波驻波与多普勒效应": EXPECTED_CHAPTERS[9],
            "光的干涉衍射和偏振": EXPECTED_CHAPTERS[10],
            "光电效应和德布罗意波": EXPECTED_CHAPTERS[11],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(build_kb.classify(text), expected)

    def test_standard_template_and_policy_are_mandatory_teacher_context(self) -> None:
        # Deployment supplies these private files; a clean checkout must test
        # their configured resolution without requiring real exam materials.
        with tempfile.TemporaryDirectory() as temporary:
            exam_root = Path(temporary) / "restricted-exams"
            fixtures = {
                "TEACHER_EXAM_TEMPLATE_FILE": (
                    teacher_exam.DEFAULT_EXAM_TEMPLATE_RELATIVE_PATH,
                    r"\documentclass{article}\begin{document}Synthetic exam\end{document}",
                ),
                "TEACHER_EXAM_GUIDE_FILE": (
                    teacher_exam.MANDATORY_EXAM_GUIDE_RELATIVE_PATH,
                    "合成命题规范：选择题30分、填空题20分、计算题50分。",
                ),
            }
            expected_paths = {}
            for key, (relative, content) in fixtures.items():
                path = exam_root / Path(relative).relative_to("考试素材")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                expected_paths[key] = path
            with patch.dict(
                "os.environ", {"PHYSICS_EXAM_MATERIALS_DIR": str(exam_root)}
            ):
                configured = runpy.run_path(str(APP_DIR / "config.py"))
            self.assertEqual(configured["EXAM_MATERIALS_DIR"], exam_root)
            self.assertIn(exam_root, configured["TEACHER_EXAM_SOURCE_DIRS"])
            for key, path in expected_paths.items():
                with self.subTest(setting=key):
                    self.assertEqual(configured[key], path)
                    self.assertEqual(
                        configured[key].read_text(encoding="utf-8"), fixtures[key][1]
                    )
        self.assertIn("25262大物1补考/main.tex", teacher_exam.DEFAULT_EXAM_TEMPLATE_RELATIVE_PATH)
        self.assertIn(
            "25262大物1补考/answer.tex",
            teacher_exam.DEFAULT_ANSWER_TEMPLATE_RELATIVE_PATH,
        )
        self.assertIn("30分", teacher_exam.MANDATORY_EXAM_POLICY_CONTEXT)
        self.assertIn("大学物理B", teacher_exam.MANDATORY_EXAM_POLICY_CONTEXT)
        self.assertIn("独立的2pt黑色外框", teacher_exam.MANDATORY_EXAM_POLICY_CONTEXT)
        self.assertIn("答题空间", teacher_exam.MANDATORY_EXAM_POLICY_CONTEXT)
        self.assertIn("A4单栏", teacher_exam.MANDATORY_EXAM_POLICY_CONTEXT)
        self.assertIn("题号/答案横表", teacher_exam.MANDATORY_EXAM_POLICY_CONTEXT)

    def test_private_builder_indexes_exam_root_tex_policy_and_safe_zip_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repo"
            project = repository / "agent_of_college_physics"
            exam = repository / "考试素材"
            teacher = project / "教学素材" / "教师专用" / "教研考试"
            exam.mkdir(parents=True)
            teacher.mkdir(parents=True)
            guide = exam / "大学物理课程章节与组卷分值规范.md"
            guide.write_text("大学物理1默认章节分值与命题规范，仅供教师组卷审核使用。", encoding="utf-8")
            template = exam / "试卷" / "2025-2026-2" / "25262大物1补考" / "main.tex"
            template.parent.mkdir(parents=True)
            template.write_text("\\documentclass{article} 标准试卷模板：单选、填空、计算题，总分一百分。", encoding="utf-8")
            answer = template.with_name("answer.tex")
            answer.write_text(
                "\\documentclass{article} 标准答案模板：客观题答案横表，计算题分步给分，逐题核对量纲。",
                encoding="utf-8",
            )
            archive = exam / "题库.zip"
            with zipfile.ZipFile(archive, "w") as handle:
                handle.writestr(
                    "内部题库.md",
                    "清华题库内部大学物理计算题与参考解题方法，包含条件检查、量纲核对、"
                    "分步评分和答案复核要求，仅供教师在教研考试模式检索。",
                )
            output = project / "agnet" / "knowledge_base" / "private" / "teacher_exam.jsonl"
            manifest_file = output.with_name("teacher_exam.manifest.json")

            with patch.multiple(
                build_teacher_exam_kb,
                PROJECT_ROOT=project,
                MATERIALS_DIR=project / "教学素材",
                EXAM_MATERIALS_DIR=exam,
                TEACHER_EXAM_MATERIALS_DIR=teacher,
                TEACHER_EXAM_GUIDE_FILE=guide,
                TEACHER_EXAM_TEMPLATE_FILE=template,
                TEACHER_EXAM_KB_FILE=output,
                TEACHER_EXAM_KB_MANIFEST_FILE=manifest_file,
            ):
                manifest = build_teacher_exam_kb.build()

            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            serialized = json.dumps(rows, ensure_ascii=False)
            self.assertIn("标准试卷模板", serialized)
            self.assertIn("清华题库内部", serialized)
            self.assertTrue(all(row["access_scope"] == "teacher_exam" for row in rows))
            self.assertTrue(all(row["visibility"] == "verified_teacher" for row in rows))
            self.assertTrue(any(row["document_role"] == "mandatory_policy" for row in rows))
            self.assertTrue(any(row["template_standard"] for row in rows))
            self.assertTrue(any(
                row["document_role"] == "answer" and "标准答案模板" in row["text"]
                for row in rows
            ))
            self.assertEqual(manifest["standard_template_sha256"], build_teacher_exam_kb._source_hash(template))
            self.assertNotIn("password", serialized.lower())
            self.assertNotIn("password", json.dumps(manifest, ensure_ascii=False).lower())

    def test_source_passwords_are_automatic_and_never_needed_in_cli(self) -> None:
        with patch.dict(
            "os.environ",
            {"PHYSICS_EXAM_SOURCE_PASSWORDS": "first,second", "PHYSICS_PDF_PASSWORDS": "second;third"},
            clear=False,
        ):
            self.assertEqual(build_teacher_exam_kb._passwords(), ("first", "second", "third"))

    def test_source_passwords_are_not_embedded_in_source(self) -> None:
        with patch.dict(
            "os.environ",
            {"PHYSICS_EXAM_SOURCE_PASSWORDS": "", "PHYSICS_PDF_PASSWORDS": ""},
            clear=False,
        ), patch.object(build_teacher_exam_kb, "setting", return_value=""):
            self.assertEqual(build_teacher_exam_kb._passwords(), ())


if __name__ == "__main__":
    unittest.main()
