from __future__ import annotations

import os
import re
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


WEB_PATH = APP_DIR / "experiments" / "franck_hertz" / "web.jl"


class FranckHertzWebContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WEB_PATH.read_text(encoding="utf-8")

    def test_project_and_web_entrypoint_exist(self) -> None:
        self.assertTrue(WEB_PATH.is_file())
        self.assertTrue((WEB_PATH.parent / "Project.toml").is_file())
        self.assertTrue((WEB_PATH.parent / "Manifest.toml").is_file())

    def test_service_contract_uses_private_port_9394(self) -> None:
        service = experiment_hub.FRANCK_HERTZ
        self.assertEqual(service.key, "franck_hertz")
        self.assertEqual(service.title, "弗兰克-赫兹实验")
        self.assertEqual(service.project_dir, WEB_PATH.parent)
        self.assertEqual(service.web_path, WEB_PATH)
        self.assertEqual(service.port_env, "PHYSICS_FRANCK_HERTZ_PORT")
        self.assertEqual(service.default_port, 9394)
        self.assertEqual(service.julia_host_env, "FRANCK_HERTZ_WEB_HOST")
        self.assertEqual(service.julia_port_env, "FRANCK_HERTZ_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "FRANCK_HERTZ_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "franck-hertz-wgl-ready")
        self.assertEqual(service.failed_event, "franck-hertz-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:franck-hertz")
        self.assertEqual(service.root_marker, "弗兰克-赫兹")
        self.assertIs(experiment_hub.SERVICES["franck_hertz"], service)

    def test_public_prefix_gateway_query_and_invalid_port_contract(self) -> None:
        service = experiment_hub.FRANCK_HERTZ
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(service, "/analysis"),
                "/agent/experiments/franck-hertz/analysis",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(service),
                "https://physics.example/agent/experiments/franck-hertz/",
            )

        request = SimpleNamespace(
            path="/agent/experiments/franck-hertz/analysis",
            query_string="scan=8&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9394/analysis?scan=8&theme=dark",
            )

        with patch.dict(os.environ, {"PHYSICS_FRANCK_HERTZ_PORT": "65536"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(service)

    def test_four_independent_routes_health_and_private_port(self) -> None:
        self.assertIn('const HEALTH_MARKER = "physics-experiment:franck-hertz"', self.source)
        self.assertIn('Bonito.route!(server, "/__physics_health__" => health_app())', self.source)
        for route in ("apparatus", "curve", "analysis", "uncertainty"):
            self.assertIn(f'Bonito.route!(server, "/{route}"', self.source)
        self.assertIn('get(ENV, "FRANCK_HERTZ_WEB_PORT", "9394")', self.source)
        self.assertIn('get(ENV, "FRANCK_HERTZ_WEB_HOST", "127.0.0.1")', self.source)
        self.assertIn('get(ENV, "FRANCK_HERTZ_WEB_PROXY_URL", ".")', self.source)

    def test_layout_and_pointer_mapping_follow_experiment_contract(self) -> None:
        self.assertIn("const FIGURE_WIDTH = 960", self.source)
        self.assertIn("const FIGURE_HEIGHT = 760", self.source)
        self.assertIn('document.querySelector(".franck-hertz-lab")', self.source)
        self.assertIn('"pointerdown"', self.source)
        self.assertIn("screen.winscale = baseWinscale * layoutScale", self.source)
        self.assertIn("availableWidth / $(FIGURE_WIDTH)", self.source)
        self.assertIn("availableHeight / $(FIGURE_HEIGHT)", self.source)

    def test_client_status_script_keeps_javascript_newlines_escaped(self) -> None:
        self.assertIn(r'\nWebGL 状态', self.source)
        self.assertIn(r'\n页面地址', self.source)
        self.assertIn(r'\n" + event.filename', self.source)
        self.assertNotIn('75 秒。\nWebGL 状态', self.source.replace(r"\n", ""))

    def test_physics_contract_uses_peak_spacing_and_correct_wavelength_constant(self) -> None:
        constant = re.search(r"const HC_EV_NM = ([0-9.]+)", self.source)
        self.assertIsNotNone(constant)
        self.assertAlmostEqual(float(constant.group(1)), 1239.841984, places=6)
        self.assertIn("λ=hc/(eΔU)≈1239.84/ΔU nm", self.source)
        self.assertIn("绝对首峰不应直接当作激发电势", self.source)
        self.assertIn("6³P₀ 亚稳态约 4.67 eV", self.source)
        self.assertIn("真实汞管实验涉及有毒汞蒸气、高温和高压", self.source)

    def test_sliders_are_distinct_and_self_test_covers_every_page(self) -> None:
        self.assertGreaterEqual(self.source.count("add_slider!(controls,"), 22)
        for builder in (
            "apparatus_figure",
            "curve_figure",
            "analysis_figure",
            "uncertainty_figure",
        ):
            self.assertIn(builder, self.source)
        self.assertIn("for builder in (apparatus_figure, curve_figure, analysis_figure, uncertainty_figure)", self.source)


if __name__ == "__main__":
    unittest.main()
