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


class NewtonRingsIntegrationTests(unittest.TestCase):
    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @classmethod
    def _julia_source(cls) -> str:
        return cls._source(APP_DIR / "experiments" / "newton_rings" / "web.jl")

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
    def _number_constant(source: str, name: str) -> float:
        match = re.search(
            rf"(?m)^const\s+{re.escape(name)}\s*=\s*(\d+(?:\.\d+)?)\s*$",
            source,
        )
        if match is None:
            raise AssertionError(f"Julia number constant {name!r} was not found")
        return float(match.group(1))

    def test_service_uses_its_own_loopback_port(self):
        service = experiment_hub.NEWTON_RINGS
        self.assertEqual(service.key, "newton_rings")
        self.assertEqual(service.default_port, 9389)
        self.assertEqual(service.port_env, "PHYSICS_NEWTON_RINGS_PORT")
        self.assertEqual(service.julia_host_env, "NEWTON_RINGS_WEB_HOST")
        self.assertEqual(service.julia_port_env, "NEWTON_RINGS_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "NEWTON_RINGS_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "newton-rings-wgl-ready")
        self.assertEqual(service.failed_event, "newton-rings-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:newton-rings")
        self.assertEqual(service.root_marker, "牛顿环")
        self.assertIn("newton_rings", experiment_hub.SERVICES)

    def test_public_prefix_and_gateway_route_are_consistent(self):
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(
                    experiment_hub.NEWTON_RINGS, "/measurement"
                ),
                "/agent/experiments/newton-rings/measurement",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(experiment_hub.NEWTON_RINGS),
                "https://physics.example/agent/experiments/newton-rings/",
            )

        request = SimpleNamespace(
            path="/agent/experiments/newton-rings/difference",
            query_string="theme=dark&attempt=7",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9389/difference?theme=dark&attempt=7",
            )

    def test_invalid_newton_rings_port_is_rejected(self):
        with patch.dict(os.environ, {"PHYSICS_NEWTON_RINGS_PORT": "0"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.NEWTON_RINGS)

    def test_launcher_prefers_installed_julia_110_channel(self):
        probe = SimpleNamespace(
            returncode=0,
            stdout="julia version 1.10.10",
            stderr="",
        )
        with (
            patch.dict(
                os.environ,
                {"PHYSICS_JULIA_EXE": "", "PHYSICS_JULIA_CHANNEL": ""},
            ),
            patch.object(experiment_hub.shutil, "which", return_value="julia.exe"),
            patch.object(experiment_hub.subprocess, "run", return_value=probe),
        ):
            command = experiment_hub._julia_command(
                experiment_hub.NEWTON_RINGS
            )
        self.assertEqual(command[:2], ["julia.exe", "+1.10.10"])
        self.assertIn("--no-instantiate", command)

    def test_explicit_julia_executable_stays_authoritative(self):
        configured = str(Path(f"{chr(67)}:/") / "Julia-1.10" / "bin" / "julia.exe")
        with (
            patch.dict(
                os.environ,
                {
                    "PHYSICS_JULIA_EXE": configured,
                    "PHYSICS_JULIA_CHANNEL": "release",
                },
            ),
            patch.object(experiment_hub.subprocess, "run") as run,
        ):
            command = experiment_hub._julia_command(
                experiment_hub.NEWTON_RINGS
            )
        self.assertEqual(command[0], configured)
        self.assertNotIn("+release", command)
        run.assert_not_called()

    def test_hub_and_sidebar_expose_the_course_workflow(self):
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")

        self.assertIn('"牛顿环"', hub_source)
        self.assertIn('"等厚干涉与环纹": "/formation"', hub_source)
        self.assertIn('"读数显微镜测量": "/measurement"', hub_source)
        self.assertIn('"逐差法求曲率半径": "/difference"', hub_source)
        self.assertIn('"线性拟合与误差": "/fit"', hub_source)
        self.assertIn('key="sidebar_newton_rings"', app_source)
        self.assertIn('visual_experiment_name = "牛顿环"', app_source)

    def test_julia_service_declares_four_independent_routes(self):
        source = self._julia_source()
        route_pairs = re.findall(
            r'Bonito\.route!\(\s*server\s*,\s*"(/[^"]+)"\s*=>\s*'
            r'experiment_app\(\s*"[^"]+"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\)',
            source,
        )
        routes = dict(route_pairs)
        self.assertEqual(
            routes,
            {
                "/formation": "formation_figure",
                "/measurement": "measurement_figure",
                "/difference": "difference_figure",
                "/fit": "fit_figure",
            },
        )
        self.assertEqual(len(set(routes.values())), 4)
        self.assertIn("physics-experiment:newton-rings", source)
        self.assertIn("newton-rings-wgl-ready", source)
        self.assertIn("newton-rings-wgl-failed", source)
        self.assertIn('"--self-test"', source)

    def test_course_constants_and_measurement_order_match_the_local_manual(self):
        source = self._julia_source()
        self.assertAlmostEqual(
            self._number_constant(source, "SODIUM_REFERENCE_NM"), 589.3, places=1
        )
        self.assertEqual(self._number_constant(source, "COURSE_DIFFERENCE"), 15)
        self.assertRegex(
            source,
            r"const\s+COURSE_ORDERS\s*=\s*\(5,\s*10,\s*15,\s*20,\s*25,\s*30\)",
        )
        measurement = self._julia_function(source, "measurement_model")
        self.assertIn("vcat(reverse(orders), orders)", measurement)
        self.assertIn(
            "[30, 25, 20, 15, 10, 5, 5, 10, 15, 20, 25, 30]",
            self._julia_function(source, "run_self_test"),
        )
        self.assertIn("scan_is_monotonic", measurement)

    def test_ring_image_sampling_prevents_outer_fringe_aliasing(self):
        source = self._julia_source()
        formation = self._julia_function(source, "formation_model")
        self.assertGreaterEqual(
            self._number_constant(source, "RING_GRID_POINTS"), 321
        )
        self.assertIn("length = RING_GRID_POINTS", formation)
        self.assertIn("hypot(x_mm, y_mm) <= span_mm", formation)
        self.assertIn(
            "size(formation.ring_image) == (RING_GRID_POINTS, RING_GRID_POINTS)",
            self._julia_function(source, "run_self_test"),
        )
        self.assertIn(
            '"中心间隙 t₀", 0.00:0.01:0.30, 0.00',
            self._julia_function(source, "formation_figure"),
        )

    def test_difference_and_fit_use_the_correct_diameter_squared_laws(self):
        source = self._julia_source()
        difference = self._julia_function(source, "difference_model")
        fit = self._julia_function(source, "fit_model")

        self.assertIn("[5, 10, 15]", difference)
        self.assertIn("COURSE_DIFFERENCE", difference)
        self.assertRegex(
            difference,
            r"4\.0\s*\*\s*SODIUM_WAVELENGTH_M\s*\*\s*COURSE_DIFFERENCE",
        )
        self.assertRegex(
            fit,
            r"fit\.slope\s*\*\s*1\.0e-6\s*/\s*\(4\.0\s*\*\s*SODIUM_WAVELENGTH_M\)",
        )
        self.assertIn("fit.intercept", fit)
        self.assertIn("radius_uncertainty_m", fit)
        self.assertIn("Dₘ²=D₀²+4Rλm", source)

    def test_reflection_phase_loss_and_ring_radii_follow_newton_ring_physics(self):
        source = self._julia_source()
        reflected = self._julia_function(source, "reflected_intensity")
        dark = self._julia_function(source, "dark_ring_diameter")
        bright = self._julia_function(source, "bright_ring_diameter")
        self_test = self._julia_function(source, "run_self_test")

        # One reflected ray undergoes a half-wave phase reversal, so an ideal
        # contact is dark and the reflected intensity is sin²(2πnt/λ).
        self.assertRegex(
            reflected,
            r"sinpi\(2\.0\s*\*\s*film_index\s*\*\s*thickness\s*/\s*wavelength_m\)\^2",
        )
        self.assertIn("ideal contact dark", reflected)
        self.assertRegex(
            dark,
            r"Float64\(order\)\s*\*\s*wavelength_m\s*/\s*film_index\s*"
            r"-\s*2\.0\s*\*\s*contact_gap_m",
        )
        self.assertRegex(
            bright,
            r"\(Float64\(order\)\s*\+\s*0\.5\)\s*\*\s*wavelength_m\s*/\s*film_index",
        )
        self.assertRegex(
            self_test,
            r"reflected_intensity\(0\.0,\s*1\.0,\s*SODIUM_WAVELENGTH_M,\s*1\.0,\s*0\.0\)"
            r",\s*0\.0",
        )
        self.assertRegex(
            self_test,
            r"first_bright\^2,\s*2\.0\s*\*\s*SODIUM_WAVELENGTH_M",
        )

    def test_sodium_wavelength_is_fixed_as_the_known_quantity(self):
        source = self._julia_source()
        slider_labels = re.findall(
            r'add_slider!\([^\n]*?,\s*\d+\s*,\s*"([^"]+)"', source
        )

        self.assertTrue(slider_labels)
        self.assertNotIn("波长 λ", slider_labels)
        self.assertTrue(
            all("波长" not in label or "不确定度" in label for label in slider_labels)
        )
        self.assertIn("SODIUM_WAVELENGTH_M", source)
        self.assertNotIn("632.8", source)

    def test_canvas_scales_without_repeating_a_page_title(self):
        source = self._julia_source()
        base_figure = self._julia_function(source, "base_figure")
        width = int(self._number_constant(source, "FIGURE_WIDTH"))
        height = int(self._number_constant(source, "FIGURE_HEIGHT"))

        self.assertEqual(width, 960)
        self.assertGreaterEqual(height, 740)
        self.assertNotIn("Label(", base_figure)
        self.assertRegex(
            base_figure,
            r"Figure\(\s*size\s*=\s*\(FIGURE_WIDTH,\s*FIGURE_HEIGHT\)",
        )
        self.assertIn("window.visualViewport", source)
        self.assertIn("ResizeObserver(scheduleFit)", source)
        self.assertIn("translate3d(", source)
        self.assertRegex(
            source,
            r"\.newton-rings-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;"
            r"[^}]*height:\s*\$\(FIGURE_HEIGHT\)px;",
        )
        self.assertIn("const renderedWidth = $(FIGURE_WIDTH) * scale", source)
        self.assertIn("const renderedHeight = $(FIGURE_HEIGHT) * scale", source)
        self.assertRegex(
            source,
            r"(?s)Math\.min\(.*?availableWidth\s*/\s*\$\(FIGURE_WIDTH\)\s*,"
            r"\s*availableHeight\s*/\s*\$\(FIGURE_HEIGHT\).*?\)",
        )

    def test_css_scale_is_applied_to_wgl_pointer_coordinates(self):
        source = self._julia_source()

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

    def test_canvas_rows_leave_safe_space_for_controls_and_bottom_metrics(self):
        source = self._julia_source()
        base_figure = self._julia_function(source, "base_figure")
        slider_helper = self._julia_function(source, "add_slider!")
        metrics_helper = self._julia_function(source, "add_metrics!")
        height = int(self._number_constant(source, "FIGURE_HEIGHT"))

        padding_match = re.search(
            r"figure_padding\s*=\s*\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)",
            base_figure,
        )
        self.assertIsNotNone(padding_match)
        left, right, bottom, top = map(int, padding_match.groups())
        self.assertGreaterEqual(min(left, right, bottom, top), 16)

        row_sizes = {
            int(row): int(size)
            for row, size in re.findall(
                r"rowsize!\(figure\.layout,\s*(\d+),\s*(\d+)\)", base_figure
            )
        }
        self.assertEqual(row_sizes, {1: 380, 2: 170, 3: 110})
        gap_match = re.search(r"rowgap!\(figure\.layout,\s*(\d+)\)", base_figure)
        self.assertIsNotNone(gap_match)
        row_gap = int(gap_match.group(1))
        used_height = sum(row_sizes.values()) + top + bottom + 2 * row_gap
        self.assertGreaterEqual(height - used_height, 16)

        self.assertIn("rowsize!(grid, row, 24)", slider_helper)
        self.assertIn("rowgap!(grid, 4)", slider_helper)
        self.assertLessEqual(4 * 24 + 3 * 4, row_sizes[2])
        self.assertIn("rowsize!(grid, 1, 28)", metrics_helper)
        self.assertIn("rowsize!(grid, 2, 48)", metrics_helper)
        self.assertIn("rowgap!(grid, 8)", metrics_helper)
        self.assertLessEqual(28 + 48 + 8, row_sizes[3])


if __name__ == "__main__":
    unittest.main()
