from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import experiment_hub
import gateway


class RotationalInertiaServiceTests(unittest.TestCase):
    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_service_contract_uses_private_port_9391(self):
        service = experiment_hub.ROTATIONAL_INERTIA
        self.assertEqual(service.key, "rotational_inertia")
        self.assertEqual(service.title, "转动惯量测定实验")
        self.assertEqual(service.project_dir, APP_DIR / "experiments" / "rotational_inertia")
        self.assertEqual(service.web_path, service.project_dir / "web.jl")
        self.assertEqual(service.port_env, "PHYSICS_ROTATIONAL_INERTIA_PORT")
        self.assertEqual(service.default_port, 9391)
        self.assertEqual(service.julia_host_env, "ROTATIONAL_INERTIA_WEB_HOST")
        self.assertEqual(service.julia_port_env, "ROTATIONAL_INERTIA_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "ROTATIONAL_INERTIA_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "rotational-inertia-wgl-ready")
        self.assertEqual(service.failed_event, "rotational-inertia-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:rotational-inertia")
        self.assertEqual(service.root_marker, "转动惯量")
        self.assertIs(experiment_hub.SERVICES["rotational_inertia"], service)

    def test_public_prefix_gateway_and_query_are_preserved(self):
        service = experiment_hub.ROTATIONAL_INERTIA
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(service, "/parallel-axis"),
                "/agent/experiments/rotational-inertia/parallel-axis",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(service),
                "https://physics.example/agent/experiments/rotational-inertia/",
            )

        request = SimpleNamespace(
            path="/agent/experiments/rotational-inertia/pendulum-fit",
            query_string="attempt=12&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9391/pendulum-fit?attempt=12&theme=dark",
            )

    def test_invalid_port_is_rejected(self):
        with patch.dict(os.environ, {"PHYSICS_ROTATIONAL_INERTIA_PORT": "0"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.ROTATIONAL_INERTIA)

    def test_hub_and_sidebar_expose_four_independent_pages(self):
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")

        self.assertIn('"转动惯量"', hub_source)
        self.assertIn('"扭摆法测转动惯量": "/torsion"', hub_source)
        self.assertIn('"三线摆法测转动惯量": "/trifilar"', hub_source)
        self.assertIn('"平行轴定理验证": "/parallel-axis"', hub_source)
        self.assertIn('"摆动周期拟合与不确定度": "/pendulum-fit"', hub_source)
        self.assertIn('key="rotational_inertia_experiment_name"', hub_source)
        self.assertIn('key="sidebar_rotational_inertia"', app_source)
        self.assertIn('visual_experiment_name = "转动惯量"', app_source)

    def test_rocky_scripts_and_example_config_cover_lifecycle(self):
        manage_path = PROJECT_ROOT / "manage.sh"
        install_path = PROJECT_ROOT / "install.sh"
        env_path = PROJECT_ROOT / "physics-assistant.env.example"
        if not (manage_path.exists() and install_path.exists() and env_path.exists()):
            self.skipTest("Windows source tree has no standalone Rocky lifecycle scripts")

        manage_source = self._source(manage_path)
        install_source = self._source(install_path)
        env_source = self._source(env_path)
        self.assertIn('PHYSICS_ROTATIONAL_INERTIA_PORT="${PHYSICS_ROTATIONAL_INERTIA_PORT:-9391}"', manage_source)
        self.assertIn("experiments/rotational_inertia/web.jl", manage_source)
        self.assertIn("physics-experiment:rotational-inertia", manage_source)
        self.assertIn("/experiments/rotational-inertia/__physics_health__", manage_source)
        self.assertIn("rotational_inertia.log", install_source)
        self.assertIn("young_modulus rotational_inertia", install_source)
        self.assertIn("PHYSICS_ROTATIONAL_INERTIA_PORT=9391", env_source)
        self.assertIn("PHYSICS_ROTATIONAL_INERTIA_UPSTREAM=http://127.0.0.1:9391", env_source)


if __name__ == "__main__":
    unittest.main()
