#!/usr/bin/env python3
"""Fail when project-owned paths depend on a Windows drive or escape the project."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path, PurePosixPath, PureWindowsPath


ROOT = Path(__file__).resolve().parent
DRIVE_PATH = re.compile(r"(?i)(?<![A-Za-z])[A-Z]:[\\/]")
TEST_FIXTURE_MARKER = "portable-path-test-fixture"
TEST_FIXTURE_COMMENT = re.compile(
    rf"(?:^|\s)(?:#|//)\s*{re.escape(TEST_FIXTURE_MARKER)}\s*$"
)
TEXT_SUFFIXES = {
    "",
    ".bat",
    ".cjs",
    ".cmd",
    ".conf",
    ".css",
    ".env",
    ".example",
    ".gitignore",
    ".gitattributes",
    ".htm",
    ".html",
    ".in",
    ".ini",
    ".jl",
    ".js",
    ".jsx",
    ".json",
    ".jsonl",
    ".less",
    ".lock",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".scss",
    ".service",
    ".sh",
    ".svg",
    ".tex",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
SKIP_PARTS = {
    ".git", ".venv", ".runtime", ".codex-tmp", ".tmp",
    "__pycache__", "教学素材", "考试素材", "tmp",
}


def project_text_files():
    for path in ROOT.rglob("*"):
        relative_path = path.relative_to(ROOT)
        # Ignore project-owned subdirectories, not ancestors of the checkout.
        if not path.is_file() or any(part in SKIP_PARTS for part in relative_path.parts):
            continue
        relative = relative_path.as_posix()
        if "/knowledge_base/private/" in f"/{relative}":
            continue
        if relative.endswith("knowledge_base/chunks.jsonl"):
            continue
        if "/knowledge_base/imports/" in f"/{relative}" and path.suffix == ".jsonl":
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_SUFFIXES:
            yield path


def safe_relative(value: str) -> bool:
    if not value or "\\" in value or value.startswith(("/", "\\")):
        return False
    if PureWindowsPath(value).drive:
        return False
    return ".." not in PurePosixPath(value).parts


def is_marked_test_fixture(path: Path, text: str, offset: int) -> bool:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return False
    if "tests" not in relative.parts:
        return False
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end < 0:
        line_end = len(text)
    return TEST_FIXTURE_COMMENT.search(text[line_start:line_end]) is not None


def audit_source_text(errors: list[str]) -> None:
    for path in project_text_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"无法读取 {path.relative_to(ROOT)}：{exc}")
            continue
        match = next(
            (
                candidate
                for candidate in DRIVE_PATH.finditer(text)
                if not is_marked_test_fixture(path, text, candidate.start())
            ),
            None,
        )
        if match is not None:
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"硬编码盘符：{path.relative_to(ROOT)}:{line}")


def audit_knowledge_base(errors: list[str]) -> None:
    for app_root in (ROOT / "agnet", ROOT / "agent_of_college_physics" / "agnet"):
        chunks = app_root / "knowledge_base" / "chunks.jsonl"
        if not chunks.is_file():
            continue
        with chunks.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                value = str(row.get("relative_path", ""))
                if not safe_relative(value):
                    errors.append(f"非法知识库路径：{chunks.relative_to(ROOT)}:{line_number}")
                    break

        manifest_path = app_root / "knowledge_base" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        project_root = app_root.parent
        for key in ("primary_textbook", "primary_solution"):
            value = str(manifest.get(key, ""))
            if not safe_relative(value):
                errors.append(f"非法清单路径：{manifest_path.relative_to(ROOT)} -> {key}")
            elif not (project_root / value).is_file():
                errors.append(f"清单目标不存在：{manifest_path.relative_to(ROOT)} -> {value}")


def audit_databases(errors: list[str]) -> None:
    for database in ROOT.glob("**/data/**/*.db"):
        if ".venv" in database.parts:
            continue
        try:
            with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                for (table,) in tables.fetchall():
                    columns = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                    for column in (row[1] for row in columns if str(row[2]).upper() in {"", "TEXT"}):
                        rows = connection.execute(
                            f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
                        )
                        if any(DRIVE_PATH.search(str(row[0])) for row in rows):
                            errors.append(
                                f"数据库含盘符：{database.relative_to(ROOT)} -> {table}.{column}"
                            )
        except sqlite3.Error as exc:
            errors.append(f"数据库检查失败：{database.relative_to(ROOT)}：{exc}")


def main() -> int:
    errors: list[str] = []
    audit_source_text(errors)
    audit_knowledge_base(errors)
    audit_databases(errors)
    if errors:
        print("便携路径检查失败：")
        for error in errors:
            print(f"- {error}")
        return 1
    print("便携路径检查通过：未发现盘符注入，知识库和数据库路径均可迁移。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
