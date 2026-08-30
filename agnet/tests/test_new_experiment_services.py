from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import experiment_hub
import gateway
import build_kb


SERVICE_CASES = (
    (
        experiment_hub.TEMPERATURE_SENSOR,
        "temperature_sensor",
        "temperature-sensor",
        9395,
        "physics-experiment:temperature-sensor",
    ),
    (
        experiment_hub.WHEATSTONE_BRIDGE,
        "wheatstone_bridge",
        "wheatstone-bridge",
        9396,
        "physics-experiment:wheatstone-bridge",
    ),
    (
        experiment_hub.HALL_EFFECT,
        "hall_effect",
        "hall-effect",
        9397,
        "physics-experiment:hall-effect",
    ),
    (
        experiment_hub.MAGNETIC_HYSTERESIS,
        "magnetic_hysteresis",
        "magnetic-hysteresis",
        9398,
        "physics-experiment:magnetic-hysteresis",
    ),
    (
        experiment_hub.THIN_LENS_FOCAL,
        "thin_lens_focal",
        "thin-lens-focal",
        9399,
        "physics-experiment:thin-lens-focal",
    ),
    (
        experiment_hub.PRISM_REFRACTIVE_INDEX,
        "prism_refractive_index",
        "prism-refractive-index",
        9400,
        "physics-experiment:prism-refractive-index",
    ),
    (
        experiment_hub.THERMAL_CONDUCTIVITY,
        "thermal_conductivity",
        "thermal-conductivity",
        9401,
        "physics-experiment:thermal-conductivity",
    ),
)


class NewExperimentServiceTests(unittest.TestCase):
    def test_new_knowledge_collections_use_subject_accurate_labels(self) -> None:
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS["thin_lens_focal"],
            ("薄透镜焦距的测定实验", "光学实验·几何光学"),
        )
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS["prism_refractive_index"],
            ("三棱镜折射率测定实验", "光学实验·几何光学"),
        )
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS["thermal_conductivity"],
            ("固体热传导系数测定实验", "第5章 热力学基础"),
        )

    def test_private_service_and_gateway_contracts(self) -> None:
        for service, key, slug, port, marker in SERVICE_CASES:
            with self.subTest(key=key):
                self.assertEqual(service.key, key)
                self.assertEqual(service.default_port, port)
                self.assertEqual(service.identity_marker, marker)
                self.assertIs(experiment_hub.SERVICES[key], service)
                self.assertEqual(
                    gateway.EXPERIMENT_UPSTREAMS[f"/experiments/{slug}"],
                    f"http://127.0.0.1:{port}",
                )

                request = SimpleNamespace(
                    path=f"/agent/experiments/{slug}/__physics_health__",
                    query_string="attempt=3",
                )
                with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
                    self.assertEqual(
                        gateway.upstream_url(request),
                        f"http://127.0.0.1:{port}/__physics_health__?attempt=3",
                    )

    def test_browser_paths_keep_the_public_prefix(self) -> None:
        with patch.dict(
            "os.environ",
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            for service, _, slug, _, _ in SERVICE_CASES:
                with self.subTest(slug=slug):
                    self.assertEqual(
                        experiment_hub.service_browser_path(service, "/fit"),
                        f"/agent/experiments/{slug}/fit",
                    )

    def test_rocky_management_scripts_cover_all_new_services(self) -> None:
        project_root = APP_DIR.parent
        deployment_root = (
            project_root
            if project_root.name == "agent_of_college_physics"
            else project_root / "agent_of_college_physics"
        )
        manage = (deployment_root / "manage.sh").read_text(encoding="utf-8")
        install = (deployment_root / "install.sh").read_text(encoding="utf-8")
        for _, key, slug, port, marker in SERVICE_CASES:
            with self.subTest(key=key):
                env_stem = key.upper()
                self.assertIn(f"PHYSICS_{env_stem}_PORT", manage)
                self.assertIn(f'"{slug}" "{marker}"', manage)
                self.assertIn(f"experiments/{key}/web.jl", manage)
                self.assertIn(key, install)
                self.assertIn(str(port), manage)


if __name__ == "__main__":
    unittest.main()
