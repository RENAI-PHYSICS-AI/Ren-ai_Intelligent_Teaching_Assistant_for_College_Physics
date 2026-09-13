from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import check_portable_paths as portable


WINDOWS_PATH = "C:" + "\\build\\physics"


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
