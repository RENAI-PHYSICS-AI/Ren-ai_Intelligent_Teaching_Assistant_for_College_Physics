#!/usr/bin/env python3
"""Audit source and stored path metadata without changing application data."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path, PurePosixPath, PureWindowsPath


ROOT = Path(__file__).resolve().parent
DRIVE_PATH = re.compile(r"(?i)(?<![A-Za-z])[A-Z]:[\\/]")
PERSONAL_PATH = re.compile(
    r"(?<![:/\w])/(?:home|Users)/[\w.-]+(?:/|(?=[\s\"']|$))"
    r"|(?<![:/\w])/ro" r"ot/"
)
UNC_PATH = re.compile(
    r"(?<![:/\\\w])(?:\\\\|//)[\w.-]+[\\/][\w$.-]+(?=[\\/][\w.-]|[\"'\s]|$)"
)
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
# Historical reports and quoted course content are not executable settings.
CONFIG_SOURCE_SUFFIXES = {
    "", ".py", ".jl", ".sh", ".ps1", ".bat", ".cmd", ".service", ".env",
    ".example", ".toml", ".yaml", ".yml", ".ini", ".conf", ".js", ".ts",
    ".jsx", ".tsx", ".html", ".css",
}
UNC_CONFIG_SUFFIXES = {".env", ".example", ".service", ".toml", ".yaml", ".yml", ".ini", ".conf"}
METADATA_PATH_FIELDS = {
    "relative_path", "source_path", "source", "path", "local_file", "file", "same_as",
    "index_file", "output", "source_catalog", "source_roots", "excluded_materials",
    "primary_textbook", "primary_solution", "standard_template", "mandatory_guide",
}
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
    if not value or "\\" in value or value.startswith(("/", "~")):
        return False
    if PureWindowsPath(value).drive or URI_SCHEME.match(value):
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
            continue
        if path.suffix.lower() not in CONFIG_SOURCE_SUFFIXES:
            continue
        for pattern in (PERSONAL_PATH, UNC_PATH):
            # Python/TeX regular expressions can resemble UNC shares.
            if pattern is UNC_PATH and path.suffix.lower() not in UNC_CONFIG_SUFFIXES:
                continue
            match = next(
                (candidate for candidate in pattern.finditer(text)
                 if not is_marked_test_fixture(path, text, candidate.start())), None
            )
            if match is not None:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"硬编码个人或共享目录：{path.relative_to(ROOT)}:{line}")
                break


def metadata_path_values(value, prefix: str = ""):
    """Inspect explicit path fields only, never user prose or reference URLs."""
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else key
            if key in METADATA_PATH_FIELDS:
                if isinstance(child, str) and child:
                    yield location, child
                elif isinstance(child, list):
                    for index, item in enumerate(child):
                        if isinstance(item, str) and item:
                            yield f"{location}[{index}]", item
            yield from metadata_path_values(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from metadata_path_values(child, f"{prefix}[{index}]")


def audit_index_file(path: Path, errors: list[str]) -> None:
    """Validate main/import/private index metadata, with no content in errors."""
    relative = path.relative_to(ROOT).as_posix()
    try:
        with path.open(encoding="utf-8-sig") as handle:
            if path.suffix == ".jsonl":
                rows = ((number, json.loads(line)) for number, line in enumerate(handle, 1)
                        if line.strip())
            else:
                rows = ((1, json.load(handle)),)
            for number, row in rows:
                if path.name == "chunks.jsonl" and (
                    not isinstance(row, dict) or not safe_relative(str(row.get("relative_path", "")))
                ):
                    errors.append(f"非法知识库路径：{relative}:{number} -> relative_path")
                    return
                for field, value in metadata_path_values(row):
                    if not safe_relative(value):
                        errors.append(f"非法知识库路径：{relative}:{number} -> {field}")
                        return
    except (OSError, ValueError) as exc:
        # Do not print JSON decoding excerpts, which may contain private text.
        errors.append(f"知识库元数据无法读取：{relative} ({type(exc).__name__})")


def audit_knowledge_base(errors: list[str]) -> None:
    for app_root in (ROOT / "agnet", ROOT / "agent_of_college_physics" / "agnet"):
        kb_root = app_root / "knowledge_base"
        if not kb_root.is_dir():
            continue
        for path in sorted(kb_root.rglob("*")):
            if path.is_file() and path.suffix in {".json", ".jsonl"}:
                audit_index_file(path, errors)
        manifest_path = kb_root / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue  # Already reported by audit_index_file.
        if not isinstance(manifest, dict):
            errors.append(f"非法知识库清单：{manifest_path.relative_to(ROOT)}")
            continue
        project_root = app_root.parent
        for key in ("primary_textbook", "primary_solution"):
            value = str(manifest.get(key, ""))
            if not safe_relative(value):
                errors.append(f"非法清单路径：{manifest_path.relative_to(ROOT)} -> {key}")
            elif not (project_root / value).is_file():
                errors.append(f"清单目标不存在：{manifest_path.relative_to(ROOT)} -> {value}")


def audit_databases(errors: list[str]) -> None:
    attachment_columns = {"images_json", "artifacts_json", "attachments_json"}
    for database in ROOT.glob("**/data/**/*.db"):
        if any(part in SKIP_PARTS for part in database.relative_to(ROOT).parts):
            continue
        try:
            # URI escaping also handles relocated directories with spaces/#.
            with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                for (table,) in tables.fetchall():
                    quoted_table = '"' + table.replace('"', '""') + '"'
                    columns = connection.execute(f'PRAGMA table_info({quoted_table})').fetchall()
                    for column in (row[1] for row in columns):
                        is_path = column in {"path", "file", "directory"} or column.endswith(("_path", "_dir", "_file"))
                        if not is_path and column not in attachment_columns:
                            continue  # Message prose, hashes and logs are not file paths.
                        quoted_column = '"' + column.replace('"', '""') + '"'
                        rows = connection.execute(
                            f'SELECT {quoted_column} FROM {quoted_table} WHERE {quoted_column} IS NOT NULL'
                        )
                        for (raw,) in rows:
                            if not raw:
                                continue
                            if is_path:
                                values = ((column, str(raw)),)
                            else:
                                try:
                                    attachments = json.loads(raw)
                                except (ValueError, TypeError):
                                    errors.append(f"附件元数据无法读取：{database.relative_to(ROOT)} -> {table}.{column}")
                                    break
                                values = list(metadata_path_values(attachments))
                                if isinstance(attachments, list):
                                    values.extend(
                                        (f"[{index}].name", item["name"])
                                        for index, item in enumerate(attachments)
                                        if isinstance(item, dict) and isinstance(item.get("name"), str)
                                    )
                            if any(not safe_relative(value) for _field, value in values):
                                errors.append(f"数据库路径非相对路径：{database.relative_to(ROOT)} -> {table}.{column}")
                                break
        except sqlite3.Error as exc:
            errors.append(f"数据库检查失败：{database.relative_to(ROOT)} ({type(exc).__name__})")


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
    print("便携路径检查通过：源码无硬编码个人路径，知识库路径元数据均为相对路径。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
