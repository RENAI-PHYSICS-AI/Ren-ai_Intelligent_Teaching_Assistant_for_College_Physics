from __future__ import annotations

import os
from pathlib import Path

import pytest


LOCAL_ASSET_TEST_MODULES = frozenset(
    {
        "test_added_experiment_knowledge.py",
        "test_franck_hertz_knowledge.py",
        "test_hall_effect_experiment.py",
        "test_magnetic_hysteresis_knowledge.py",
        "test_prism_refractive_index_knowledge.py",
        "test_rotational_inertia_knowledge.py",
        "test_specific_heat_knowledge.py",
        "test_temperature_sensor_knowledge.py",
        "test_thermal_conductivity_knowledge.py",
        "test_thin_lens_focal_knowledge.py",
        "test_viscosity_knowledge.py",
    }
)


def is_local_asset_test(path: object) -> bool:
    """Return whether a test module needs ignored or Git-LFS teaching files."""
    return Path(str(path)).name in LOCAL_ASSET_TEST_MODULES


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv("PHYSICS_SKIP_LOCAL_ASSET_TESTS", "").strip() != "1":
        return
    skip = pytest.mark.skip(
        reason="requires local or Git-LFS teaching assets omitted from the CI checkout"
    )
    for item in items:
        if is_local_asset_test(item.path):
            item.add_marker(skip)
