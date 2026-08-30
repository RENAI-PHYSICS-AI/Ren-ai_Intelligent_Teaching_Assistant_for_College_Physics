from __future__ import annotations

import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from text_formatting import normalize_latex_markdown


def test_prose_math_is_normalized_for_streamlit() -> None:
    result = normalize_latex_markdown(r"行内 \(F=ma\)，显示 \[E=mc^2\] [资料 2]")
    assert "$F=ma$" in result
    assert "\n$$\nE=mc^2\n$$\n" in result
    assert "资料 2" not in result


def test_named_tex_fence_is_preserved_byte_for_byte() -> None:
    tex = (
        "```latex answer.tex\n"
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Title\\\\[2pt]\n"
        "\\[E=mc^2\\]\n"
        "\\end{document}\n"
        "```"
    )
    source = r"正文中 \(x=1\)。" + "\n" + tex + "\n" + r"结尾 \[y=2\]。"
    result = normalize_latex_markdown(source)

    assert tex in result
    assert "$x=1$" in result
    assert "\n$$\ny=2\n$$\n" in result
    assert "Title\\\n$$" not in result


def test_multiple_fences_and_non_tex_code_are_not_rewritten() -> None:
    first = "```python\nvalue = r'\\[not_math\\]'\n```"
    second = "```tex answer.tex\nA\\\\[4pt]\n```"
    result = normalize_latex_markdown(first + "\n\n" + second)
    assert first in result
    assert second in result


def test_truncated_unclosed_tex_fence_is_protected_to_end_of_message() -> None:
    source = (
        r"开头 \(x=1\)。"
        "\n```latex answer.tex\n"
        "\\documentclass{article}\n"
        "Title\\\\[2pt]\n"
        "\\[E=mc^2\\]\n"
    )
    result = normalize_latex_markdown(source)

    assert "$x=1$" in result
    assert "Title\\\\[2pt]" in result
    assert "\\[E=mc^2\\]" in result
    assert "Title\\\n$$" not in result
