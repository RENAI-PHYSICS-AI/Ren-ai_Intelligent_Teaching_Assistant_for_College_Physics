from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import check_portable_paths as portable


WINDOWS_PATH = "C:" + "\\build\\physics"


@pytest.mark.parametrize("ancestor", sorted(portable.SKIP_PARTS))
def test_checkout_ancestors_do_not_suppress_source_audit(
    tmp_path: Path, monkeypatch, ancestor: str
) -> None:
    checkout = tmp_path / ancestor / "project"
    checkout.mkdir(parents=True)
    source = checkout / "application.py"
    source.write_text(f"path={WINDOWS_PATH}\n", encoding="utf-8")
    monkeypatch.setattr(portable, "ROOT", checkout)

    errors: list[str] = []
    portable.audit_source_text(errors)

    assert errors == [f"硬编码盘符：{source.name}:1"]


@pytest.mark.parametrize("excluded", sorted(portable.SKIP_PARTS))
def test_project_subdirectories_remain_excluded(
    tmp_path: Path, monkeypatch, excluded: str
) -> None:
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    excluded_dir = tmp_path / "package" / excluded
    excluded_dir.mkdir(parents=True)
    source = excluded_dir / "application.py"
    source.write_text(f"path={WINDOWS_PATH}\n", encoding="utf-8")
    included = tmp_path / "application.py"
    included.write_text("value=1\n", encoding="utf-8")

    assert list(portable.project_text_files()) == [included]
    errors: list[str] = []
    portable.audit_source_text(errors)
    assert errors == []


@pytest.mark.parametrize(
    "suffix",
    [".yml", ".yaml", ".js", ".html", ".css", ".env", ".jsonl", ".svg", ".tex", ".txt"],
)
def test_new_text_suffixes_are_scanned(tmp_path: Path, monkeypatch, suffix: str) -> None:
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    source = tmp_path / f"configuration{suffix}"
    source.write_text(f"path={WINDOWS_PATH}\n", encoding="utf-8")

    errors: list[str] = []
    portable.audit_source_text(errors)

    assert errors == [f"硬编码盘符：{source.name}:1"]


def test_fixture_marker_is_limited_to_exact_test_comment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    test_dir = tmp_path / "package" / "tests"
    test_dir.mkdir(parents=True)
    exact = test_dir / "test_fixture.py"
    exact.write_text(
        f"value={WINDOWS_PATH}  # {portable.TEST_FIXTURE_MARKER}\n",
        encoding="utf-8",
    )

    errors: list[str] = []
    portable.audit_source_text(errors)

    assert errors == []


@pytest.mark.parametrize(
    "relative, trailer",
    [
        (Path("application.py"), ""),
        (Path("application.py"), "  # portable-path-test-fixture"),
        (Path("tests/test_fixture.py"), "  # portable-path-test-fixture-extra"),
    ],
)
def test_non_test_or_inexact_markers_do_not_bypass_scan(
    tmp_path: Path, monkeypatch, relative: Path, trailer: str
) -> None:
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    source = tmp_path / relative
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(f"path={WINDOWS_PATH}{trailer}\n", encoding="utf-8")

    errors: list[str] = []
    portable.audit_source_text(errors)

    assert len(errors) == 1
    assert errors[0].startswith("硬编码盘符：")


@pytest.mark.parametrize("value", [
    "/" + "home/alice/project", "/" + "Users/alice/project",
    "/" + "root/project", "\\\\" + "server\\share\\file", "//" + "server/share/file",
])
def test_personal_and_unc_paths_in_settings_are_rejected(tmp_path, monkeypatch, value):
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    (tmp_path / "app.env").write_text(f'ASSET="{value}"\n', encoding="utf-8")
    errors = []
    portable.audit_source_text(errors)
    assert errors == ["硬编码个人或共享目录：app.env:1"]


