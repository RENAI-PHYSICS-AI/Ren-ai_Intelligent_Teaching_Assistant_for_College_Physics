from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
VARIANT_ROOT = APP_DIR.parent
EXPERIMENT_DIR = APP_DIR / "experiments" / "thermal_conductivity"
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


def _function_block(source: str, function_name: str) -> str:
    start = source.index(f"function {function_name}()")
    next_function = source.find("\nfunction ", start + 1)
    return source[start:] if next_function < 0 else source[start:next_function]


class ThermalConductivityExperimentTests(unittest.TestCase):
    """固体热传导系数 WGLMakie 模块的独立静态与物理契约。"""

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

    def test_four_routes_and_public_builder_names(self) -> None:
        expected = {
            "steady-state": "steady_state_figure",
            "cooling": "cooling_figure",
            "fit": "fit_figure",
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

    def test_each_page_has_one_playback_binding_and_full_reset(self) -> None:
        for builder in (
            "steady_state_figure",
            "cooling_figure",
            "fit_figure",
            "uncertainty_figure",
        ):
            body = _function_block(self.source, builder)
            slider_count = body.count("add_slider!(")
            self.assertGreaterEqual(slider_count, 6, builder)
            self.assertEqual(body.count("bind_playback!("), 1, builder)
            call = re.search(r"bind_playback!\([^\n]+", body)
            self.assertIsNotNone(call, builder)
            self.assertEqual(call.group(0).count("), ("), slider_count - 1, builder)
        self.assertIn('label = "播放"', self.source)
        self.assertIn('label = "重置"', self.source)
        self.assertIn('play_button.label[] = playing[] ? "暂停" : "播放"', self.source)

    def test_fourier_law_cooling_fit_and_uncertainty_models(self) -> None:
        for token in (
            "steady_state_model",
            "cooling_model",
            "fit_model",
            "uncertainty_model",
            "linear_fit",
            "effective_power",
            "disc_k",
            "rod_k",
            "corrected_heat_rate",
            "fitted_k",
            "combined_percent",
            "expanded_uncertainty",
        ):
            self.assertIn(token, self.source)
        for expression in (
            "effective_power=power*(1.0-loss_fraction)",
            "disc_k=effective_power*disc_thickness/(disc_area*delta_temperature)",
            "rod_k=effective_power/(rod_area*rod_gradient)",
            "base_heat_rate=mass*specific_heat*rate_per_second",
            "conductivity=corrected_heat_rate*thickness/(area*(hot-disc))",
            "fitted_k=effective_power/(area*abs(fit.slope))",
            "conductivity=power*length_value/(area*temperature_difference)",
            "combined_percent=sqrt(sum(abs2,components))",
            "expanded_percent=2.0*combined_percent",
        ):
            self.assertIn(expression, self.compact)
        self.assertIn("傅里叶定律", self.source)
        self.assertIn("Lees 圆盘", self.source)
        self.assertIn("barplot!", self.source)
        self.assertIn("hlines!", self.source)

    def test_browser_health_pointer_and_layout_contract(self) -> None:
        self.assertIn("physics-experiment:thermal-conductivity", self.source)
        self.assertIn("thermal-conductivity-wgl-ready", self.source)
        self.assertIn("thermal-conductivity-wgl-failed", self.source)
        self.assertIn("pointerdown", self.source)
        self.assertIn("baseWinscale * layoutScale", self.source)
        self.assertRegex(
            self.source,
            r"\.thermal-conductivity-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;",
        )

    def test_environment_contract_reserved_port_and_self_test(self) -> None:
        self.assertIn('"THERMAL_CONDUCTIVITY_WEB_HOST"', self.source)
        self.assertIn('"THERMAL_CONDUCTIVITY_WEB_PORT", "9401"', self.source)
        self.assertIn('"THERMAL_CONDUCTIVITY_WEB_PROXY_URL"', self.source)
        self.assertIn('"--self-test" in ARGS', self.source)
        self.assertIn("function run_self_test()", self.source)

    def test_windows_and_rocky_experiment_trees_are_identical(self) -> None:
        counterpart = COUNTERPART_ROOT / "agnet" / "experiments" / "thermal_conductivity"
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
