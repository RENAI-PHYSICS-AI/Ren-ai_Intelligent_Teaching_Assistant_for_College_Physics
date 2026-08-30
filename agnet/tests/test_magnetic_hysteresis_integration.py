from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
VARIANT_ROOT = APP_DIR.parent
EXPERIMENT_DIR = APP_DIR / "experiments" / "magnetic_hysteresis"
WEB_PATH = EXPERIMENT_DIR / "web.jl"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"
COUNTERPART_EXPERIMENT = (
    COUNTERPART_ROOT / "agnet" / "experiments" / "magnetic_hysteresis"
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MagneticHysteresisExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = _source(WEB_PATH)

    def test_reproducible_julia_environment_exists(self) -> None:
        project = _source(EXPERIMENT_DIR / "Project.toml")
        manifest = EXPERIMENT_DIR / "Manifest.toml"
        self.assertIn('Bonito = "824d6782-a2ef-11e9-3a09-e5662e0c26f8"', project)
        self.assertIn('WGLMakie = "276b4fcb-3e11-5398-bf8b-a0c2d153d008"', project)
        self.assertIn('julia = "1.10"', project)
        self.assertTrue(manifest.is_file())
        self.assertGreater(manifest.stat().st_size, 10_000)

    def test_four_independent_routes_and_identity_markers(self) -> None:
        route_pairs = re.findall(
            r'Bonito\.route!\(\s*server\s*,\s*"(/[^"]+)"\s*=>\s*'
            r'experiment_app\(\s*"[^"]+"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\)',
            self.source,
        )
        self.assertEqual(
            dict(route_pairs),
            {
                "/loop": "loop_figure",
                "/apparatus": "apparatus_figure",
                "/demagnetization": "demagnetization_figure",
                "/fit": "fit_figure",
            },
        )
        self.assertIn("physics-experiment:magnetic-hysteresis", self.source)
        self.assertIn("magnetic-hysteresis-wgl-ready", self.source)
        self.assertIn("magnetic-hysteresis-wgl-failed", self.source)
        self.assertIn('"--self-test"', self.source)
        self.assertRegex(
            self.source,
            r'get\(ENV,\s*"MAGNETIC_HYSTERESIS_WEB_PORT",\s*"9398"\)',
        )

    def test_every_page_has_parameter_controls_playback_and_full_reset(self) -> None:
        boundaries = (
            ("loop_figure", "apparatus_model", 5),
            ("apparatus_figure", "demagnetization_model", 6),
            ("demagnetization_figure", "loss_model", 5),
            ("fit_figure", "run_self_test", 6),
        )
        for figure_name, next_name, slider_count in boundaries:
            start = self.source.index(f"function {figure_name}()")
            end = self.source.index(f"function {next_name}", start)
            body = self.source[start:end]
            self.assertEqual(body.count("add_slider!("), slider_count, figure_name)
            self.assertEqual(body.count("bind_playback!("), 1, figure_name)
            binding = re.search(r"bind_playback!\([^\n]+\)", body)
            self.assertIsNotNone(binding, figure_name)
            # One opening parenthesis belongs to bind_playback! itself; each
            # controlled slider must also appear once in the reset tuple list.
            self.assertEqual(binding.group(0).count("("), slider_count + 1)

        helper_start = self.source.index("function bind_playback!")
        helper_end = self.source.index("function loop_curve", helper_start)
        helper = self.source[helper_start:helper_end]
        for required in (
            'label = "\u64ad\u653e"',
            'label = "\u91cd\u7f6e"',
            '"\u6682\u505c"',
            'play_button.label[] = "\u64ad\u653e"',
            "generation[] += 1",
            "@async begin",
            "for (slider, value) in reset_values",
            "set_close_to!(slider, value)",
        ):
            self.assertIn(required, helper)

    def test_physics_models_cover_measurement_demagnetization_and_loss(self) -> None:
        for function_name in (
            "loop_curve",
            "apparatus_model",
            "demagnetization_model",
            "loss_model",
        ):
            self.assertRegex(
                self.source,
                re.compile(rf"^function\s+{function_name}\b", re.MULTILINE),
            )
        for concept in (
            "\u77eb\u987d\u529b",
            "\u5269\u78c1",
            "RC \u79ef\u5206",
            "\u793a\u6ce2\u5668 X-Y",
            "\u4ea4\u6d41\u9000\u78c1",
            "Steinmetz",
            "\u78c1\u6ede\u635f\u8017",
            "\u4e0d\u786e\u5b9a\u5ea6",
        ):
            self.assertIn(concept, self.source)

    def test_two_platform_experiment_trees_are_byte_identical(self) -> None:
        self.assertTrue(COUNTERPART_EXPERIMENT.is_dir())
        for name in ("Project.toml", "Manifest.toml", "web.jl"):
            self.assertEqual(
                _sha256(EXPERIMENT_DIR / name),
                _sha256(COUNTERPART_EXPERIMENT / name),
                name,
            )


if __name__ == "__main__":
    unittest.main()
