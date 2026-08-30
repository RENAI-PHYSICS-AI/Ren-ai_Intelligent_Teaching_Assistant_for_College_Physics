from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import experiment_hub


class MagneticHysteresisServiceTests(unittest.TestCase):
    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_service_contract_uses_private_port_9398(self) -> None:
        service = experiment_hub.MAGNETIC_HYSTERESIS
        self.assertEqual(service.key, "magnetic_hysteresis")
        self.assertEqual(service.title, "\u94c1\u78c1\u6ede\u56de\u7ebf\u6d4b\u5b9a\u4e0e\u89c2\u5bdf\u5b9e\u9a8c")
        self.assertEqual(
            service.project_dir,
            APP_DIR / "experiments" / "magnetic_hysteresis",
        )
        self.assertEqual(service.web_path, service.project_dir / "web.jl")
        self.assertEqual(service.port_env, "PHYSICS_MAGNETIC_HYSTERESIS_PORT")
        self.assertEqual(service.default_port, 9398)
        self.assertEqual(service.julia_host_env, "MAGNETIC_HYSTERESIS_WEB_HOST")
        self.assertEqual(service.julia_port_env, "MAGNETIC_HYSTERESIS_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "MAGNETIC_HYSTERESIS_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "magnetic-hysteresis-wgl-ready")
        self.assertEqual(service.failed_event, "magnetic-hysteresis-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:magnetic-hysteresis")
        self.assertEqual(service.root_marker, "\u94c1\u78c1\u6ede\u56de\u7ebf")
        self.assertIs(experiment_hub.SERVICES["magnetic_hysteresis"], service)

    def test_public_browser_path_and_proxy_url_are_stable(self) -> None:
        service = experiment_hub.MAGNETIC_HYSTERESIS
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(service, "/loop"),
                "/agent/experiments/magnetic-hysteresis/loop",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(service),
                "https://physics.example/agent/experiments/magnetic-hysteresis/",
            )

    def test_invalid_port_is_rejected(self) -> None:
        with patch.dict(os.environ, {"PHYSICS_MAGNETIC_HYSTERESIS_PORT": "65536"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.MAGNETIC_HYSTERESIS)

    def test_hub_and_sidebar_expose_all_four_pages(self) -> None:
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")
        for fragment in (
            '"\u94c1\u78c1\u6ede\u56de\u7ebf\u6d4b\u5b9a\u4e0e\u89c2\u5bdf"',
            '"\u57fa\u672c\u78c1\u6ede\u56de\u7ebf\u4e0e\u7279\u5f81\u91cf": "/loop"',
            '"\u793a\u6ce2\u5668\u6cd5\u4e0e\u79ef\u5206\u5668\u6807\u5b9a": "/apparatus"',
            '"\u4ea4\u6d41\u9000\u78c1\u4e0e\u5269\u78c1\u8870\u51cf": "/demagnetization"',
            '"\u635f\u8017\u5206\u79bb\u4e0e\u4e0d\u786e\u5b9a\u5ea6": "/fit"',
            'key="magnetic_hysteresis_experiment_name"',
        ):
            self.assertIn(fragment, hub_source)
        self.assertIn('key="sidebar_magnetic_hysteresis"', app_source)
        self.assertIn(
            'visual_experiment_name = "\u94c1\u78c1\u6ede\u56de\u7ebf\u6d4b\u5b9a\u4e0e\u89c2\u5bdf"',
            app_source,
        )
        self.assertIn('visual_experiment_category = "\u7535\u78c1\u5b9e\u9a8c"', app_source)


if __name__ == "__main__":
    unittest.main()
