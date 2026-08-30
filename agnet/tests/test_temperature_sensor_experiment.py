from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
VARIANT_ROOT = APP_DIR.parent
EXPERIMENT_DIR = APP_DIR / "experiments" / "temperature_sensor"
WEB_PATH = EXPERIMENT_DIR / "web.jl"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class TemperatureSensorExperimentTests(unittest.TestCase):
    """Static and physics contract for the WGLMakie temperature-sensor lab."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WEB_PATH.read_text(encoding="utf-8")
        cls.compact = re.sub(r"\s+", "", cls.source)

    def test_is_self_contained_julia_project(self) -> None:
        project = (EXPERIMENT_DIR / "Project.toml").read_text(encoding="utf-8")
        manifest = EXPERIMENT_DIR / "Manifest.toml"
        self.assertIn('Bonito = "824d6782-a2ef-11e9-3a09-e5662e0c26f8"', project)
        self.assertIn('WGLMakie = "276b4fcb-3e11-5398-bf8b-a0c2d153d008"', project)
        self.assertIn('julia = "1.10"', project)
        self.assertTrue(manifest.is_file())
        self.assertGreater(manifest.stat().st_size, 40_000)

    def test_four_routes_and_builders_are_registered(self) -> None:
        expected = {
            "calibration": "calibration_figure",
            "response": "response_figure",
            "bridge": "bridge_figure",
            "uncertainty": "uncertainty_figure",
        }
        for route, builder in expected.items():
            self.assertIn(f"function {builder}()", self.source)
            self.assertRegex(
                self.source,
                rf'Bonito\.route!\(server,\s*"/{route}"\s*=>\s*experiment_app\([^\n]+{builder}\)\)',
            )
            self.assertIn(f'"./{route}"', self.source)
        self.assertIn('Bonito.route!(server, "/__physics_health__"', self.source)
        self.assertIn('Bonito.route!(server, "/" => index_app())', self.source)

    def test_every_page_has_sliders_playback_and_reset(self) -> None:
        for builder in ("calibration", "response", "bridge", "uncertainty"):
            block = re.search(
                rf"function {builder}_figure\(\)(.*?)\nend\n",
                self.source,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(block)
            body = block.group(1)
            self.assertGreaterEqual(body.count("add_slider!("), 6)
            self.assertIn("bind_playback!(", body)
            self.assertIn("add_metrics!(", body)
        self.assertIn('label = "播放"', self.source)
        self.assertIn('label = "重置"', self.source)
        self.assertIn('play_button.label[] = playing[] ? "暂停" : "播放"', self.source)

    def test_core_models_and_error_visuals_are_present(self) -> None:
        for token in (
            "pt100_resistance",
            "pt100_temperature",
            "pt100_sensitivity",
            "calibration_model",
            "response_model",
            "bridge_model",
            "uncertainty_model",
            "linear_fit",
            "temperature_errors",
            "residual_heating",
            "residual_cooling",
            "combined_u_c",
            "expanded_u_c",
        ):
            self.assertIn(token, self.source)
        self.assertIn("barplot!", self.source)
        self.assertIn("hlines!", self.source)
        self.assertIn("scatter!", self.source)

    def test_physics_formula_contract(self) -> None:
        for expression in (
            "Float64(r0)*(1.0+Float64(alpha)*Float64(t)+Float64(beta)*Float64(t)^2)",
            "tb.+(t0-tb).*exp.(-curve_times./tau)",
            "fitted_tau=-1.0/fit.slope",
            "sensor_branch=nominal_resistance+2.0*lead",
            "self_heating_mw=1000.0*current_a^2*nominal_resistance",
            "combined_u_c=sqrt(sum(abs2,components))",
            "expanded_u_c=2.0*combined_u_c",
        ):
            self.assertIn(expression, self.compact)
        self.assertIn("PT100_R0 = 100.0", self.source)
        self.assertIn("PT100_ALPHA = 3.9083e-3", self.source)
        self.assertIn("PT100_BETA = -5.775e-7", self.source)

    def test_browser_health_pointer_and_layout_contract(self) -> None:
        self.assertIn("physics-experiment:temperature-sensor", self.source)
        self.assertIn("temperature-sensor-wgl-ready", self.source)
        self.assertIn("temperature-sensor-wgl-failed", self.source)
        self.assertIn("pointerdown", self.source)
        self.assertIn("baseWinscale * layoutScale", self.source)
        self.assertRegex(
            self.source,
            r"\.temperature-sensor-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;",
        )

    def test_environment_contract_and_reserved_port(self) -> None:
        self.assertIn('"TEMPERATURE_SENSOR_WEB_HOST"', self.source)
        self.assertIn('"TEMPERATURE_SENSOR_WEB_PORT", "9395"', self.source)
        self.assertIn('"TEMPERATURE_SENSOR_WEB_PROXY_URL"', self.source)
        self.assertIn('"--self-test" in ARGS', self.source)

    def test_windows_and_rocky_experiment_trees_are_identical(self) -> None:
        counterpart = COUNTERPART_ROOT / "agnet" / "experiments" / "temperature_sensor"
        if not counterpart.is_dir():
            self.skipTest("counterpart tree is not present")
        actual = {
            path.relative_to(EXPERIMENT_DIR).as_posix(): _sha256(path)
            for path in EXPERIMENT_DIR.rglob("*")
            if path.is_file()
        }
        expected = {
            path.relative_to(counterpart).as_posix(): _sha256(path)
            for path in counterpart.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
