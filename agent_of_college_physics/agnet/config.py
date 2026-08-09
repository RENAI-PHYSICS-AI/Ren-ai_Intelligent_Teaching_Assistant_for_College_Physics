from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
TEXTBOOK_DIR = PROJECT_ROOT / "教学素材" / "教材"
MATERIALS_DIR = PROJECT_ROOT / "教学素材"
KB_DIR = APP_DIR / "knowledge_base"
KB_FILE = KB_DIR / "chunks.jsonl"
IMPORTED_KB_DIR = KB_DIR / "imports"

TEXTBOOK_NAME = "物理学 第5版（祝之光，2018，高等教育出版社）"
SOLUTION_NAME = "物理学（第五版）祝之光习题解答"


def setting(name: str, default: str = "") -> str:
    """Read environment settings without making Streamlit a hard dependency."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name.lower(), default))
    except Exception:
        return default
