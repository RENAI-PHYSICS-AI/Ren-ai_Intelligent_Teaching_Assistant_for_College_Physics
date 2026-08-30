from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import web_search


SETTINGS = {
    "PHYSICS_WEB_SEARCH_PROVIDER": "tavily",
    "TAVILY_API_KEY": "secret-test-key",
    "PHYSICS_WEB_SEARCH_MAX_RESULTS": "5",
    "PHYSICS_WEB_SEARCH_TIMEOUT_SECONDS": "8",
    "PHYSICS_WEB_SEARCH_CACHE_MINUTES": "30",
}


def setting_value(name, default=""):
    return SETTINGS.get(name, default)


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class WebSearchTests(unittest.TestCase):
    def setUp(self):
        web_search._CACHE.clear()

    def test_regular_course_question_does_not_search(self):
        with (
            patch.object(web_search, "setting", side_effect=setting_value),
            patch.object(web_search.requests, "post") as post,
        ):
            self.assertEqual(web_search.search_web("动量守恒条件是什么？"), [])
        post.assert_not_called()

    def test_explicit_network_information_request_triggers_search(self):
        with patch.object(web_search, "setting", side_effect=setting_value):
            self.assertTrue(web_search.should_search_web("请结合网络的信息生成一份试卷"))

    def test_time_sensitive_question_searches_and_sanitizes_results(self):
        payload = {"results": [
            {"title": "  Official   update ", "url": "https://example.edu/news", "content": "new\nresult"},
            {"title": "unsafe", "url": "javascript:alert(1)", "content": "ignore"},
        ]}
        with (
            patch.object(web_search, "setting", side_effect=setting_value),
            patch.object(web_search.requests, "post", return_value=FakeResponse(payload)) as post,
        ):
            results = web_search.search_web("量子计算最新进展")
        self.assertEqual(results, [{
            "title": "Official update",
            "url": "https://example.edu/news",
            "content": "new result",
        }])
        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["search_depth"], "basic")
        self.assertEqual(request_payload["time_range"], "year")
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer secret-test-key",
        )

    def test_failure_falls_back_without_raising(self):
        with (
            patch.object(web_search, "setting", side_effect=setting_value),
            patch.object(web_search.requests, "post", side_effect=requests.Timeout("slow")),
        ):
            self.assertEqual(web_search.search_web("请联网搜索最新进展"), [])

    def test_source_links_are_appended(self):
        result = web_search.append_web_sources("答案", [{
            "title": "来源",
            "url": "https://example.edu/source",
            "content": "摘要",
        }])
        self.assertIn("联网参考来源", result)
        self.assertIn("[来源](https://example.edu/source)", result)


if __name__ == "__main__":
    unittest.main()