def test_system_paths_urls_and_historical_reports_are_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    (tmp_path / "settings.env").write_text(
        'FONT=/usr/share/fonts/example.ttf\nTOOL=/usr/bin/env\n'
        'APP=${HOME}/project\nUNIT=%h/project\nTLS=config/tls/server.crt\n'
        'URL=https://example.org/home/alice/reference\n', encoding="utf-8"
    )
    (tmp_path / "report.md").write_text("历史安装位置：/" + "home/alice/project", encoding="utf-8")
    errors = []
    portable.audit_source_text(errors)
    assert errors == []


@pytest.mark.parametrize("value", [
    WINDOWS_PATH, "/" + "home/alice/notes.pdf", "../private.pdf", "~/notes.pdf",
    "file:///notes.pdf", "https://example.org/notes.pdf", "folder\\notes.pdf",
])
@pytest.mark.parametrize("field", ["source", "source_path", "source_roots", "local_file", "output"])
def test_import_and_private_metadata_require_portable_paths(tmp_path, monkeypatch, value, field):
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    index = tmp_path / "agnet/knowledge_base/private/teacher_exam.manifest.json"
    index.parent.mkdir(parents=True)
    item = [value] if field == "source_roots" else value
    index.write_text(json.dumps({"sources": [{field: item}]}), encoding="utf-8")
    errors = []
    portable.audit_knowledge_base(errors)
    assert len(errors) == 1
    assert field in errors[0]
    assert value not in errors[0]  # No private content or paths in diagnostics.


def test_nested_import_metadata_keeps_user_prose_and_urls_out_of_audit(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    index = tmp_path / "agnet/knowledge_base/imports/experiment.jsonl"
    index.parent.mkdir(parents=True)
    row = {"source_path": "教学素材/实验/说明.md", "url": "https://example.org/paper",
           "text": "引用过的历史路径：" + WINDOWS_PATH,
           "sources": [{"local_file": "ref/paper.pdf"}]}
    index.write_text(json.dumps(row), encoding="utf-8")
    errors = []
    portable.audit_knowledge_base(errors)
    assert errors == []


def test_malformed_index_reports_only_location(tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    index = tmp_path / "agnet/knowledge_base/imports/broken.jsonl"
    index.parent.mkdir(parents=True)
    index.write_text('{"text": "PRIVATE_SENTINEL"', encoding="utf-8")
    errors = []
    portable.audit_knowledge_base(errors)
    assert len(errors) == 1
    assert "broken.jsonl" in errors[0]
    assert "PRIVATE_SENTINEL" not in errors[0]


@pytest.mark.parametrize("stored_path", ["outputs/main.pdf", WINDOWS_PATH, "/outside/notes.pdf", "../notes.pdf"])
def test_database_checks_path_columns_not_message_prose(tmp_path, monkeypatch, stored_path):
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    database = tmp_path / "with spaces # 教学/data/app.db"
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute('CREATE TABLE messages(content TEXT, password_hash TEXT, file_path TEXT)')
        connection.execute("INSERT INTO messages VALUES (?, ?, ?)", (WINDOWS_PATH, WINDOWS_PATH, stored_path))
        connection.commit()
    before = database.read_bytes()
    errors = []
    portable.audit_databases(errors)
    assert database.read_bytes() == before
    assert bool(errors) == (stored_path != "outputs/main.pdf")
    if errors:
        assert "file_path" in errors[0]
        assert stored_path not in errors[0]


@pytest.mark.parametrize("name", ["main.tex", WINDOWS_PATH])
def test_database_attachments_audit_filename_not_payload(tmp_path, monkeypatch, name):
    monkeypatch.setattr(portable, "ROOT", tmp_path)
    database = tmp_path / "data/app.db"
    database.parent.mkdir(parents=True)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute('CREATE TABLE messages(artifacts_json TEXT)')
        attachment = {"name": name, "data": WINDOWS_PATH, "mime": "application/x-tex"}
        connection.execute("INSERT INTO messages VALUES (?)", (json.dumps([attachment]),))
        connection.commit()
    errors = []
    portable.audit_databases(errors)
    assert bool(errors) == (name != "main.tex")
    assert all(WINDOWS_PATH not in error for error in errors)
