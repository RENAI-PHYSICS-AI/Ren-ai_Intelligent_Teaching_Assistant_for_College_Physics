from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_DIR = Path(__file__).resolve().parent
APP_DIR = TEST_DIR.parent
for candidate in (APP_DIR, TEST_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import llm
from exam_blueprint import (
    blueprint_to_dict,
    canonical_blueprint_json,
    parse_exam_blueprint,
)
from test_exam_blueprint import (
    combined_targeted_repair_data,
    complete_targeted_repairs,
    valid_blueprint_data,
    valid_blueprint_json,
)


EXAM_REQUEST = "生成2025—2026学年第二学期大学物理1补考试卷，考试日期2026年8月"

SETTINGS = {
    "PHYSICS_BASE_URL": "http://vision-host:1234/v1",
    "PHYSICS_API_KEY": "vision-key",
    "PHYSICS_MODEL": "mimo-chat",
    "PHYSICS_VISION_MODEL": "qwen-vl-30b",
    "PHYSICS_EXAM_BASE_URL": "http://exam-host:1234/v1",
    "PHYSICS_EXAM_API_KEY": "exam-key",
    "PHYSICS_EXAM_MODEL": "deepseek-v4-flash",
    "PHYSICS_EXAM_CONTEXT_WINDOW": "65536",
    "PHYSICS_EXAM_MAX_OUTPUT_TOKENS": "32768",
    "PHYSICS_EXAM_TIMEOUT_SECONDS": "900",
    "PHYSICS_CONTEXT_WINDOW": "4096",
    "PHYSICS_HISTORY_MAX_MESSAGES": "8",
    "PHYSICS_CHAT_NO_THINK_SUFFIX": "/no_think",
    "PHYSICS_EXAM_NO_THINK_SUFFIX": "",
    "PHYSICS_VISION_NO_THINK_SUFFIX": "",
}


class FakeResponse:
    def __init__(self, *, payload=None, lines=None, content_type="application/json", status=200):
        self._payload = payload or {}
        self._lines = lines or []
        self.headers = {"content-type": content_type}
        self.status_code = status
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise llm.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=False):
        del decode_unicode
        return iter(self._lines)


def setting_value(name, default=""):
    return SETTINGS.get(name, default)


def stream_response(text: str, finish_reason: str = "stop", *, metadata: bool = False):
    event = json.dumps({
        "choices": [{
            "delta": {"reasoning_content": "内部推理绝不能显示", "content": text},
            "finish_reason": None,
        }],
    }, ensure_ascii=False).encode("utf-8")
    finish = json.dumps({
        "choices": [{"delta": {"reasoning_content": "仍不显示"}, "finish_reason": finish_reason}],
    }, ensure_ascii=False).encode("utf-8")
    lines = [b"event: message", b": proxy keepalive", b"keepalive", b"id: 42"] if metadata else []
    lines.extend([b"data: " + event, b"data: " + finish, b"data: [DONE]"])
    return FakeResponse(lines=lines, content_type="text/event-stream")


def chunked_stream_response(chunks: list[str], finish_reason: str = "stop"):
    lines = []
    for index, chunk in enumerate(chunks, 1):
        event = json.dumps({
            "choices": [{
                "delta": {"reasoning_content": f"内部推理{index}", "content": chunk},
                "finish_reason": None,
            }],
        }, ensure_ascii=False).encode("utf-8")
        lines.append(b"data: " + event)
    finish = json.dumps({
        "choices": [{"delta": {}, "finish_reason": finish_reason}],
    }, ensure_ascii=False).encode("utf-8")
    lines.extend([b"data: " + finish, b"data: [DONE]"])
    return FakeResponse(lines=lines, content_type="text/event-stream")


def json_response(text: str, finish_reason: str = "stop", status: int = 200):
    return FakeResponse(payload={
        "choices": [{
            "message": {"reasoning_content": "隐藏推理", "content": text},
            "finish_reason": finish_reason,
        }],
    }, status=status)


def blueprint_with_duplicate_options(*question_numbers: int) -> dict:
    data = valid_blueprint_data()
    for number in question_numbers:
        options = data["questions"][number - 1]["options"]
        options[3] = options[2] + "。"
    return data


def option_repair_response(data: dict, *question_numbers: int) -> dict:
    repairs = []
    for number in question_numbers:
        options = list(data["questions"][number - 1]["options"])
        options[3] = f"第{number}题独立且明确错误的干扰项"
        repairs.append({"number": number, "options": options})
    return {"repairs": repairs}


