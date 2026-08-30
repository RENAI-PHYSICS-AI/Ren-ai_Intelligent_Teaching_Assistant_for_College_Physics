from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import llm
import teacher_exam
from exam_blueprint import parse_exam_blueprint
from test_exam_blueprint import valid_blueprint_json


SETTINGS = {
    "PHYSICS_BASE_URL": "http://127.0.0.1:1235/v1",
    "PHYSICS_MODEL": "mimo-vl-local-prod",
    "PHYSICS_VISION_MODEL": "mimo-vl-local-prod",
    "PHYSICS_EXAM_BASE_URL": "http://127.0.0.1:1240/v1",
    "PHYSICS_EXAM_MODEL": "deepseek-v4-flash",
    "PHYSICS_CHAT_NO_THINK_SUFFIX": "/no_think",
    "PHYSICS_VISION_NO_THINK_SUFFIX": "/no_think",
    "PHYSICS_MAX_OUTPUT_TOKENS": "4096",
    "PHYSICS_VISION_MAX_OUTPUT_TOKENS": "2048",
    "PHYSICS_VISION_TIMEOUT_SECONDS": "360",
}


class FakeResponse:
    def __init__(self, *, payload=None, lines=None, content_type="application/json"):
        self._payload = payload or {}
        self._lines = lines or []
        self.headers = {"content-type": content_type}
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def close(self):
        return None

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=False):
        del decode_unicode
        return iter(self._lines)


def setting_value(name, default=""):
    return SETTINGS.get(name, default)


def stream_response(text="完成"):
    event = json.dumps({"choices": [{"delta": {"content": text}}]}, ensure_ascii=False)
    finish = json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]})
    return FakeResponse(
        lines=[f"data: {event}".encode(), f"data: {finish}".encode(), b"data: [DONE]"],
        content_type="text/event-stream",
    )


def json_response(text="已完成。"):
    return FakeResponse(payload={
        "choices": [{
            "message": {"content": text},
            "finish_reason": "stop",
        }],
    })


VALID_EXAM_OUTPUT = (
    "已完成。\n```latex\n% main.tex\n"
    "\\documentclass{ctexart}\n\\begin{document}题面\\end{document}\n```\n"
    "```latex\n% answer.tex\n"
    "\\documentclass{ctexart}\n\\begin{document}答案\\end{document}\n```"
)


