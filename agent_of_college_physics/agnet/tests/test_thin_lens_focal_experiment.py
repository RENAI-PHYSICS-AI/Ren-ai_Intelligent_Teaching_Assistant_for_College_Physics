from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
VARIANT_ROOT = APP_DIR.parent
EXPERIMENT_DIR = APP_DIR / "experiments" / "thin_lens_focal"
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


class ThinLensFocalExperimentTests(unittest.TestCase):
    """Static and physics contract for the thin-lens WGLMakie lab."""

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
            "direct": "direct_figure",
            "autocollimation": "autocollimation_figure",
            "displacement": "displacement_figure",
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

    def test_each_page_has_all_parameter_sliders_and_one_playback_binding(self) -> None:
        for builder in ("direct", "autocollimation", "displacement", "uncertainty"):
            block = re.search(
                rf"function {builder}_figure\(\)(.*?)\nend\n",
                self.source,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(block)
            body = block.group(1)
            self.assertEqual(body.count("add_slider!("), 6)
            self.assertEqual(body.count("bind_playback!("), 1)
            self.assertIn("add_metrics!(", body)
        self.assertIn('label = "播放"', self.source)
        self.assertIn('label = "重置"', self.source)
        self.assertIn('play_button.label[] = playing[] ? "暂停" : "播放"', self.source)

    def test_core_physics_models_and_formulae_are_present(self) -> None:
        for token in (
            "thin_lens_focal",
            "thin_lens_image_distance",
            "direct_model",
            "autocollimation_model",
            "displacement_model",
            "uncertainty_model",
            "principal_shift_mm",
            "returned_axial_shift_mm",
            "measured_displacement",
            "current_fraction",
            "sensitivity_u",
            "combined_u",
            "expanded_u",
        ):
            self.assertIn(token, self.source)
        for expression in (
            "Float64(u)*Float64(v)/(Float64(u)+Float64(v))",
            "Float64(f)*Float64(u)/(Float64(u)-Float64(f))",
            "sqrt(distance^2-4.0*distance*focal)",
            "(distance^2-measured_displacement^2)/(4.0*distance)",
            "current=distance*current_fraction",
            "v^2/(u+v)^2",
            "u^2/(u+v)^2",
            "expanded_u=2.0*combined_u",
        ):
            self.assertIn(expression, self.compact)
        self.assertIn("barplot!", self.source)
        self.assertIn("scatter!", self.source)
        self.assertIn("vlines!", self.source)

    def test_displacement_playback_uses_normalized_position(self) -> None:
        self.assertIn('"透镜位置进度", 0:1:100', self.source)
        self.assertIn("current_fraction = clamp", self.source)
        self.assertIn("current = distance * current_fraction", self.source)
        self.assertNotIn('"当前透镜位置", 0:1:140', self.source)
        self.assertIn("displacement_model(80.0, 15.0, 100.0", self.source)

    def test_browser_health_pointer_and_layout_contract(self) -> None:
        self.assertIn("physics-experiment:thin-lens-focal", self.source)
        self.assertIn("thin-lens-focal-wgl-ready", self.source)
        self.assertIn("thin-lens-focal-wgl-failed", self.source)
        self.assertIn("pointerdown", self.source)
        self.assertIn("baseWinscale * layoutScale", self.source)
        self.assertRegex(
            self.source,
            r"\.thin-lens-focal-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;",
        )

    def test_environment_contract_and_reserved_port(self) -> None:
        self.assertIn('"THIN_LENS_FOCAL_WEB_HOST"', self.source)
        self.assertIn('"THIN_LENS_FOCAL_WEB_PORT", "9399"', self.source)
        self.assertIn('"THIN_LENS_FOCAL_WEB_PROXY_URL"', self.source)
        self.assertIn('"--self-test" in ARGS', self.source)

    def test_windows_and_rocky_experiment_trees_are_identical(self) -> None:
        counterpart = COUNTERPART_ROOT / "agnet" / "experiments" / "thin_lens_focal"
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
