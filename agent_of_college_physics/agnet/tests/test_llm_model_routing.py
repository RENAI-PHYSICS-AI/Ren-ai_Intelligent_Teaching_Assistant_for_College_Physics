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


SETTINGS = {
    "PHYSICS_BASE_URL": "http://127.0.0.1:1235/v1",
    "PHYSICS_MODEL": "mimo-vl-local-prod",
    "PHYSICS_VISION_MODEL": "mimo-vl-local-prod",
    "PHYSICS_CHAT_NO_THINK_SUFFIX": "/no_think",
    "PHYSICS_VISION_NO_THINK_SUFFIX": "/no_think",
    "PHYSICS_MAX_OUTPUT_TOKENS": "4096",
    "PHYSICS_VISION_MAX_OUTPUT_TOKENS": "2048",
    "PHYSICS_VISION_TIMEOUT_SECONDS": "360",
}


class FakeResponse:
    def __init__(self, *, payload=None, lines=None, content_type="application/json", status=200):
        self._payload = payload or {}
        self._lines = lines or []
        self.headers = {"content-type": content_type}
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def close(self):
        return None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=False):
        del decode_unicode
        return iter(self._lines)


def setting_value(name, default=""):
    return SETTINGS.get(name, default)


def stream_response(text="最终答案", finish_reason="stop"):
    event = json.dumps({"choices": [{"delta": {"content": text}}]}, ensure_ascii=False)
    finish = json.dumps({
        "choices": [{"delta": {}, "finish_reason": finish_reason}],
    })
    return FakeResponse(
        lines=[
            f"data: {event}".encode(),
            f"data: {finish}".encode(),
            b"data: [DONE]",
        ],
        content_type="text/event-stream",
    )


def json_response(text, finish_reason="stop"):
    return FakeResponse(payload={
        "choices": [{
            "message": {"content": text},
            "finish_reason": finish_reason,
        }],
    })


class ModelRoutingTests(unittest.TestCase):
    def test_text_question_goes_directly_to_mimo(self):
        calls = []

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return stream_response()

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer("什么是动量？", "教材片段", []))

        self.assertEqual(result, "最终答案")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "mimo-vl-local-prod")
        self.assertEqual(calls[0]["max_tokens"], 4096)
        self.assertTrue(calls[0]["messages"][-1]["content"].endswith("/no_think"))
        self.assertNotIn("enable_search", calls[0])

    def test_web_results_are_passed_as_untrusted_text(self):
        calls = []

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return stream_response()

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer(
                "最新进展？", "教材片段", [], web_context="[联网1] 官方结果"
            ))

        self.assertEqual(result, "最终答案")
        content = calls[0]["messages"][-1]["content"]
        self.assertIn("外部不可信参考文本", content)
        self.assertIn("[联网1] 官方结果", content)

    def test_images_are_recognized_then_passed_as_text_to_same_mimo(self):
        calls = []

        def fake_post(_url, **kwargs):
            payload = kwargs["json"]
            calls.append(payload)
            if payload.get("stream") is False:
                return FakeResponse(payload={
                    "choices": [{"message": {"content": "图中可见质量 m=2 kg，速度 v=3 m/s。"}}]
                })
            return stream_response("由MiMo组织的答案")

        images = [{"data": b"fake-png", "mime": "image/png", "name": "题目.png"}]
        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer("请解答图片中的题目", "教材片段", [], images))

        self.assertEqual(result, "由MiMo组织的答案")
        self.assertEqual(
            [call["model"] for call in calls],
            ["mimo-vl-local-prod", "mimo-vl-local-prod"],
        )
        vision_content = calls[0]["messages"][-1]["content"]
        self.assertTrue(any(item.get("type") == "image_url" for item in vision_content))
        self.assertEqual(vision_content[-1], {"type": "text", "text": "/no_think"})
        chat_content = calls[1]["messages"][-1]["content"]
        self.assertIsInstance(chat_content, str)
        self.assertIn("图中可见质量 m=2 kg", chat_content)
        self.assertNotIn("image_url", chat_content)
        self.assertTrue(chat_content.endswith("/no_think"))

    def test_empty_vision_result_stops_before_chat_model(self):
        calls = []

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return FakeResponse(payload={"choices": [{"message": {"content": ""}}]})

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
            self.assertRaisesRegex(RuntimeError, "没有返回可用"),
        ):
            list(llm.stream_answer(
                "识别图片", "", [], [{"data": b"fake", "mime": "image/png"}]
            ))

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "mimo-vl-local-prod")

    def test_visualization_plan_uses_mimo_and_final_no_think_suffix(self):
        calls = []
        specification = {
            "kind": "function",
            "title": "简谐振动",
            "x_label": "t / s",
            "y_label": "x / m",
            "x_min": 0,
            "x_max": 6.28,
            "series": [{"name": "x(t)", "expression": "cos(2*x)"}],
        }

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return FakeResponse(payload={
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "function": {
                                "arguments": json.dumps(
                                    specification, ensure_ascii=False
                                ),
                            },
                        }],
                    },
                }],
            })

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = llm.plan_visualization(
                "请画出简谐振动曲线", "位移随时间按余弦规律变化。"
            )

        self.assertEqual(result, [specification])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "mimo-vl-local-prod")
        self.assertTrue(
            calls[0]["messages"][-1]["content"].endswith("/no_think")
        )
        self.assertEqual(calls[0]["reasoning_effort"], "none")

    def test_sse_length_continues_once_and_removes_exact_overlap(self):
        calls = []
        responses = [
            stream_response("代码：value = np.sin(theta", "length"),
            stream_response("np.sin(theta) + offset\n```", "stop"),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer("请给出演示代码", "教材片段", []))

        self.assertEqual(result, "代码：value = np.sin(theta) + offset\n```")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["temperature"], 0)
        self.assertEqual(calls[1]["messages"][-2], {
            "role": "assistant",
            "content": "代码：value = np.sin(theta",
        })
        self.assertTrue(
            calls[1]["messages"][-1]["content"].endswith("/no_think")
        )

    def test_second_sse_length_stops_with_explicit_notice(self):
        calls = []
        responses = [
            stream_response("第一段未完成。", "length"),
            stream_response("第二段仍未完成。", "length"),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer("详细说明", "教材片段", []))

        self.assertEqual(len(calls), 2)
        self.assertIn("回答再次达到输出上限", result)
        self.assertTrue(result.startswith("第一段未完成。第二段仍未完成。"))

    def test_non_sse_max_tokens_also_continues_once(self):
        calls = []
        responses = [
            json_response("推导到 x = cos(omega", "max_tokens"),
            json_response("cos(omega*t)。", "stop"),
        ]

        def fake_post(_url, **kwargs):
            calls.append(kwargs["json"])
            return responses.pop(0)

        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer("继续推导", "教材片段", []))

        self.assertEqual(result, "推导到 x = cos(omega*t)。")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