class TeacherExamDomainTests(unittest.TestCase):
    def test_only_active_verified_teacher_is_allowed(self):
        account = {
            "role": "teacher",
            "identity_type": "teacher",
            "institutional_id": "T001",
            "identity_verified": 1,
            "is_active": 1,
        }
        self.assertTrue(teacher_exam.is_verified_teacher(account))
        for field, value in (
            ("role", "student"),
            ("identity_type", "student"),
            ("institutional_id", ""),
            ("identity_verified", 0),
            ("is_active", "0"),
        ):
            denied = dict(account)
            denied[field] = value
            self.assertFalse(teacher_exam.is_verified_teacher(denied), field)

    def test_portal_and_query_parameters_are_allow_listed(self):
        self.assertEqual(
            teacher_exam.normalize_teacher_exam_portal("teacher-exam"),
            teacher_exam.TEACHER_EXAM_PORTAL,
        )
        self.assertEqual(
            teacher_exam.normalize_teacher_exam_portal("teaching-exam"),
            "teaching-exam",
        )
        self.assertEqual(teacher_exam.normalize_teacher_exam_portal("admin"), "")
        sanitized = teacher_exam.sanitize_exam_query_params({
            "portal": "teacher-exam",
            "chapter": "第3章 刚体的定轴转动",
            "topics": ["转动惯量", "不应采用第二值"],
            "redirect": "https://attacker.invalid/",
            "token": "secret",
        })
        self.assertEqual(sanitized, {
            "portal": "teaching-exam",
            "chapter": "第3章 刚体的定轴转动",
            "topics": "转动惯量",
        })

    def test_compatibility_portal_exports_resolve_internal_modes(self):
        account = {
            "role": "teacher",
            "identity_type": "teacher",
            "institutional_id": "T001",
            "identity_verified": 1,
            "is_active": 1,
        }
        self.assertEqual(teacher_exam.PORTAL_ASSISTANT, "assistant")
        self.assertEqual(teacher_exam.PORTAL_TEACHING_EXAM, "teaching_exam")
        self.assertTrue(all(isinstance(item, str) for item in teacher_exam.EXAM_QUICK_TASKS))
        self.assertEqual(
            teacher_exam.portal_query_value(teacher_exam.PORTAL_TEACHING_EXAM),
            "teaching-exam",
        )
        self.assertEqual(teacher_exam.portal_query_value("teacher-exam"), "teaching-exam")
        self.assertEqual(
            teacher_exam.resolve_teacher_portal(account, "teaching-exam", None),
            teacher_exam.PORTAL_TEACHING_EXAM,
        )
        self.assertEqual(
            teacher_exam.resolve_teacher_portal(account, "", "assistant"),
            teacher_exam.PORTAL_ASSISTANT,
        )
        self.assertIsNone(
            teacher_exam.resolve_teacher_portal(account, "invalid", "assistant")
        )
        self.assertIsNone(
            teacher_exam.resolve_teacher_portal({**account, "identity_verified": 0}, "assistant", None)
        )

    def test_retrieval_query_preserves_scope_and_deduplicates_terms(self):
        query = teacher_exam.exam_retrieval_query(
            "生成两道可验算的计算题",
            chapter="第3章 刚体的定轴转动",
            topics="转动惯量、角动量、转动惯量",
            question_types=["计算题", "实验题"],
        )
        self.assertIn("课程章节：第3章 刚体的定轴转动", query)
        self.assertIn("目标知识点：转动惯量 角动量", query)
        self.assertIn("题型：计算题 实验题", query)
        self.assertTrue(query.endswith("教师命题任务：生成两道可验算的计算题"))
        self.assertGreaterEqual(len(teacher_exam.QUICK_EXAM_TASKS), 4)
        self.assertGreaterEqual(len(teacher_exam.EXAM_DESIGN_STANDARDS), 4)

    def test_request_classifier_separates_new_exam_from_supplied_material(self):
        self.assertEqual(
            teacher_exam.classify_teacher_exam_request(
                "请生成2025-2026学年第二学期大学物理1补考试卷"
            ),
            teacher_exam.EXAM_REQUEST_FULL_GENERATION,
        )
        self.assertEqual(
            teacher_exam.classify_teacher_exam_request(
                "做一份2025-2026学年第二学期大学物理1期末试卷"
            ),
            teacher_exam.EXAM_REQUEST_FULL_GENERATION,
        )
        self.assertEqual(
            teacher_exam.classify_teacher_exam_request(
                "做一份答案", has_attachments=True
            ),
            teacher_exam.EXAM_REQUEST_SOURCE_MATERIAL,
        )
        self.assertEqual(
            teacher_exam.classify_teacher_exam_request(
                "请为这份大学物理1试卷生成逐题答案和评分标准"
            ),
            teacher_exam.EXAM_REQUEST_SOURCE_MATERIAL,
        )
        self.assertEqual(
            teacher_exam.classify_teacher_exam_request("分析本学期试题难度"),
            teacher_exam.EXAM_REQUEST_SOURCE_MATERIAL,
        )
        self.assertEqual(
            teacher_exam.classify_teacher_exam_request("说明命题时如何控制难度"),
            teacher_exam.EXAM_REQUEST_GENERAL,
        )

    def test_source_material_answer_request_is_narrow(self):
        for task in (
            "做一份答案",
            "请为这份试卷生成逐题参考答案",
            "解答这份试卷",
            "解析上传的试题",
            "生成评分标准",
            "只需评分细则",
            "参考答案和评分细则",
        ):
            with self.subTest(task=task):
                self.assertTrue(teacher_exam.source_material_answer_requested(task))

        for task in (
            "审核这份试卷",
            "分析试卷难度和章节分布",
            "检查现有答案是否正确",
            "审核答案并分析难度",
            "不要答案，只审核试卷",
            "请生成2025-2026学年第二学期大学物理1期末试卷并附参考答案",
        ):
            with self.subTest(task=task):
                self.assertFalse(teacher_exam.source_material_answer_requested(task))

    def test_source_material_artifact_request_recognizes_delivery_followups(self):
        for task in (
            "编译",
            "请编译成 PDF",
            "给我生成PDF",
            "转成pdf",
            "导出 PDF",
            "把刚才的答案编译成 PDF",
            "请将上述 LaTeX 代码转为 PDF 文件",
            "提供现有答案的 TeX/PDF 文件",
        ):
            with self.subTest(task=task):
                self.assertTrue(teacher_exam.source_material_artifact_requested(task))
                self.assertEqual(
                    teacher_exam.classify_teacher_exam_request(task),
                    teacher_exam.EXAM_REQUEST_SOURCE_MATERIAL,
                )

    def test_source_material_artifact_request_excludes_questions_and_new_exams(self):
        for task in (
            "如何编译 TeX？",
            "怎么把 LaTeX 转成 PDF？",
            "为什么 PDF 编译失败？",
            "请解释 TeX 编译错误的原因",
            "PDF 文件是什么？",
            "请审核这份 PDF 中的题目",
            "请生成一份关于 PDF 格式的说明文档",
            "请生成2026-2027学年第一学期大学物理1期末试卷并导出PDF",
        ):
            with self.subTest(task=task):
                self.assertFalse(teacher_exam.source_material_artifact_requested(task))

        self.assertEqual(
            teacher_exam.classify_teacher_exam_request(
                "请生成2026-2027学年第一学期大学物理1期末试卷并导出PDF"
            ),
            teacher_exam.EXAM_REQUEST_FULL_GENERATION,
        )

    def test_artifact_revision_is_not_a_direct_file_reuse_request(self):
        for task in (
            "把这份答案修改后再编译成 PDF",
            "修正上述 LaTeX 并导出 PDF",
            "补充评分细则，然后提供 TeX/PDF 文件",
            "重新排版刚才的答案并生成 PDF",
        ):
            with self.subTest(task=task):
                self.assertTrue(
                    teacher_exam.source_material_artifact_requested(task)
                )
                self.assertTrue(
                    teacher_exam.source_material_artifact_revision_requested(task)
                )
                self.assertEqual(
                    teacher_exam.classify_teacher_exam_request(task),
                    teacher_exam.EXAM_REQUEST_SOURCE_MATERIAL,
                )

        for task in ("编译成 PDF", "导出上述答案的 TeX/PDF 文件"):
            with self.subTest(task=task):
                self.assertFalse(
                    teacher_exam.source_material_artifact_revision_requested(task)
                )


