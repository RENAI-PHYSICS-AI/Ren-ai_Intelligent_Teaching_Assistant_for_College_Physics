from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
TEXTBOOK_DIR = PROJECT_ROOT / "教学素材" / "教材"
MATERIALS_DIR = PROJECT_ROOT / "教学素材"
TEACHER_MATERIALS_DIR = MATERIALS_DIR / "教师专用"
TEACHER_EXAM_MATERIALS_DIR = TEACHER_MATERIALS_DIR / "教研考试"


def _exam_materials_dir() -> Path:
    """Locate the restricted exam corpus without copying it into the app tree."""
    configured = os.getenv("PHYSICS_EXAM_MATERIALS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    candidates = (PROJECT_ROOT / "考试素材", PROJECT_ROOT.parent / "考试素材")
    return next((path for path in candidates if path.is_dir()), candidates[0])


EXAM_MATERIALS_DIR = _exam_materials_dir()
TEACHER_EXAM_SOURCE_DIRS = (EXAM_MATERIALS_DIR, TEACHER_EXAM_MATERIALS_DIR)
TEACHER_EXAM_GUIDE_FILE = EXAM_MATERIALS_DIR / "大学物理课程章节与组卷分值规范.md"
TEACHER_EXAM_TEMPLATE_FILE = (
    EXAM_MATERIALS_DIR / "试卷" / "2025-2026-2" / "25262大物1补考" / "main.tex"
)
KB_DIR = APP_DIR / "knowledge_base"
KB_FILE = KB_DIR / "chunks.jsonl"
IMPORTED_KB_DIR = KB_DIR / "imports"
PRIVATE_KB_DIR = KB_DIR / "private"
TEACHER_EXAM_KB_FILE = PRIVATE_KB_DIR / "teacher_exam.jsonl"
TEACHER_EXAM_KB_MANIFEST_FILE = PRIVATE_KB_DIR / "teacher_exam.manifest.json"

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
