from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_DIR.parent
ROCKY_CANDIDATE = PROJECT_ROOT / "agent_of_college_physics"
ROCKY_ROOT = ROCKY_CANDIDATE if ROCKY_CANDIDATE.is_dir() else PROJECT_ROOT
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import experiment_hub
import gateway


class PhotoelectricExperimentIntegrationTests(unittest.TestCase):
    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @classmethod
    def _photoelectric_source(cls) -> str:
        return cls._source(APP_DIR / "experiments" / "photoelectric" / "web.jl")

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

    def test_service_uses_dedicated_private_upstream(self):
        service = experiment_hub.PHOTOELECTRIC
        self.assertEqual(service.key, "photoelectric")
        self.assertEqual(service.default_port, 9387)
        self.assertEqual(service.port_env, "PHYSICS_PHOTOELECTRIC_PORT")
        self.assertEqual(service.julia_host_env, "PHOTOELECTRIC_WEB_HOST")
        self.assertEqual(service.julia_port_env, "PHOTOELECTRIC_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "PHOTOELECTRIC_WEB_PROXY_URL")
        self.assertEqual(service.identity_marker, "physics-experiment:photoelectric")
        self.assertEqual(service.root_marker, "光电效应")
        self.assertIn("photoelectric", experiment_hub.SERVICES)

    def test_public_prefix_is_preserved_for_iframe_and_bonito(self):
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(
                    experiment_hub.PHOTOELECTRIC, "/uncertainty"
                ),
                "/agent/experiments/photoelectric/uncertainty",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(experiment_hub.PHOTOELECTRIC),
                "https://physics.example/agent/experiments/photoelectric/",
            )

    def test_invalid_photoelectric_port_is_rejected(self):
        with patch.dict(os.environ, {"PHYSICS_PHOTOELECTRIC_PORT": "70000"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.PHOTOELECTRIC)

    def test_gateway_routes_photoelectric_and_keeps_query(self):
        request = SimpleNamespace(
            path="/agent/experiments/photoelectric/planck",
            query_string="attempt=42&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9387/planck?attempt=42&theme=dark",
            )

    def test_hub_and_sidebar_expose_the_fourth_experiment(self):
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")
        self.assertIn(
            '["李萨如图形", "声速测量", "电子荷质比", "光电效应"]',
            hub_source,
        )
        self.assertIn('"光电管伏安特性": "/iv"', hub_source)
        self.assertIn('"普朗克常量拟合": "/planck"', hub_source)
        self.assertIn('"截止频率与光强": "/threshold"', hub_source)
        self.assertIn('"遏止电压判读": "/uncertainty"', hub_source)
        self.assertIn('key="sidebar_photoelectric"', app_source)
        self.assertIn('visual_experiment_name = "光电效应"', app_source)

    def test_julia_service_declares_four_independent_routes_and_markers(self):
        source = self._photoelectric_source()
        route_pairs = re.findall(
            r'Bonito\.route!\(\s*server\s*,\s*"(/[^"]+)"\s*=>\s*'
            r'experiment_app\(\s*"[^"]+"\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\)',
            source,
        )
        routes = dict(route_pairs)
        self.assertEqual(
            routes,
            {
                "/iv": "iv_figure",
                "/planck": "planck_figure",
                "/threshold": "threshold_figure",
                "/uncertainty": "uncertainty_figure",
            },
        )
        self.assertEqual(len(set(routes.values())), 4)
        self.assertIn("physics-experiment:photoelectric", source)
        self.assertIn("photoelectric-wgl-ready", source)
        self.assertIn("photoelectric-wgl-failed", source)
        self.assertIn('"--self-test"', source)

    def test_browser_status_script_preserves_javascript_newline_escapes(self):
        source = self._photoelectric_source()

        # CLIENT_STATUS_SCRIPT is a Julia string which emits JavaScript.  A
        # single ``\n`` here becomes a literal line break inside a quoted JS
        # string and prevents all four pages from reporting WGL readiness.
        self.assertIn('"\\\\nWebGL 状态："', source)
        self.assertIn('"\\\\n页面地址："', source)
        self.assertIn('"\\\\n" + event.filename', source)
        self.assertNotIn('"\\nWebGL 状态："', source)
        self.assertNotIn('"\\n页面地址："', source)

    def test_canvas_does_not_repeat_the_page_heading(self):
        source = self._photoelectric_source()
        base_figure = self._julia_function(source, "base_figure")

        self.assertRegex(base_figure, r"^function\s+base_figure\(\s*\)")
        self.assertNotIn("Label(", base_figure)
        self.assertNotRegex(base_figure, r"\b(?:title|subtitle)\b")

        for builder in (
            "iv_figure",
            "planck_figure",
            "threshold_figure",
            "uncertainty_figure",
        ):
            builder_source = self._julia_function(source, builder)
            base_calls = re.findall(r"\bbase_figure\((.*?)\)", builder_source, re.S)
            self.assertEqual([arguments.strip() for arguments in base_calls], [""])

    def test_layout_tracks_the_real_embedded_viewport(self):
        source = self._photoelectric_source()
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
            r"\.photoelectric-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;"
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

    def test_layout_reserves_space_below_controls_and_detail(self):
        source = self._photoelectric_source()
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
            figure_height
            - bottom_padding
            - top_padding
            - occupied_height
        )
        bottom_safe_space = bottom_padding + layout_slack
        self.assertGreaterEqual(layout_slack, 16)
        self.assertGreaterEqual(bottom_safe_space, 32)

        metric_rows = {
            int(row): int(height)
            for row, height in re.findall(
                r"rowsize!\(grid,\s*(\d+),\s*(\d+)\)", add_metrics
            )
        }
        self.assertEqual(set(metric_rows), {1, 2})
        self.assertRegex(add_metrics, r"Label\(grid\[2,\s*1:4\],\s*detail\b")
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
            len(
                re.findall(
                    r"\badd_slider!\(controls,",
                    self._julia_function(source, builder),
                )
            )
            for builder in (
                "iv_figure",
                "planck_figure",
                "threshold_figure",
                "uncertainty_figure",
            )
        )
        controls_height = (
            max_slider_count * slider_height
            + (max_slider_count - 1) * slider_gap
        )
        self.assertGreaterEqual(figure_rows[2] - controls_height, 16)

    def test_rocky_scripts_include_precompile_stop_and_health_checks(self):
        manage_source = self._source(ROCKY_ROOT / "manage.sh")
        install_source = self._source(ROCKY_ROOT / "install.sh")
        env_source = self._source(ROCKY_ROOT / "physics-assistant.env.example")

        self.assertIn('PHYSICS_PHOTOELECTRIC_PORT="${PHYSICS_PHOTOELECTRIC_PORT:-9387}"', manage_source)
        self.assertIn("experiments/photoelectric/web.jl", manage_source)
        self.assertIn("physics-experiment:photoelectric", manage_source)
        self.assertIn("lissajous sound_speed electron_em photoelectric", install_source)
        self.assertIn('runtime/experiments/photoelectric.log"', install_source)
        self.assertIn("PHYSICS_PHOTOELECTRIC_PORT=9387", env_source)
        self.assertIn(
            "PHYSICS_PHOTOELECTRIC_UPSTREAM=http://127.0.0.1:9387",
            env_source,
        )
        self.assertTrue(
            (
                ROCKY_ROOT
                / "agnet"
                / "runtime"
                / "experiments"
                / "photoelectric.log"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
