from __future__ import annotations

import re


_FENCED_CODE_RE = re.compile(
    r"(```[^\r\n`]*\r?\n.*?(?:```|\Z))",
    re.S,
)
_SOURCE_CITATION_RE = re.compile(r"\s*\[资料\s*\d+\]")
_SOURCE_PHRASE_RE = re.compile(
    r"(?:结合|根据)您提供的(?:教材)?资料(?:（[^）]*）)?(?:以及课堂讨论内容)?"
)


def _normalize_prose_latex(text: str) -> str:
    text = _SOURCE_CITATION_RE.sub("", text)
    text = _SOURCE_PHRASE_RE.sub("依据知识库", text)
    text = text.replace(r"\[", "\n$$\n").replace(r"\]", "\n$$\n")
    text = text.replace(r"\(", "$").replace(r"\)", "$")
    return re.sub(r"\n{3,}", "\n\n", text)


def normalize_latex_markdown(value: object) -> str:
    r"""Normalize prose math delimiters without ever rewriting fenced code.

    TeX answers are delivered inside named Markdown fences.  Rewriting ``\[``
    inside such a fence also corrupts a valid row break like ``\\[2pt]``.
    Splitting around complete fences keeps source files byte-for-byte intact.
    A truncated, unclosed fence is protected through end-of-message as well,
    while ordinary prose retains the Streamlit-friendly delimiter conversion.
    """
    text = str(value or "")
    parts = _FENCED_CODE_RE.split(text)
    return "".join(
        part if index % 2 else _normalize_prose_latex(part)
        for index, part in enumerate(parts)
    )
