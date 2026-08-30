from __future__ import annotations

import os
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


class SpecificHeatServiceTests(unittest.TestCase):
    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_service_contract_uses_private_port_9393(self) -> None:
        service = experiment_hub.SPECIFIC_HEAT
        self.assertEqual(service.key, "specific_heat")
        self.assertEqual(service.title, "固体比热容的测定实验")
        self.assertEqual(service.project_dir, APP_DIR / "experiments" / "specific_heat")
        self.assertEqual(service.web_path, service.project_dir / "web.jl")
        self.assertEqual(service.port_env, "PHYSICS_SPECIFIC_HEAT_PORT")
        self.assertEqual(service.default_port, 9393)
        self.assertEqual(service.julia_host_env, "SPECIFIC_HEAT_WEB_HOST")
        self.assertEqual(service.julia_port_env, "SPECIFIC_HEAT_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "SPECIFIC_HEAT_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "specific-heat-wgl-ready")
        self.assertEqual(service.failed_event, "specific-heat-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:specific-heat")
        self.assertEqual(service.root_marker, "固体比热容")
        self.assertIs(experiment_hub.SERVICES["specific_heat"], service)

    def test_public_prefix_gateway_and_query_are_preserved(self) -> None:
        service = experiment_hub.SPECIFIC_HEAT
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(service, "/cooling"),
                "/agent/experiments/specific-heat/cooling",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(service),
                "https://physics.example/agent/experiments/specific-heat/",
            )

        request = SimpleNamespace(
            path="/agent/experiments/specific-heat/fit",
            query_string="attempt=5&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9393/fit?attempt=5&theme=dark",
            )

    def test_invalid_port_is_rejected(self) -> None:
        with patch.dict(os.environ, {"PHYSICS_SPECIFIC_HEAT_PORT": "65536"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.SPECIFIC_HEAT)

    def test_hub_and_sidebar_expose_four_independent_pages(self) -> None:
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")

        self.assertIn('"固体比热容的测定"', hub_source)
        self.assertIn('"混合法与热量平衡": "/mixing"', hub_source)
        self.assertIn('"冷却修正与热损失": "/cooling"', hub_source)
        self.assertIn('"电热法与能量输入": "/electrical"', hub_source)
        self.assertIn('"线性拟合与不确定度": "/fit"', hub_source)
        self.assertIn('key="specific_heat_experiment_name"', hub_source)
        self.assertIn('key="sidebar_specific_heat"', app_source)
        self.assertIn('visual_experiment_name = "固体比热容的测定"', app_source)
        self.assertIn('visual_experiment_category = "热学实验"', app_source)

    def test_web_contract_has_four_routes_health_and_scaled_pointer_mapping(self) -> None:
        web_source = self._source(
            APP_DIR / "experiments" / "specific_heat" / "web.jl"
        )

        self.assertIn("const FIGURE_WIDTH = 960", web_source)
        self.assertIn("const FIGURE_HEIGHT = 760", web_source)
        self.assertIn('const HEALTH_MARKER = "physics-experiment:specific-heat"', web_source)
        self.assertIn('Bonito.route!(server, "/__physics_health__" => health_app())', web_source)
        for route in ("mixing", "cooling", "electrical", "fit"):
            self.assertIn(f'Bonito.route!(server, "/{route}"', web_source)

        self.assertIn('"pointerdown"', web_source)
        self.assertIn("screen.winscale = baseWinscale * layoutScale", web_source)
        # CLIENT_STATUS_SCRIPT is a Julia string. JavaScript string newlines must
        # therefore be double-escaped, otherwise the browser receives invalid JS.
        self.assertIn(r'\\nWebGL 状态', web_source)
        self.assertIn(r'\\n页面地址', web_source)
        self.assertIn(r'\\n" + event.filename', web_source)


if __name__ == "__main__":
    unittest.main()
