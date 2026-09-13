from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import conftest


class _FakeItem:
    def __init__(self, name: str) -> None:
        self.path = Path(name)
        self.markers: list[object] = []

    def add_marker(self, marker: object) -> None:
        self.markers.append(marker)


def test_local_asset_modules_are_explicitly_identified() -> None:
    assert conftest.is_local_asset_test("tests/test_added_experiment_knowledge.py")
    assert conftest.is_local_asset_test("tests/test_prism_refractive_index_knowledge.py")
    assert not conftest.is_local_asset_test("tests/test_rag.py")


def test_ci_environment_marks_only_local_asset_tests(monkeypatch) -> None:
    monkeypatch.setenv("PHYSICS_SKIP_LOCAL_ASSET_TESTS", "1")
    local_asset = _FakeItem("tests/test_added_experiment_knowledge.py")
    ordinary = _FakeItem("tests/test_rag.py")

    conftest.pytest_collection_modifyitems(
        SimpleNamespace(),  # type: ignore[arg-type]
        [local_asset, ordinary],  # type: ignore[list-item]
    )

    assert len(local_asset.markers) == 1
    assert getattr(local_asset.markers[0], "name", "") == "skip"
    assert ordinary.markers == []
