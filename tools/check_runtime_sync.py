#!/usr/bin/env python3
"""Fail when the Windows runtime and Rocky release snapshot drift apart.

Shared runtime/build Python, Julia implementations, and Julia dependency files
must stay semantically identical.  Only the explicitly listed source-only
importers may be absent from the Rocky release snapshot.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRIMARY_ROOT = REPOSITORY_ROOT / "agnet"
ROCKY_ROOT = REPOSITORY_ROOT / "agent_of_college_physics" / "agnet"
PRIMARY_ONLY_BUILD_FILES = frozenset(
    {
        # These corpus importers are retained only in the Windows source tree;
        # their already-built JSONL indexes are shipped in the Rocky snapshot.
        "build_electron_em_import.py",
        "build_photoelectric_import.py",
    }
)
JULIA_DEPENDENCY_FILES = frozenset({"Project.toml", "Manifest.toml"})


def _runtime_files(root: Path) -> dict[Path, Path]:
    files: dict[Path, Path] = {}
    for path in root.glob("*.py"):
        if path.name in PRIMARY_ONLY_BUILD_FILES:
            continue
        files[path.relative_to(root)] = path
    for path in (root / "experiments").rglob("*"):
        if path.is_file() and (
            path.suffix == ".jl" or path.name in JULIA_DEPENDENCY_FILES
        ):
            files[path.relative_to(root)] = path
    return files


def _python_signature(path: Path) -> str:
    source = path.read_text(encoding="utf-8-sig")
    return ast.dump(ast.parse(source, filename=str(path)), include_attributes=False)


def _text_signature(path: Path) -> str:
    lines = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").splitlines()
    return "\n".join(line.rstrip() for line in lines).strip()


def _toml_signature(path: Path) -> dict:
    source = path.read_text(encoding="utf-8-sig")
    return tomllib.loads(source)


def _signature(path: Path):
    if path.suffix == ".py":
        return _python_signature(path)
    if path.suffix == ".toml":
        return _toml_signature(path)
    return _text_signature(path)


def main() -> int:
    primary = _runtime_files(PRIMARY_ROOT)
    rocky = _runtime_files(ROCKY_ROOT)
    failures: list[str] = []

    for relative in sorted(primary.keys() | rocky.keys(), key=lambda item: item.as_posix()):
        if relative not in primary:
            failures.append(f"only in Rocky snapshot: {relative.as_posix()}")
            continue
        if relative not in rocky:
            failures.append(f"missing from Rocky snapshot: {relative.as_posix()}")
            continue
        try:
            matches = _signature(primary[relative]) == _signature(rocky[relative])
        except (OSError, SyntaxError, tomllib.TOMLDecodeError, UnicodeError) as exc:
            failures.append(f"cannot compare {relative.as_posix()}: {exc}")
            continue
        if not matches:
            failures.append(f"runtime differs: {relative.as_posix()}")

    if failures:
        print("Windows/Rocky runtime synchronization check failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"Runtime synchronization check passed ({len(primary)} shared files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
