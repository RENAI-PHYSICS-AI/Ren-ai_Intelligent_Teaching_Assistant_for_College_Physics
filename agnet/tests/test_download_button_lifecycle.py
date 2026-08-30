from __future__ import annotations

import ast
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]


def streamlit_download_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
        and node.func.attr == "download_button"
    ]


class DownloadButtonLifecycleTests(unittest.TestCase):
    def test_downloads_never_rerun_the_page(self) -> None:
        expected_counts = {
            APP_DIR / "app.py": 3,
            APP_DIR / "visualization.py": 1,
        }
        for path, expected_count in expected_counts.items():
            calls = streamlit_download_calls(path)
            self.assertEqual(len(calls), expected_count, path.name)
            for call in calls:
                with self.subTest(file=path.name, line=call.lineno):
                    keyword = next(
                        (item for item in call.keywords if item.arg == "on_click"),
                        None,
                    )
                    self.assertIsNotNone(
                        keyword,
                        "下载按钮必须禁止页面重跑，避免首次点击时临时 URL 失效",
                    )
                    self.assertIsInstance(keyword.value, ast.Constant)
                    self.assertEqual(keyword.value.value, "ignore")


if __name__ == "__main__":
    unittest.main()
