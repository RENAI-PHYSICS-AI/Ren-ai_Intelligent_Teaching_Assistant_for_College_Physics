from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools import check_runtime_sync


def test_runtime_inventory_includes_builders_and_julia_dependencies(tmp_path: Path) -> None:
    root = tmp_path / "agnet"
    experiment = root / "experiments" / "demo"
    experiment.mkdir(parents=True)
    (root / "build_shared_import.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "build_electron_em_import.py").write_text("VALUE = 2\n", encoding="utf-8")
    (experiment / "web.jl").write_text("value = 1\n", encoding="utf-8")
    (experiment / "Project.toml").write_text('[deps]\nDemo = "uuid"\n', encoding="utf-8")
    (experiment / "Manifest.toml").write_text('julia_version = "1.10"\n', encoding="utf-8")

    inventory = check_runtime_sync._runtime_files(root)

    assert Path("build_shared_import.py") in inventory
    assert Path("build_electron_em_import.py") not in inventory
    assert Path("experiments/demo/web.jl") in inventory
    assert Path("experiments/demo/Project.toml") in inventory
    assert Path("experiments/demo/Manifest.toml") in inventory


def test_toml_signature_ignores_formatting_and_key_order(tmp_path: Path) -> None:
    first = tmp_path / "first.toml"
    second = tmp_path / "second.toml"
    first.write_text('[compat]\njulia = "1.10"\nBonito = "4.2"\n', encoding="utf-8")
    second.write_text('[compat]\nBonito="4.2"\n\njulia="1.10"\n', encoding="utf-8")

    assert check_runtime_sync._toml_signature(first) == check_runtime_sync._toml_signature(second)


def test_shared_launchers_and_examples_are_checked_but_windows_only_scripts_are_not(tmp_path):
    shared = ("launcher_paths.sh", "model.service", "model.env.example")
    windows_only = ("start.bat", "start.ps1")
    for name in shared + windows_only:
        (tmp_path / name).write_text("# fixture\n", encoding="utf-8")
    inventory = check_runtime_sync._runtime_files(tmp_path)
    assert set(inventory) == {Path(name) for name in shared}
