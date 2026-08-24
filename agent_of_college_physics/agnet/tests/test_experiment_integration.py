from __future__ import annotations

import os
import re
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


class ElectronEmExperimentIntegrationTests(unittest.TestCase):
    @staticmethod
    def _electron_source() -> str:
        return (
            APP_DIR / "experiments" / "electron_em" / "web.jl"
        ).read_text(encoding="utf-8")

    @staticmethod
    def _julia_function(source: str, name: str) -> str:
        match = re.search(
            rf"(?ms)^function\s+{re.escape(name)}\([^\n]*\)\s*$.*?(?=^function\s+|\Z)",
            source,
        )
        if match is None:
            raise AssertionError(f"Julia function {name!r} was not found")
        return match.group(0)

    @staticmethod
    def _julia_int_constant(source: str, name: str) -> int:
        match = re.search(
            rf"(?m)^const\s+{re.escape(name)}\s*=\s*(\d+)\s*$",
            source,
        )
        if match is None:
            raise AssertionError(f"Julia integer constant {name!r} was not found")
        return int(match.group(1))

    def test_service_uses_dedicated_port_and_environment(self):
        service = experiment_hub.ELECTRON_EM
        self.assertEqual(service.default_port, 9386)
        self.assertEqual(service.port_env, "PHYSICS_ELECTRON_EM_PORT")
        self.assertEqual(service.julia_port_env, "ELECTRON_EM_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "ELECTRON_EM_WEB_PROXY_URL")
        self.assertEqual(service.identity_marker, "physics-experiment:electron-em")

    def test_service_browser_path_preserves_public_prefix(self):
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(
                    experiment_hub.ELECTRON_EM, "/focus"
                ),
                "/agent/experiments/electron-em/focus",
            )

    def test_invalid_experiment_port_is_rejected(self):
        with patch.dict(os.environ, {"PHYSICS_ELECTRON_EM_PORT": "70000"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.ELECTRON_EM)

    def test_gateway_routes_experiment_and_keeps_query(self):
        request = SimpleNamespace(
            path="/agent/experiments/electron-em/thomson",
            query_string="attempt=42",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9386/thomson?attempt=42",
            )

    def test_julia_service_declares_four_independent_routes(self):
        source = self._electron_source()
        route_pairs = re.findall(
            r'Bonito\.route!\(\s*server\s*,\s*"(/[^"]+)"\s*=>\s*'
            r'experiment_app\(\s*"[^"]+"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\)',
            source,
        )
        routes = dict(route_pairs)
        self.assertEqual(
            routes,
            {
                "/circular": "circular_figure",
                "/helmholtz": "helmholtz_figure",
                "/focus": "focus_figure",
                "/thomson": "thomson_figure",
            },
        )
        self.assertEqual(len(set(routes.values())), 4)
        self.assertIn("physics-experiment:electron-em", source)
        self.assertIn("electron-em-wgl-ready", source)
        self.assertIn("electron-em-wgl-failed", source)
        self.assertIn("blocked_thomson.transmitted", source)

    def test_electron_canvas_does_not_repeat_the_page_heading(self):
        source = self._electron_source()
        base_figure = self._julia_function(source, "base_figure")

        self.assertRegex(base_figure, r"^function\s+base_figure\(\s*\)")
        self.assertNotIn("Label(", base_figure)
        self.assertNotRegex(base_figure, r"\b(?:title|subtitle)\b")

        for builder in (
            "circular_figure",
            "helmholtz_figure",
            "focus_figure",
            "thomson_figure",
        ):
            builder_source = self._julia_function(source, builder)
            base_calls = re.findall(r"\bbase_figure\((.*?)\)", builder_source, re.S)
            self.assertEqual([arguments.strip() for arguments in base_calls], [""])

    def test_electron_layout_tracks_the_real_embedded_viewport(self):
        source = self._electron_source()
        figure_width = self._julia_int_constant(source, "FIGURE_WIDTH")
        figure_height = self._julia_int_constant(source, "FIGURE_HEIGHT")
        base_figure = self._julia_function(source, "base_figure")

        self.assertEqual(figure_width, 960)
        self.assertGreaterEqual(figure_height, 760)
        self.assertRegex(
            base_figure,
            r"Figure\(size\s*=\s*\(FIGURE_WIDTH,\s*FIGURE_HEIGHT\)",
        )
        self.assertRegex(
            source,
            r"\.electron-em-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;"
            r"\s*height:\s*\$\(FIGURE_HEIGHT\)px;",
        )
        self.assertIn("window.visualViewport", source)
        self.assertIn("ResizeObserver(scheduleFit)", source)
        self.assertIn("translate3d(", source)
        self.assertRegex(
            source,
            r"(?s)Math\.min\(.*?availableWidth\s*/\s*\$\(FIGURE_WIDTH\)\s*,"
            r"\s*availableHeight\s*/\s*\$\(FIGURE_HEIGHT\).*?\)",
        )
        self.assertRegex(
            source,
            r"const renderedWidth\s*=\s*\$\(FIGURE_WIDTH\)\s*\*\s*scale;",
        )
        self.assertRegex(
            source,
            r"const renderedHeight\s*=\s*\$\(FIGURE_HEIGHT\)\s*\*\s*scale;",
        )
        self.assertNotIn("Math.max(300, document.documentElement.clientHeight", source)

    def test_electron_css_scale_is_applied_to_wgl_pointer_coordinates(self):
        source = self._electron_source()

        self.assertIn("const syncWGLPointerScale = event =>", source)
        self.assertIn("event.target instanceof HTMLCanvasElement", source)
        self.assertIn("canvas.wglmakie_screen", source)
        self.assertIn("screen.__physicsBaseWinscale = screen.winscale", source)
        self.assertIn("screen.winscale = baseWinscale * layoutScale", source)
        self.assertRegex(
            source,
            r"layoutScale\s*=\s*scale;\s*page\.style\.transform",
        )
        for event_name in ("mousemove", "mousedown", "pointerdown", "pointermove"):
            self.assertIn(f'"{event_name}"', source)
        self.assertRegex(source, r"capture:\s*true")
        restore_delay = re.search(
            r"__physicsPointerScaleTimer\s*=\s*window\.setTimeout\(\(\)\s*=>\s*\{"
            r".*?screen\.winscale\s*=\s*baseWinscale;.*?\},\s*(\d+)\s*\);",
            source,
            re.S,
        )
        self.assertIsNotNone(restore_delay)
        self.assertGreaterEqual(int(restore_delay.group(1)), 80)

    def test_electron_layout_reserves_space_below_controls_and_detail(self):
        source = self._electron_source()
        figure_height = self._julia_int_constant(source, "FIGURE_HEIGHT")
        base_figure = self._julia_function(source, "base_figure")
        add_slider = self._julia_function(source, "add_slider!")
        add_metrics = self._julia_function(source, "add_metrics!")

        padding_match = re.search(r"figure_padding\s*=\s*(\d+)", base_figure)
        self.assertIsNotNone(padding_match)
        figure_padding = int(padding_match.group(1))
        figure_rows = {
            int(row): int(height)
            for row, height in re.findall(
                r"rowsize!\(figure\.layout,\s*(\d+),\s*(\d+)\)",
                base_figure,
            )
        }
        self.assertEqual(set(figure_rows), {1, 2, 3})
        outer_gap_match = re.search(
            r"rowgap!\(figure\.layout,\s*(\d+)\)", base_figure
        )
        self.assertIsNotNone(outer_gap_match)
        outer_gap = int(outer_gap_match.group(1))

        occupied_height = sum(figure_rows.values()) + outer_gap * (
            len(figure_rows) - 1
        )
        layout_slack = figure_height - 2 * figure_padding - occupied_height
        bottom_safe_space = figure_padding + layout_slack
        self.assertGreaterEqual(layout_slack, 16)
        self.assertGreaterEqual(bottom_safe_space, 32)

        metric_rows = {
            int(row): int(height)
            for row, height in re.findall(
                r"rowsize!\(grid,\s*(\d+),\s*(\d+)\)", add_metrics
            )
        }
        self.assertEqual(set(metric_rows), {1, 2})
        self.assertRegex(
            add_metrics,
            r"Label\(grid\[2,\s*1:4\],\s*detail\b",
        )
        metric_gap_match = re.search(r"rowgap!\(grid,\s*(\d+)\)", add_metrics)
        self.assertIsNotNone(metric_gap_match)
        metric_gap = int(metric_gap_match.group(1))
        metric_slack = figure_rows[3] - sum(metric_rows.values()) - metric_gap
        self.assertGreaterEqual(metric_rows[2], 48)
        self.assertGreaterEqual(metric_slack, 20)

        slider_height_match = re.search(
            r"rowsize!\(grid,\s*row,\s*(\d+)\)", add_slider
        )
        slider_gap_match = re.search(r"rowgap!\(grid,\s*(\d+)\)", add_slider)
        self.assertIsNotNone(slider_height_match)
        self.assertIsNotNone(slider_gap_match)
        slider_height = int(slider_height_match.group(1))
        slider_gap = int(slider_gap_match.group(1))
        max_slider_count = max(
            len(re.findall(r"\badd_slider!\(controls,", self._julia_function(source, builder)))
            for builder in (
                "circular_figure",
                "helmholtz_figure",
                "focus_figure",
                "thomson_figure",
            )
        )
        controls_height = (
            max_slider_count * slider_height
            + (max_slider_count - 1) * slider_gap
        )
        self.assertGreaterEqual(figure_rows[2] - controls_height, 16)


if __name__ == "__main__":
    unittest.main()
