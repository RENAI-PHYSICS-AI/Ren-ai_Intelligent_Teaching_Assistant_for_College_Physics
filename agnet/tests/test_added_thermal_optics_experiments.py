from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import experiment_hub
import gateway


CASES = (
    (experiment_hub.GAS_GAMMA, "gas_gamma", "gas-gamma", 9402),
    (experiment_hub.GRATING_INTERFERENCE, "grating_interference", "grating-interference", 9403),
    (experiment_hub.LIGHT_POLARIZATION, "light_polarization", "light-polarization", 9404),
    (experiment_hub.MICHELSON_WAVELENGTH, "michelson_wavelength", "michelson-wavelength", 9405),
)


class AddedThermalOpticsExperimentTests(unittest.TestCase):
    def test_shared_server_uses_bonito_42_route_api(self) -> None:
        shared = (APP_DIR / "experiments" / "parameter_lab.jl").read_text(encoding="utf-8")
        self.assertIn("Bonito.route!(server, path => app)", shared)
        self.assertNotIn("Bonito.HTTPServer.start(server, routes", shared)

    def test_shared_template_configures_a_verified_cjk_font(self) -> None:
        shared = (APP_DIR / "experiments" / "parameter_lab.jl").read_text(encoding="utf-8")
        self.assertIn("font_supports_cjk", shared)
        self.assertIn('get(ENV, "PHYSICS_CJK_FONT", "")', shared)
        self.assertIn("configure_parameter_lab_theme!()", shared)

    def test_shared_template_uses_the_embed_message_contract(self) -> None:
        shared = (APP_DIR / "experiments" / "parameter_lab.jl").read_text(encoding="utf-8")
        self.assertIn("send('$(LAB_SPEC.ready_event)'", shared)
        self.assertIn("send('$(LAB_SPEC.failed_event)'", shared)
        self.assertNotIn("type:'physics-experiment-status'", shared)

    def test_shared_template_has_mature_transport_and_apparatus_views(self) -> None:
        shared = (APP_DIR / "experiments" / "parameter_lab.jl").read_text(encoding="utf-8")
        for label in ('label = "播放"', 'label = "单步"', 'label = "复位"'):
            self.assertIn(label, shared)
        for helper in (
            "draw_gas_apparatus!",
            "draw_grating_apparatus!",
            "draw_polarization_apparatus!",
            "draw_michelson_apparatus!",
        ):
            self.assertIn(helper, shared)
        self.assertIn("load_packaged_wgl_shaders!()", shared)
        self.assertIn("syncPointer", shared)

    def test_service_gateway_and_four_page_contracts(self) -> None:
        for service, key, slug, port in CASES:
            with self.subTest(key=key):
                self.assertIs(experiment_hub.SERVICES[key], service)
                self.assertEqual(service.default_port, port)
                self.assertEqual(gateway.EXPERIMENT_UPSTREAMS[f"/experiments/{slug}"], f"http://127.0.0.1:{port}")
                source = service.web_path.read_text(encoding="utf-8")
                self.assertEqual(source.count('"=>(title="'), 4)
                self.assertIn(service.identity_marker, source)
                self.assertIn(f'failed_event="{service.failed_event}"', source)
                self.assertIn("reference=", source)
                self.assertTrue((service.project_dir / "Project.toml").is_file())


if __name__ == "__main__":
    unittest.main()
