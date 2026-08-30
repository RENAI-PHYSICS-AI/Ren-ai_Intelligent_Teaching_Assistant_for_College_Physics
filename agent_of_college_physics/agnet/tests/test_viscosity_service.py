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


class ViscosityServiceTests(unittest.TestCase):
    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_service_contract_uses_private_port_9392(self) -> None:
        service = experiment_hub.VISCOSITY
        self.assertEqual(service.key, "viscosity")
        self.assertEqual(service.title, "粘滞系数测定实验")
        self.assertEqual(service.project_dir, APP_DIR / "experiments" / "viscosity")
        self.assertEqual(service.web_path, service.project_dir / "web.jl")
        self.assertEqual(service.port_env, "PHYSICS_VISCOSITY_PORT")
        self.assertEqual(service.default_port, 9392)
        self.assertEqual(service.julia_host_env, "VISCOSITY_WEB_HOST")
        self.assertEqual(service.julia_port_env, "VISCOSITY_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "VISCOSITY_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "viscosity-wgl-ready")
        self.assertEqual(service.failed_event, "viscosity-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:viscosity")
        self.assertEqual(service.root_marker, "粘滞系数")
        self.assertIs(experiment_hub.SERVICES["viscosity"], service)

    def test_public_prefix_gateway_and_query_are_preserved(self) -> None:
        service = experiment_hub.VISCOSITY
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(service, "/correction"),
                "/agent/experiments/viscosity/correction",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(service),
                "https://physics.example/agent/experiments/viscosity/",
            )

        request = SimpleNamespace(
            path="/agent/experiments/viscosity/fit",
            query_string="attempt=12&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9392/fit?attempt=12&theme=dark",
            )

    def test_invalid_port_is_rejected(self) -> None:
        with patch.dict(os.environ, {"PHYSICS_VISCOSITY_PORT": "0"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.VISCOSITY)

    def test_hub_and_sidebar_expose_four_independent_pages(self) -> None:
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")

        self.assertIn('"粘滞系数测定"', hub_source)
        self.assertIn('"斯托克斯定律与受力平衡": "/stokes"', hub_source)
        self.assertIn('"终端速度与落球计时": "/terminal"', hub_source)
        self.assertIn('"容器壁面修正": "/correction"', hub_source)
        self.assertIn('"多球拟合与不确定度": "/fit"', hub_source)
        self.assertIn('key="viscosity_experiment_name"', hub_source)
        self.assertIn('key="sidebar_viscosity"', app_source)
        self.assertIn('visual_experiment_name = "粘滞系数测定"', app_source)


if __name__ == "__main__":
    unittest.main()
