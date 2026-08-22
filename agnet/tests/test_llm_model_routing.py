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
    "PHYSICS_MODEL": "glm47-local-prod",
    "PHYSICS_VISION_MODEL": "qwen-vl30-local-prod",
    "PHYSICS_CHAT_NO_THINK_SUFFIX": "/nothink",
    "PHYSICS_VISION_NO_THINK_SUFFIX": "/no_think",
    "PHYSICS_MAX_OUTPUT_TOKENS": "2048",
    "PHYSICS_VISION_MAX_OUTPUT_TOKENS": "1024",
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


def stream_response(text="最终答案"):
    event = json.dumps({"choices": [{"delta": {"content": text}}]}, ensure_ascii=False)
    return FakeResponse(
        lines=[f"data: {event}".encode(), b"data: [DONE]"],
        content_type="text/event-stream",
    )


class ModelRoutingTests(unittest.TestCase):
    def test_text_question_goes_directly_to_glm(self):
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
        self.assertEqual(calls[0]["model"], "glm47-local-prod")
        self.assertTrue(calls[0]["messages"][-1]["content"].endswith("/nothink"))
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

    def test_images_are_recognized_by_qwen_then_passed_as_text_to_glm(self):
        calls = []

        def fake_post(_url, **kwargs):
            payload = kwargs["json"]
            calls.append(payload)
            if payload["model"] == "qwen-vl30-local-prod":
                return FakeResponse(payload={
                    "choices": [{"message": {"content": "图中可见质量 m=2 kg，速度 v=3 m/s。"}}]
                })
            return stream_response("由GLM组织的答案")

        images = [{"data": b"fake-png", "mime": "image/png", "name": "题目.png"}]
        with (
            patch.object(llm, "setting", side_effect=setting_value),
            patch.object(llm, "_request_verify", return_value=False),
            patch.object(llm.requests, "post", side_effect=fake_post),
        ):
            result = "".join(llm.stream_answer("请解答图片中的题目", "教材片段", [], images))

        self.assertEqual(result, "由GLM组织的答案")
        self.assertEqual(
            [call["model"] for call in calls],
            ["qwen-vl30-local-prod", "glm47-local-prod"],
        )
        vision_content = calls[0]["messages"][-1]["content"]
        self.assertTrue(any(item.get("type") == "image_url" for item in vision_content))
        self.assertEqual(vision_content[-1], {"type": "text", "text": "/no_think"})
        chat_content = calls[1]["messages"][-1]["content"]
        self.assertIsInstance(chat_content, str)
        self.assertIn("图中可见质量 m=2 kg", chat_content)
        self.assertNotIn("image_url", chat_content)
        self.assertTrue(chat_content.endswith("/nothink"))

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
        self.assertEqual(calls[0]["model"], "qwen-vl30-local-prod")


if __name__ == "__main__":
    unittest.main()
