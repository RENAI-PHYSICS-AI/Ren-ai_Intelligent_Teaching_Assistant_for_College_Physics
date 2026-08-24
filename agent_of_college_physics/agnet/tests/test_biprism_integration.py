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


class BiprismExperimentIntegrationTests(unittest.TestCase):
    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @classmethod
    def _biprism_source(cls) -> str:
        return cls._source(APP_DIR / "experiments" / "biprism" / "web.jl")

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
    def _julia_number_constant(source: str, name: str) -> float:
        match = re.search(
            rf"(?m)^const\s+{re.escape(name)}\s*=\s*(\d+(?:\.\d+)?)\s*$",
            source,
        )
        if match is None:
            raise AssertionError(f"Julia number constant {name!r} was not found")
        return float(match.group(1))

    @classmethod
    def _julia_int_constant(cls, source: str, name: str) -> int:
        value = cls._julia_number_constant(source, name)
        if not value.is_integer():
            raise AssertionError(f"Julia constant {name!r} is not an integer")
        return int(value)

    def test_service_uses_dedicated_private_upstream(self):
        service = experiment_hub.BIPRISM
        self.assertEqual(service.key, "biprism")
        self.assertEqual(service.default_port, 9388)
        self.assertEqual(service.port_env, "PHYSICS_BIPRISM_PORT")
        self.assertEqual(service.julia_host_env, "BIPRISM_WEB_HOST")
        self.assertEqual(service.julia_port_env, "BIPRISM_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "BIPRISM_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "biprism-wgl-ready")
        self.assertEqual(service.failed_event, "biprism-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:biprism")
        self.assertIn("双棱镜", service.root_marker)
        self.assertIn("biprism", experiment_hub.SERVICES)

    def test_public_prefix_is_preserved_for_iframe_and_bonito(self):
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(
                    experiment_hub.BIPRISM, "/wavelength"
                ),
                "/agent/experiments/biprism/wavelength",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(experiment_hub.BIPRISM),
                "https://physics.example/agent/experiments/biprism/",
            )

    def test_invalid_biprism_port_is_rejected(self):
        with patch.dict(os.environ, {"PHYSICS_BIPRISM_PORT": "70000"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.BIPRISM)

    def test_gateway_routes_biprism_and_keeps_query(self):
        request = SimpleNamespace(
            path="/agent/experiments/biprism/fringes",
            query_string="attempt=42&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9388/fringes?attempt=42&theme=dark",
            )

    def test_hub_and_sidebar_expose_biprism(self):
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")

        for experiment_name in (
            "李萨如图形",
            "声速测量",
            "电子荷质比",
            "光电效应",
            "双棱镜干涉",
            "牛顿环",
        ):
            self.assertIn(f'"{experiment_name}"', hub_source)
        self.assertIn('"分波阵面与虚光源": "/geometry"', hub_source)
        self.assertIn('"钠黄光干涉条纹": "/fringes"', hub_source)
        self.assertIn('"二次成像测间距": "/separation"', hub_source)
        self.assertIn('"波长拟合与误差": "/wavelength"', hub_source)
        self.assertIn('key="sidebar_biprism"', app_source)
        self.assertIn('visual_experiment_name = "双棱镜干涉"', app_source)

    def test_julia_service_declares_four_independent_routes_and_markers(self):
        source = self._biprism_source()
        route_pairs = re.findall(
            r'Bonito\.route!\(\s*server\s*,\s*"(/[^"]+)"\s*=>\s*'
            r'experiment_app\(\s*"[^"]+"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\)',
            source,
        )
        routes = dict(route_pairs)
        self.assertEqual(
            routes,
            {
                "/geometry": "geometry_figure",
                "/fringes": "fringes_figure",
                "/separation": "separation_figure",
                "/wavelength": "wavelength_figure",
            },
        )
        self.assertEqual(len(set(routes.values())), 4)
        self.assertIn("physics-experiment:biprism", source)
        self.assertIn("biprism-wgl-ready", source)
        self.assertIn("biprism-wgl-failed", source)
        self.assertIn('"--self-test"', source)

    def test_sodium_yellow_reference_and_measurement_formulae(self):
        source = self._biprism_source()
        sodium_d2 = self._julia_number_constant(source, "SODIUM_D2_NM")
        sodium_d1 = self._julia_number_constant(source, "SODIUM_D1_NM")
        sodium_reference = self._julia_number_constant(
            source, "SODIUM_REFERENCE_NM"
        )

        self.assertAlmostEqual(sodium_d2, 588.9950, places=4)
        self.assertAlmostEqual(sodium_d1, 589.5924, places=4)
        self.assertAlmostEqual(sodium_reference, 589.3, places=1)
        self.assertLess(sodium_d2, sodium_reference)
        self.assertLess(sodium_reference, sodium_d1)
        self.assertNotIn("632.8", source)

        lens_formula = self._julia_function(source, "lens_separation")
        wavelength_formula = self._julia_function(
            source, "wavelength_from_readings"
        )
        self.assertRegex(
            lens_formula,
            r"return\s+sqrt\(image_separation_1_m\s*\*\s*image_separation_2_m\)",
        )
        self.assertRegex(
            wavelength_formula,
            r"return\s+fringe_spacing_m\s*\*\s*source_separation_m\s*/\s*screen_distance_m",
        )
        self.assertIn("λ=βd/D", source)
        self.assertTrue(
            "d=√(d₁d₂)" in source
            or "√(s大s小)" in source,
            "页面应向学生展示二次成像间距的几何平均公式",
        )

        self_test = self._julia_function(source, "run_self_test")
        self.assertRegex(
            self_test,
            r"isapprox\(ideal\.wavelength_nm,\s*SODIUM_REFERENCE_NM",
        )
        self.assertIn("wavelength_from_readings(", self_test)

    def test_canvas_does_not_repeat_the_page_heading(self):
        source = self._biprism_source()
        base_figure = self._julia_function(source, "base_figure")

        self.assertRegex(base_figure, r"^function\s+base_figure\(\s*\)")
        self.assertNotIn("Label(", base_figure)
        self.assertNotRegex(base_figure, r"\b(?:title|subtitle)\b")

        for builder in (
            "geometry_figure",
            "fringes_figure",
            "separation_figure",
            "wavelength_figure",
        ):
            builder_source = self._julia_function(source, builder)
            base_calls = re.findall(r"\bbase_figure\((.*?)\)", builder_source, re.S)
            self.assertEqual([arguments.strip() for arguments in base_calls], [""])

    def test_layout_tracks_the_real_embedded_viewport(self):
        source = self._biprism_source()
        figure_width = self._julia_int_constant(source, "FIGURE_WIDTH")
        figure_height = self._julia_int_constant(source, "FIGURE_HEIGHT")
        base_figure = self._julia_function(source, "base_figure")

        self.assertEqual(figure_width, 960)
        self.assertGreaterEqual(figure_height, 760)
        self.assertRegex(
            base_figure,
            r"Figure\(\s*size\s*=\s*\(FIGURE_WIDTH,\s*FIGURE_HEIGHT\)",
        )
        self.assertRegex(
            source,
            r"\.biprism-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;"
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

    def test_css_scale_is_applied_to_wgl_pointer_coordinates(self):
        source = self._biprism_source()

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

    def test_layout_reserves_space_below_controls_and_detail(self):
        source = self._biprism_source()
        figure_height = self._julia_int_constant(source, "FIGURE_HEIGHT")
        base_figure = self._julia_function(source, "base_figure")
        add_slider = self._julia_function(source, "add_slider!")
        add_metrics = self._julia_function(source, "add_metrics!")

        padding_match = re.search(
            r"figure_padding\s*=\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
            base_figure,
        )
        self.assertIsNotNone(padding_match)
        left_padding, right_padding, bottom_padding, top_padding = (
            int(value) for value in padding_match.groups()
        )
        self.assertEqual(left_padding, right_padding)
        self.assertGreaterEqual(top_padding, 30)

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
        layout_slack = (
            figure_height - bottom_padding - top_padding - occupied_height
        )
        self.assertGreaterEqual(layout_slack, 16)
        self.assertGreaterEqual(bottom_padding + layout_slack, 32)

        metric_rows = {
            int(row): int(height)
            for row, height in re.findall(
                r"rowsize!\(grid,\s*(\d+),\s*(\d+)\)", add_metrics
            )
        }
        self.assertEqual(set(metric_rows), {1, 2})
        self.assertRegex(add_metrics, r"Label\(\s*grid\[2,\s*1:4\],\s*detail\b")
        metric_gap_match = re.search(r"rowgap!\(grid,\s*(\d+)\)", add_metrics)
        self.assertIsNotNone(metric_gap_match)
        metric_slack = (
            figure_rows[3]
            - sum(metric_rows.values())
            - int(metric_gap_match.group(1))
        )
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
            len(
                re.findall(
                    r"\badd_slider!\(controls,",
                    self._julia_function(source, builder),
                )
            )
            for builder in (
                "geometry_figure",
                "fringes_figure",
                "separation_figure",
                "wavelength_figure",
            )
        )
        controls_height = (
            max_slider_count * slider_height
            + (max_slider_count - 1) * slider_gap
        )
        self.assertGreaterEqual(figure_rows[2] - controls_height, 16)


if __name__ == "__main__":
    unittest.main()
