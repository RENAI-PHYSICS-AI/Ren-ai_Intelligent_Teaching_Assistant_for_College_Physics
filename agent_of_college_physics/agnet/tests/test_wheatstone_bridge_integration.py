from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
VARIANT_ROOT = APP_DIR.parent
EXPERIMENT_DIR = APP_DIR / "experiments" / "wheatstone_bridge"
WEB_PATH = EXPERIMENT_DIR / "web.jl"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"
COUNTERPART_EXPERIMENT = (
    COUNTERPART_ROOT / "agnet" / "experiments" / "wheatstone_bridge"
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class WheatstoneBridgeExperimentTests(unittest.TestCase):
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
                "/principle": "principle_figure",
                "/balance": "balance_figure",
                "/sensitivity": "sensitivity_figure",
                "/fit": "fit_figure",
            },
        )
        self.assertIn("physics-experiment:wheatstone-bridge", self.source)
        self.assertIn("wheatstone-bridge-wgl-ready", self.source)
        self.assertIn("wheatstone-bridge-wgl-failed", self.source)
        self.assertIn('"--self-test"', self.source)
        self.assertRegex(
            self.source,
            r'get\(ENV,\s*"WHEATSTONE_BRIDGE_WEB_HOST",\s*"127\.0\.0\.1"\)',
        )
        self.assertRegex(
            self.source,
            r'get\(ENV,\s*"WHEATSTONE_BRIDGE_WEB_PORT",\s*"9396"\)',
        )
        self.assertIn("WHEATSTONE_BRIDGE_WEB_PROXY_URL", self.source)

    def test_all_pages_have_sliders_playback_and_reset(self) -> None:
        for figure_name, next_name in (
            ("principle_figure", "balance_model"),
            ("balance_figure", "sensitivity_model"),
            ("sensitivity_figure", "fit_model"),
            ("fit_figure", "run_self_test"),
        ):
            start = self.source.index(f"function {figure_name}()")
            end = self.source.index(f"function {next_name}", start)
            body = self.source[start:end]
            self.assertGreaterEqual(
                body.count("add_slider!("),
                6,
                f"{figure_name} must expose at least six parameter sliders",
            )
            self.assertIn("bind_playback!(", body)
        helper_start = self.source.index("function bind_playback!")
        helper_end = self.source.index("function linear_fit", helper_start)
        helper = self.source[helper_start:helper_end]
        for label in ('label = "播放"', '"暂停"', 'label = "重置"'):
            self.assertIn(label, helper)
        self.assertIn('play_button.label[] = "播放"', helper)
        self.assertIn("set_close_to!", helper)

    def test_bridge_physics_and_measurement_boundaries_are_explicit(self) -> None:
        for function_name in (
            "detector_current",
            "bridge_model",
            "balance_model",
            "sensitivity_model",
            "fit_model",
        ):
            self.assertRegex(
                self.source,
                re.compile(rf"^function\s+{function_name}\b", re.MULTILINE),
            )
        compact = re.sub(r"\s+", "", self.source)
        for formula in (
            "inferred_unknown=Float64(q)*Float64(standard)/Float64(p)",
            "parallel_resistance(p,q)+parallel_resistance(standard,unknown)",
            "open_voltage/(Float64(galvanometer)+thevenin_resistance)",
            "R=Rₓ(P/Q)+r₀",
        ):
            self.assertIn(formula, compact)
        for concept in (
            "零电流平衡",
            "戴维南电阻",
            "粗调",
            "细调",
            "接触/引线电阻",
            "检流计分辨力",
            "不确定度",
            "自热",
            "残差",
        ):
            self.assertIn(concept, self.source)

    def test_canvas_scaling_and_pointer_compensation_are_preserved(self) -> None:
        self.assertIn("const FIGURE_WIDTH = 960", self.source)
        self.assertIn("const FIGURE_HEIGHT = 760", self.source)
        self.assertRegex(
            self.source,
            r"\.wheatstone-bridge-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;"
            r"[^}]*height:\s*\$\(FIGURE_HEIGHT\)px;",
        )
        self.assertIn("window.visualViewport", self.source)
        self.assertIn("ResizeObserver(scheduleFit)", self.source)
        self.assertIn("const syncWGLPointerScale = event =>", self.source)
        self.assertIn("event.target instanceof HTMLCanvasElement", self.source)
        self.assertIn("screen.winscale = baseWinscale * layoutScale", self.source)
        for event_name in ("mousemove", "mousedown", "pointerdown", "pointermove"):
            self.assertIn(f'"{event_name}"', self.source)
        self.assertRegex(self.source, r"capture:\s*true")

    def test_two_platform_trees_are_byte_identical(self) -> None:
        self.assertTrue(COUNTERPART_EXPERIMENT.is_dir())
        for name in ("Project.toml", "Manifest.toml", "web.jl"):
            self.assertEqual(
                _sha256(EXPERIMENT_DIR / name),
                _sha256(COUNTERPART_EXPERIMENT / name),
                name,
            )


if __name__ == "__main__":
    unittest.main()