class StructuredExamFallbackTests(unittest.TestCase):
    def test_exam_stream_reports_counts_without_exposing_reasoning(self):
        progress = []
        result, finish_reason = llm._collect_exam_completion(
            stream_response("最终答案"),
            progress_callback=lambda reasoning, output: progress.append((reasoning, output)),
        )
        self.assertEqual(result, "最终答案")
        self.assertEqual(finish_reason, "stop")
        self.assertTrue(progress)
        self.assertEqual(progress[-1], (len("内部推理绝不能显示仍不显示"), len("最终答案")))

    def test_streamed_exam_reports_progress_before_completion(self):
        progress = []
        response = chunked_stream_response(["第一段", "第二段", "第三段"])
        with patch.object(llm.time, "monotonic", side_effect=[3, 6, 9, 12, 15]):
            result, finish_reason = llm._collect_exam_completion(
                response,
                progress_callback=lambda reasoning, output: progress.append((reasoning, output)),
            )

        self.assertEqual(result, "第一段第二段第三段")
        self.assertEqual(finish_reason, "stop")
        self.assertGreaterEqual(len(progress), 3)
        self.assertGreater(progress[-1][0], 0)
        self.assertEqual(progress[-1][1], len(result))
        self.assertLess(progress[0][1], progress[-1][1])

    def test_invalid_utf8_sse_is_rejected_without_replacement_characters(self):
        response = FakeResponse(
            lines=[b"data: \xff\xfe", b"data: [DONE]"],
            content_type="text/event-stream",
        )
        with self.assertRaisesRegex(llm._ExamResponseProtocolError, "UTF-8"):
            llm._collect_exam_completion(response)

    def test_exam_collection_enforces_absolute_deadline(self):
        response = chunked_stream_response(["仍在生成"])
        with (
            patch.object(llm.time, "monotonic", side_effect=[0.0, 2.0]),
            self.assertRaisesRegex(llm.ExamGenerationError, "总时间上限"),
        ):
            llm._collect_exam_completion(response, deadline_seconds=1.0)

    def test_exam_uses_one_structured_streaming_request(self):
        calls = []
        events = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return stream_response(valid_blueprint_json(), metadata=True)

        history = [
            {"role": "user", "content": "旧任务" + "甲" * 5000},
            {"role": "assistant", "content": "旧答案"},
        ]
        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
            patch.object(
                llm,
                "_collect_exam_completion",
                wraps=llm._collect_exam_completion,
            ) as collect_completion,
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST, "教师私有知识", history,
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        self.assertEqual(parse_exam_blueprint(result).kind, "exam")
        self.assertNotIn("内部推理", result)
        self.assertEqual(len(calls), 1)
        url, kwargs = calls[0]
        self.assertEqual(url, "http://exam-host:1234/v1/chat/completions")
        self.assertEqual(kwargs["json"]["model"], "deepseek-v4-flash")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer exam-key")
        self.assertGreater(kwargs["timeout"][0], 0)
        self.assertLessEqual(kwargs["timeout"][0], 15)
        self.assertGreater(kwargs["timeout"][1], 0)
        self.assertLessEqual(kwargs["timeout"][1], 900)
        self.assertTrue(kwargs["stream"])
        self.assertTrue(kwargs["json"]["stream"])
        self.assertEqual(kwargs["json"]["response_format"]["type"], "json_schema")
        deadline = collect_completion.call_args.kwargs["deadline_seconds"]
        self.assertGreater(deadline, 0)
        self.assertLessEqual(deadline, 900)
        self.assertTrue(any("旧任务" in str(item.get("content")) for item in kwargs["json"]["messages"]))
        self.assertNotIn("/no_think", kwargs["json"]["messages"][-1]["content"])
        self.assertIn("不要先生成 TeX", kwargs["json"]["messages"][-1]["content"])
        self.assertEqual(events, [])

    def test_duplicate_q6_uses_one_isolated_micro_repair_and_returns_canonical_exam(self):
        calls = []
        events = []
        original = blueprint_with_duplicate_options(6)
        repair = option_repair_response(original, 6)
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(repair, ensure_ascii=False)),
        ]

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return responses.pop(0)

        history = [
            {"role": "user", "content": "HISTORY_SECRET_MARKER"},
            {"role": "assistant", "content": "HISTORY_ASSISTANT_SECRET_MARKER"},
        ]
        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "CONTEXT_SECRET_MARKER",
                history,
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        self.assertEqual(len(calls), 2)
        blueprint = parse_exam_blueprint(result)
        self.assertEqual(result, canonical_blueprint_json(blueprint))
        result_data = blueprint_to_dict(blueprint)
        expected_q6 = dict(original["questions"][5])
        expected_q6["options"] = repair["repairs"][0]["options"]
        self.assertEqual(result_data["questions"][5], expected_q6)
        self.assertEqual(
            result_data["questions"][:5] + result_data["questions"][6:],
            original["questions"][:5] + original["questions"][6:],
        )
        self.assertEqual(events, [
            ("choice_option_repair_started", {"question_numbers": [6]}),
            ("choice_option_repair_completed", {"question_numbers": [6]}),
        ])

        full_payload = calls[0][1]["json"]
        repair_call = calls[1][1]
        repair_payload = repair_call["json"]
        full_messages = json.dumps(full_payload["messages"], ensure_ascii=False)
        repair_messages = json.dumps(repair_payload["messages"], ensure_ascii=False)
        self.assertIn("CONTEXT_SECRET_MARKER", full_messages)
        self.assertIn("HISTORY_SECRET_MARKER", full_messages)
        self.assertNotIn("CONTEXT_SECRET_MARKER", repair_messages)
        self.assertNotIn("HISTORY_SECRET_MARKER", repair_messages)
        self.assertNotIn("HISTORY_ASSISTANT_SECRET_MARKER", repair_messages)
        self.assertNotIn("SECRET_ANSWER_16", repair_messages)
        self.assertLess(len(repair_messages), 5000)
        self.assertLessEqual(repair_payload["max_tokens"], 4096)
        self.assertGreater(repair_call["timeout"][1], 0)
        self.assertLessEqual(repair_call["timeout"][1], 180)
        self.assertEqual(
            repair_payload["response_format"]["json_schema"]["name"],
            "tjrac_choice_option_repair",
        )

    def test_duplicate_option_with_accepted_4321_distribution_uses_one_micro_repair(self):
        calls = []
        original = blueprint_with_duplicate_options(6)
        answers = ("A", "A", "A", "B", "A", "B", "B", "C", "C", "D")
        for question, answer in zip(original["questions"][:10], answers):
            question["answer"] = answer
        repair = option_repair_response(original, 6)
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(repair, ensure_ascii=False)),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
            ))

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            calls[1]["json"]["response_format"]["json_schema"]["name"],
            "tjrac_choice_option_repair",
        )
        blueprint = parse_exam_blueprint(result)
        self.assertEqual(result, canonical_blueprint_json(blueprint))
        self.assertEqual(
            tuple(question.answer for question in blueprint.questions[:10]),
            answers,
        )

    def test_duplicate_option_with_unbalanced_answers_still_uses_one_micro_repair(self):
        calls = []
        events = []
        original = blueprint_with_duplicate_options(3)
        answers = ("A",) * 10
        for question, answer in zip(original["questions"][:10], answers):
            question["answer"] = answer
        repair = option_repair_response(original, 3)
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(repair, ensure_ascii=False)),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=(
                    lambda event, details: events.append((event, details))
                ),
            ))

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            calls[1]["json"]["response_format"]["json_schema"]["name"],
            "tjrac_choice_option_repair",
        )
        self.assertEqual(events, [
            ("choice_option_repair_started", {"question_numbers": [3]}),
            ("choice_option_repair_completed", {"question_numbers": [3]}),
        ])
        blueprint = parse_exam_blueprint(result)
        self.assertEqual(result, canonical_blueprint_json(blueprint))
        self.assertEqual(
            tuple(question.answer for question in blueprint.questions[:10]),
            answers,
        )

    def test_choice_and_fill_defects_use_one_isolated_targeted_repair(self):
        calls = []
        events = []
        original = combined_targeted_repair_data()
        repair = complete_targeted_repairs()
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(repair, ensure_ascii=False)),
        ]

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return responses.pop(0)

        history = [
            {"role": "user", "content": "TARGETED_HISTORY_SECRET"},
            {"role": "assistant", "content": "TARGETED_ASSISTANT_SECRET"},
        ]
        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "TARGETED_CONTEXT_SECRET",
                history,
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        self.assertEqual(len(calls), 2)
        blueprint = parse_exam_blueprint(result)
        self.assertEqual(result, canonical_blueprint_json(blueprint))
        result_data = blueprint_to_dict(blueprint)
        expected = json.loads(json.dumps(original, ensure_ascii=False))
        expected["questions"][4]["options"] = repair["choice_repairs"][0]["options"]
        expected["questions"][10]["stem"] = repair["fill_stem_repairs"][0]["stem"]
        self.assertEqual(result_data, expected)

        event_details = {
            "question_numbers": [5, 11],
            "choice_question_numbers": [5],
            "fill_question_numbers": [11],
        }
        self.assertEqual(events, [
            ("targeted_exam_repair_started", event_details),
            ("targeted_exam_repair_completed", event_details),
        ])

        full_messages = json.dumps(calls[0][1]["json"]["messages"], ensure_ascii=False)
        repair_call = calls[1][1]
        repair_payload = repair_call["json"]
        repair_messages = json.dumps(repair_payload["messages"], ensure_ascii=False)
        self.assertIn("TARGETED_CONTEXT_SECRET", full_messages)
        self.assertIn("TARGETED_HISTORY_SECRET", full_messages)
        self.assertNotIn("TARGETED_CONTEXT_SECRET", repair_messages)
        self.assertNotIn("TARGETED_HISTORY_SECRET", repair_messages)
        self.assertNotIn("TARGETED_ASSISTANT_SECRET", repair_messages)
        self.assertNotIn("SECRET_ANSWER_16", repair_messages)
        self.assertIn(original["questions"][4]["stem"], repair_messages)
        self.assertIn(original["questions"][10]["stem"], repair_messages)
        self.assertNotIn(original["questions"][0]["stem"], repair_messages)
        self.assertLess(len(repair_messages), 6500)
        self.assertLessEqual(repair_payload["max_tokens"], 4096)
        self.assertGreater(repair_call["timeout"][1], 0)
        self.assertLessEqual(repair_call["timeout"][1], 180)
        self.assertEqual(
            repair_payload["response_format"]["json_schema"]["name"],
            "tjrac_targeted_exam_repair",
        )
        schema = repair_payload["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema["required"], ["choice_repairs", "fill_stem_repairs"])
        self.assertEqual(schema["properties"]["choice_repairs"]["minItems"], 1)
        self.assertEqual(schema["properties"]["choice_repairs"]["maxItems"], 1)
        self.assertEqual(schema["properties"]["fill_stem_repairs"]["minItems"], 1)
        self.assertEqual(schema["properties"]["fill_stem_repairs"]["maxItems"], 1)

    def test_invalid_fill_marker_in_first_targeted_repair_gets_one_retry(self):
        calls = []
        events = []
        original = combined_targeted_repair_data()
        invalid_repair = complete_targeted_repairs()
        invalid_repair["fill_stem_repairs"][0]["stem"] = (
            "第一次修复仍然只有一个[[BLANK]]。"
        )
        valid_repair = complete_targeted_repairs()
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(invalid_repair, ensure_ascii=False)),
            stream_response(json.dumps(valid_repair, ensure_ascii=False)),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append(
                    (event, details)
                ),
            ))

        self.assertEqual(len(calls), 3)
        self.assertEqual(
            [event for event, _details in events],
            ["targeted_exam_repair_started", "targeted_exam_repair_completed"],
        )
        self.assertEqual(
            parse_exam_blueprint(result).questions[10].stem.count("[[BLANK]]"),
            2,
        )
        retry_messages = json.dumps(
            calls[2]["json"]["messages"], ensure_ascii=False
        )
        self.assertIn("必须且只能包含两个 [[BLANK]]", retry_messages)
        self.assertEqual(
            calls[2]["json"]["messages"][-2],
            {
                "role": "assistant",
                "content": json.dumps(invalid_repair, ensure_ascii=False),
            },
        )
        self.assertEqual(calls[1]["json"]["temperature"], 0)
        self.assertEqual(calls[2]["json"]["temperature"], 0.35)

    def test_invalid_fill_marker_three_times_fails_after_three_targeted_attempts(self):
        calls = []
        events = []
        original = combined_targeted_repair_data()
        invalid_repair = complete_targeted_repairs()
        invalid_repair["fill_stem_repairs"][0]["stem"] = (
            "两次修复都仍然只有一个[[BLANK]]。"
        )
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(invalid_repair, ensure_ascii=False)),
            stream_response(json.dumps(invalid_repair, ensure_ascii=False)),
            stream_response(json.dumps(invalid_repair, ensure_ascii=False)),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
            self.assertRaisesRegex(
                llm.ExamGenerationError,
                "已尝试 3 次受限的定点局部修复",
            ),
        ):
            "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append(
                    (event, details)
                ),
            ))

        self.assertEqual(len(calls), 4)
        self.assertEqual(
            [call["json"]["temperature"] for call in calls[1:]],
            [0, 0.35, 0.7],
        )
        self.assertEqual(
            [event for event, _details in events],
            ["targeted_exam_repair_started", "targeted_exam_repair_failed"],
        )

    def test_malformed_or_locked_targeted_repair_fails_without_third_call(self):
        original = combined_targeted_repair_data()
        locked_mutation = complete_targeted_repairs()
        locked_mutation["choice_repairs"][0]["options"][0] += "（被篡改）"
        retry_settings = {
            **SETTINGS,
            "PHYSICS_EXAM_GENERATION_ATTEMPTS": "2",
        }

        calls = []
        events = []
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(locked_mutation, ensure_ascii=False)),
        ]

        def fake_locked_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(
                llm,
                "setting",
                side_effect=lambda name, default="": retry_settings.get(name, default),
            ),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_locked_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        repaired = blueprint_to_dict(parse_exam_blueprint(result))
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [event for event, _details in events],
            ["targeted_exam_repair_started", "targeted_exam_repair_completed"],
        )
        self.assertEqual(
            repaired["questions"][4]["options"][0],
            original["questions"][4]["options"][0],
        )
        self.assertEqual(
            repaired["questions"][4]["options"][3],
            locked_mutation["choice_repairs"][0]["options"][3],
        )

        calls = []
        events = []
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response('{"choice_repairs":[]'),
        ]

        def fake_malformed_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(
                llm,
                "setting",
                side_effect=lambda name, default="": retry_settings.get(name, default),
            ),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_malformed_post),
            self.assertRaisesRegex(llm.ExamGenerationError, "定点局部修复"),
        ):
            "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [event for event, _details in events],
            ["targeted_exam_repair_started", "targeted_exam_repair_failed"],
        )
        self.assertEqual(events[-1][1], {
            "question_numbers": [5, 11],
            "choice_question_numbers": [5],
            "fill_question_numbers": [11],
        })

    def test_duplicate_with_later_validation_blocker_preserves_both_diagnostics(self):
        calls = []
        events = []
        invalid = blueprint_with_duplicate_options(5)
        invalid["questions"][15]["rubric"] = [
            {"points": 9, "criterion": "评分点总和不足十分"},
        ]
        one_attempt_settings = {
            **SETTINGS,
            "PHYSICS_EXAM_GENERATION_ATTEMPTS": "1",
        }

        def fake_post(_url, **kwargs):
            calls.append(kwargs)
            return stream_response(json.dumps(invalid, ensure_ascii=False))

        with (
            patch.object(
                llm,
                "setting",
                side_effect=lambda name, default="": one_attempt_settings.get(name, default),
            ),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
            self.assertRaises(llm.ExamGenerationError) as raised,
        ):
            "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        error_message = str(raised.exception)
        self.assertIn("第 5 题存在重复选项", error_message)
        self.assertIn("第 16 题", error_message)
        self.assertIn("评分点合计", error_message)
        self.assertEqual(len(calls), 1)
        self.assertEqual(events, [])

    def test_multiple_duplicate_questions_are_merged_into_one_repair_call(self):
        calls = []
        events = []
        original = blueprint_with_duplicate_options(6, 9)
        repair = option_repair_response(original, 6, 9)
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(repair, ensure_ascii=False)),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        self.assertEqual(len(calls), 2)
        blueprint = parse_exam_blueprint(result)
        repaired_questions = blueprint_to_dict(blueprint)["questions"]
        for repair_item in repair["repairs"]:
            self.assertEqual(
                repaired_questions[repair_item["number"] - 1]["options"],
                repair_item["options"],
            )
        repair_schema = calls[1]["json"]["response_format"]["json_schema"]["schema"]
        self.assertEqual(repair_schema["properties"]["repairs"]["minItems"], 2)
        self.assertEqual(repair_schema["properties"]["repairs"]["maxItems"], 2)
        self.assertEqual(events, [
            ("choice_option_repair_started", {"question_numbers": [6, 9]}),
            ("choice_option_repair_completed", {"question_numbers": [6, 9]}),
        ])

    def test_duplicate_left_by_first_micro_repair_gets_one_feedback_retry(self):
        calls = []
        events = []
        original = blueprint_with_duplicate_options(1)
        still_duplicate = {
            "repairs": [{
                "number": 1,
                "options": list(original["questions"][0]["options"]),
            }],
        }
        repaired = option_repair_response(original, 1)
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(still_duplicate, ensure_ascii=False)),
            stream_response(json.dumps(repaired, ensure_ascii=False)),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "RETRY_CONTEXT_SECRET",
                [{"role": "user", "content": "RETRY_HISTORY_SECRET"}],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append(
                    (event, details)
                ),
            ))

        self.assertEqual(len(calls), 3)
        self.assertEqual(events, [
            ("choice_option_repair_started", {"question_numbers": [1]}),
            ("choice_option_repair_completed", {"question_numbers": [1]}),
        ])
        blueprint = parse_exam_blueprint(result)
        self.assertEqual(result, canonical_blueprint_json(blueprint))
        retry_messages = json.dumps(
            calls[2]["json"]["messages"], ensure_ascii=False
        )
        self.assertIn("上一次局部修复仍未通过服务器校验", retry_messages)
        self.assertIn("第 1 题存在重复选项", retry_messages)
        self.assertEqual(
            calls[2]["json"]["messages"][-2],
            {
                "role": "assistant",
                "content": json.dumps(still_duplicate, ensure_ascii=False),
            },
        )
        self.assertNotIn("RETRY_CONTEXT_SECRET", retry_messages)
        self.assertNotIn("RETRY_HISTORY_SECRET", retry_messages)
        self.assertEqual(calls[1]["json"]["temperature"], 0)
        self.assertEqual(calls[2]["json"]["temperature"], 0.35)
        self.assertLessEqual(calls[1]["timeout"][1], 180)
        self.assertLessEqual(calls[2]["timeout"][1], 180)

    def test_duplicate_left_three_times_fails_after_three_local_attempts(self):
        calls = []
        events = []
        original = blueprint_with_duplicate_options(1)
        still_duplicate = {
            "repairs": [{
                "number": 1,
                "options": list(original["questions"][0]["options"]),
            }],
        }
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(still_duplicate, ensure_ascii=False)),
            stream_response(json.dumps(still_duplicate, ensure_ascii=False)),
            stream_response(json.dumps(still_duplicate, ensure_ascii=False)),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
            self.assertRaisesRegex(
                llm.ExamGenerationError,
                "已尝试 3 次受限的重复选项局部修复",
            ),
        ):
            "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append(
                    (event, details)
                ),
            ))

        self.assertEqual(len(calls), 4)
        self.assertEqual(
            [call["json"]["temperature"] for call in calls[1:]],
            [0, 0.35, 0.7],
        )
        self.assertEqual(events, [
            ("choice_option_repair_started", {"question_numbers": [1]}),
            ("choice_option_repair_failed", {"question_numbers": [1]}),
        ])

    def test_locked_or_malformed_micro_repair_fails_closed_without_third_call(self):
        original = blueprint_with_duplicate_options(6)
        locked_mutation = option_repair_response(original, 6)
        locked_mutation["repairs"][0]["options"][1] += "（被篡改）"
        retry_settings = {
            **SETTINGS,
            "PHYSICS_EXAM_GENERATION_ATTEMPTS": "2",
        }

        calls = []
        events = []
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response(json.dumps(locked_mutation, ensure_ascii=False)),
        ]

        def fake_locked_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(
                llm,
                "setting",
                side_effect=lambda name, default="": retry_settings.get(name, default),
            ),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_locked_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        repaired = blueprint_to_dict(parse_exam_blueprint(result))
        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [event for event, _details in events],
            ["choice_option_repair_started", "choice_option_repair_completed"],
        )
        self.assertEqual(
            repaired["questions"][5]["options"][1],
            original["questions"][5]["options"][1],
        )
        self.assertEqual(
            repaired["questions"][5]["options"][3],
            locked_mutation["repairs"][0]["options"][3],
        )

        calls = []
        events = []
        responses = [
            stream_response(json.dumps(original, ensure_ascii=False)),
            stream_response('{"repairs":['),
        ]

        def fake_malformed_post(_url, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

        with (
            patch.object(
                llm,
                "setting",
                side_effect=lambda name, default="": retry_settings.get(name, default),
            ),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_malformed_post),
            self.assertRaisesRegex(llm.ExamGenerationError, "局部修复"),
        ):
            "".join(llm.stream_answer(
                EXAM_REQUEST,
                "教师私有知识",
                [],
                agent_mode="teaching_exam",
                exam_event_callback=lambda event, details: events.append((event, details)),
            ))

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [event for event, _details in events],
            ["choice_option_repair_started", "choice_option_repair_failed"],
        )
        self.assertEqual(events[-1][1], {"question_numbers": [6]})

    def test_default_does_not_regenerate_whole_exam_after_invalid_result(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            return stream_response("%PDF-1.7\n<~encoded garbage~>", finish_reason="length")

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
                EXAM_REQUEST, "教师私有知识", [],
                agent_mode="teaching_exam",
            ))

        self.assertNotIn("%PDF", str(raised.exception))
        self.assertEqual(len(calls), 1)
        payload = calls[0][1]["json"]
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(payload["model"], "deepseek-v4-flash")

    def test_json_schema_compatibility_downgrades_only_after_400_or_422(self):
        calls = []
        responses = [
            json_response("", status=400),
            json_response("", status=422),
            stream_response(valid_blueprint_json()),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST, "教师私有知识", [],
                agent_mode="teaching_exam",
            ))

        self.assertEqual(parse_exam_blueprint(result).kind, "exam")
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call["stream"] for call in calls))
        self.assertEqual(calls[0]["response_format"]["type"], "json_schema")
        self.assertEqual(calls[1]["response_format"]["type"], "json_schema")
        self.assertNotIn("reasoning_effort", calls[1])
        self.assertEqual(calls[2]["response_format"], {"type": "json_object"})

    def test_configured_second_attempt_is_capped_and_uses_safe_error_prompt(self):
        calls = []
        responses = [
            stream_response("不是完整JSON", finish_reason="length"),
            stream_response(valid_blueprint_json()),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return responses.pop(0)

        retry_settings = {
            **SETTINGS,
            # Values above two must be capped to two complete generations.
            "PHYSICS_EXAM_GENERATION_ATTEMPTS": "99",
        }

        with (
            patch.object(llm, "setting", side_effect=lambda name, default="": retry_settings.get(name, default)),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST, "教师私有知识", [], agent_mode="teaching_exam"
            ))

        self.assertEqual(parse_exam_blueprint(result).kind, "exam")
        self.assertEqual(len(calls), 2)
        retry_prompt = calls[1]["messages"][-1]["content"]
        self.assertIn("未通过服务器校验", retry_prompt)
        self.assertNotIn("不是完整JSON", retry_prompt)

    def test_exam_image_uses_vision_route_then_exam_route(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs))
            if kwargs["json"]["model"] == "qwen-vl-30b":
                return json_response("图片中可见一道转动惯量题。")
            return stream_response(valid_blueprint_json())

        images = [{"data": b"png", "mime": "image/png"}]
        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                EXAM_REQUEST + "，并参考图片", "教师私有知识", [], images,
                agent_mode="teaching_exam",
            ))

        self.assertEqual(parse_exam_blueprint(result).kind, "exam")
        self.assertEqual([item[0] for item in calls], [
            "http://vision-host:1234/v1/chat/completions",
            "http://exam-host:1234/v1/chat/completions",
        ])
        self.assertEqual([item[1]["json"]["model"] for item in calls], [
            "qwen-vl-30b", "deepseek-v4-flash",
        ])
        self.assertEqual(calls[0][1]["headers"]["Authorization"], "Bearer vision-key")
        self.assertEqual(calls[1][1]["headers"]["Authorization"], "Bearer exam-key")
        self.assertFalse(calls[0][1]["json"]["stream"])
        self.assertTrue(calls[1][1]["json"]["stream"])
        self.assertEqual(calls[1][1]["json"]["response_format"]["type"], "json_schema")
        exam_prompt = calls[1][1]["json"]["messages"][-1]["content"]
        self.assertIn("图片中可见一道转动惯量题", exam_prompt)


if __name__ == "__main__":
    unittest.main()