class TeacherExamModelTests(unittest.TestCase):
    def test_teaching_exam_uses_teacher_prompt_and_exam_model(self):
        calls = []

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return stream_response(valid_blueprint_json())

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                "请生成2025-2026学年第二学期大学物理1补考试卷，考试日期2026年3月20日",
                "教材片段",
                [],
                agent_mode="teaching_exam",
            ))

        self.assertEqual(parse_exam_blueprint(result).kind, "exam")
        self.assertEqual(calls[0]["model"], SETTINGS["PHYSICS_EXAM_MODEL"])
        self.assertIn("结构化安全输出模块", calls[0]["messages"][0]["content"])
        self.assertTrue(calls[0]["stream"])
        self.assertEqual(calls[0]["response_format"]["type"], "json_schema")
        current = calls[0]["messages"][-1]["content"]
        self.assertIn(
            "教师命题任务：请生成2025-2026学年第二学期大学物理1补考试卷，考试日期2026年3月20日",
            current,
        )
        self.assertNotIn("学生问题：", current)
        for requirement in ("依据知识库", "可以求解", "验算", "评分标准", "不得机械照抄", "虚构"):
            self.assertIn(requirement, llm.TEACHER_EXAM_SYSTEM_PROMPT)

    def test_teaching_exam_blocks_encoded_stream_without_whole_exam_retry(self):
        calls = []

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return stream_response("!#%&()*+,-./:;<=>?@[]^_`{|}~" * 20)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
            self.assertRaisesRegex(
                llm.ExamGenerationError,
                "教研考试生成失败.*未自动重新生成整卷",
            ) as raised,
        ):
            "".join(llm.stream_answer(
                "请生成2025-2026学年第二学期大学物理1补考试卷",
                "[资料1] 噪声内容",
                [],
                agent_mode="teaching_exam",
            ))

        self.assertNotIn("!#%&", str(raised.exception))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["max_tokens"], 32768)
        self.assertEqual(calls[0]["response_format"]["type"], "json_schema")
        self.assertTrue(calls[0]["stream"])

    def test_default_agent_mode_remains_student_assistant(self):
        calls = []

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return stream_response()

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            self.assertEqual("".join(llm.stream_answer("什么是动量？", "教材片段", [])), "完成")

        self.assertEqual(calls[0]["messages"][0]["content"], llm.SYSTEM_PROMPT)
        self.assertIn("学生问题：什么是动量？", calls[0]["messages"][-1]["content"])

    def test_supplied_exam_answer_uses_teacher_chat_not_exam_blueprint(self):
        calls = []

        def fake_post(_url, **kwargs):
            payload = kwargs["json"]
            calls.append(payload)
            if payload.get("stream") is False:
                return FakeResponse(payload={
                    "choices": [{"message": {"content": "附件中是一份大学物理试卷。"}}]
                })
            return stream_response("已依据上传试卷逐题生成答案。")

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                "做一份答案",
                "教材片段",
                [],
                [{"data": b"exam", "mime": "application/pdf"}],
                agent_mode="teaching_exam",
            ))

        self.assertEqual(result, "已依据上传试卷逐题生成答案。")
        self.assertEqual([call["model"] for call in calls], [
            SETTINGS["PHYSICS_VISION_MODEL"], SETTINGS["PHYSICS_EXAM_MODEL"],
        ])
        vision_items = calls[0]["messages"][-1]["content"]
        self.assertIn("教师命题任务：做一份答案", vision_items[0]["text"])
        self.assertIn("教师命题任务：做一份答案", calls[1]["messages"][-1]["content"])
        self.assertNotIn("response_format", calls[1])
        self.assertEqual(calls[1]["messages"][0]["content"], llm.TEACHER_EXAM_SYSTEM_PROMPT)

    def test_context_budget_uses_selected_system_prompt(self):
        history = [
            {"role": "user", "content": "上一题"},
            {"role": "assistant", "content": "上一题答案"},
        ]
        with patch.object(llm, "setting", side_effect=lambda name, default="": {
            "PHYSICS_CONTEXT_WINDOW": "4096",
            "PHYSICS_MAX_OUTPUT_TOKENS": "512",
            "PHYSICS_HISTORY_MAX_MESSAGES": "4",
        }.get(name, default)):
            self.assertEqual(len(llm._history_for_context(history, "当前任务", "短提示")), 2)
            self.assertEqual(llm._history_for_context(history, "当前任务", "长" * 4000), [])

    def test_exam_context_budget_accepts_full_one_megatoken_setting(self):
        history = [
            {"role": "user", "content": "教师历史任务" + "甲" * 300000},
            {"role": "assistant", "content": "历史答案"},
        ]
        with patch.object(llm, "setting", side_effect=lambda name, default="": {
            "PHYSICS_EXAM_CONTEXT_WINDOW": "1048576",
            "PHYSICS_HISTORY_MAX_MESSAGES": "4",
        }.get(name, default)):
            selected = llm._history_for_context(
                history,
                "当前命题任务",
                llm.TEACHER_EXAM_SYSTEM_PROMPT,
                output_reserve=32768,
                context_window_setting="PHYSICS_EXAM_CONTEXT_WINDOW",
            )
        self.assertEqual(len(selected), 2)


if __name__ == "__main__":
    unittest.main()
