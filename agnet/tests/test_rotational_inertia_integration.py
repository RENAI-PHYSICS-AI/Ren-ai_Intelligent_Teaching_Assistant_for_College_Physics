from __future__ import annotations

import inspect
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


class RotationalInertiaIntegrationTests(unittest.TestCase):
    """Integration and physics contract for the rotational-inertia lab."""

    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @classmethod
    def _julia_source(cls) -> str:
        return cls._source(APP_DIR / "experiments" / "rotational_inertia" / "web.jl")

    @staticmethod
    def _number_constant(source: str, name: str) -> float:
        match = re.search(
            rf"^const\s+{re.escape(name)}\s*=\s*([0-9]+(?:\.[0-9]+)?)",
            source,
            re.MULTILINE,
        )
        if match is None:
            raise AssertionError(f"Julia source does not define numeric constant {name}")
        return float(match.group(1))

    def test_service_contract_uses_private_port_9391(self):
        service = experiment_hub.ROTATIONAL_INERTIA
        self.assertEqual(service.key, "rotational_inertia")
        self.assertEqual(service.title, "转动惯量测定实验")
        self.assertEqual(service.project_dir, APP_DIR / "experiments" / "rotational_inertia")
        self.assertEqual(service.web_path, service.project_dir / "web.jl")
        self.assertEqual(service.port_env, "PHYSICS_ROTATIONAL_INERTIA_PORT")
        self.assertEqual(service.default_port, 9391)
        self.assertEqual(service.julia_host_env, "ROTATIONAL_INERTIA_WEB_HOST")
        self.assertEqual(service.julia_port_env, "ROTATIONAL_INERTIA_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "ROTATIONAL_INERTIA_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "rotational-inertia-wgl-ready")
        self.assertEqual(service.failed_event, "rotational-inertia-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:rotational-inertia")
        self.assertIn("转动惯量", service.root_marker)
        self.assertIs(experiment_hub.SERVICES.get("rotational_inertia"), service)

    def test_public_prefix_and_gateway_query_are_preserved(self):
        service = experiment_hub.ROTATIONAL_INERTIA
        with patch.dict(os.environ, {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"}):
            self.assertEqual(
                experiment_hub.service_browser_path(service, "/torsion"),
                "/agent/experiments/rotational-inertia/torsion",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(service),
                "https://physics.example/agent/experiments/rotational-inertia/",
            )

        request = SimpleNamespace(
            path="/agent/experiments/rotational-inertia/torsion",
            query_string="attempt=42&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9391/torsion?attempt=42&theme=dark",
            )

    def test_invalid_port_is_rejected(self):
        with patch.dict(os.environ, {"PHYSICS_ROTATIONAL_INERTIA_PORT": "70000"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.ROTATIONAL_INERTIA)

    def test_start_command_is_argument_safe_and_uses_its_own_project(self):
        service = experiment_hub.ROTATIONAL_INERTIA
        configured = str(Path(f"{chr(67)}:/") / "Julia-1.10" / "bin" / "julia.exe")
        with patch.dict(
            os.environ,
            {
                "PHYSICS_JULIA_EXE": configured,
                "PHYSICS_EXPERIMENT_INSTANTIATE": "false",
            },
        ):
            command = experiment_hub._julia_command(service)

        self.assertEqual(command[0], configured)
        self.assertIn(f"--project={service.project_dir}", command)
        self.assertIn(str(service.web_path), command)
        self.assertIn("--no-instantiate", command)
        self.assertTrue(all(isinstance(argument, str) for argument in command))

        launcher = inspect.getsource(experiment_hub.launch_service)
        self.assertIn('environment[service.julia_host_env] = "127.0.0.1"', launcher)
        self.assertIn("subprocess.Popen(", launcher)
        self.assertNotIn("shell=True", launcher)

    def test_hub_and_sidebar_expose_the_four_part_workflow(self):
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")

        self.assertIn('"转动惯量"', hub_source)
        for route in ("/torsion", "/trifilar", "/parallel-axis", "/pendulum-fit"):
            self.assertRegex(hub_source, rf'"[^"\n]+"\s*:\s*"{re.escape(route)}"')
        self.assertIn('key="rotational_inertia_experiment_name"', hub_source)
        self.assertIn('key="sidebar_rotational_inertia"', app_source)
        self.assertIn('visual_experiment_name = "转动惯量"', app_source)

    def test_julia_service_declares_four_independent_routes_and_markers(self):
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
                "/torsion": "torsion_figure",
                "/trifilar": "trifilar_figure",
                "/parallel-axis": "parallel_axis_figure",
                "/pendulum-fit": "pendulum_fit_figure",
            },
        )
        self.assertEqual(len(set(routes.values())), 4)
        self.assertIn("physics-experiment:rotational-inertia", source)
        self.assertIn("rotational-inertia-wgl-ready", source)
        self.assertIn("rotational-inertia-wgl-failed", source)
        self.assertIn('"--self-test"', source)

    def test_course_physics_covers_all_four_measurement_methods(self):
        source = self._julia_source()
        compact = re.sub(r"\s+", "", source)

        for function_name in (
            "torsion_model",
            "trifilar_model",
            "parallel_axis_model",
            "pendulum_fit_model",
        ):
            self.assertRegex(
                source,
                re.compile(rf"^function\s+{function_name}\b", re.MULTILINE),
            )

        formula_groups = (
            ("T=2π√((I₀+I)/κ)", "I=κT²/(4π²)-I₀"),
            ("κg=mgRr/H", "I=mgRrT²/(4π²H)"),
            ("I_O=I_C+md²",),
            ("T²h=(4π²/g)(h²+k²)",),
        )
        for alternatives in formula_groups:
            self.assertTrue(
                any(formula in compact for formula in alternatives),
                f"missing physics formula from {alternatives}",
            )
        for concept in ("扭摆", "三线摆", "平行轴定理", "复摆", "不确定度"):
            self.assertIn(concept, source)

        self.assertIn("上下盘竖直间距 H", source)
        self.assertIn("vertical_spacing_m", source)
        self.assertNotIn("string_length_m", source)
        self.assertNotIn("悬线长度 L", source)
        self.assertIn("I_C拟合", source)
        self.assertIn("u[I(h)]", source)
        self.assertIn("惯量单位 kg·m²", source)
        self.assertIn('"I_C拟合=%.2e±%.1e"', source)
        self.assertIn('"I(h=%.0fcm)=%.2e"', source)
        self.assertIn('"u[I(h)]=%.1e"', source)
        self.assertNotIn("I_C拟合 = %.3e ± %.1e kg·m²", source)
        self.assertIn("斜率—截距协方差", source)
        self.assertIn("fitted_center_inertia_uncertainty", source)
        self.assertIn("slope_intercept_covariance", source)

    def test_canvas_scaling_and_pointer_compensation_match_wglmakie(self):
        source = self._julia_source()
        self.assertEqual(
            (
                int(self._number_constant(source, "FIGURE_WIDTH")),
                int(self._number_constant(source, "FIGURE_HEIGHT")),
            ),
            (960, 760),
        )
        self.assertRegex(
            source,
            r'get\(ENV,\s*"ROTATIONAL_INERTIA_WEB_HOST",\s*"127\.0\.0\.1"\)',
        )
        self.assertNotRegex(
            source,
            r'get\(ENV,\s*"ROTATIONAL_INERTIA_WEB_HOST",\s*"0\.0\.0\.0"\)',
        )
        self.assertIn("window.visualViewport", source)
        self.assertIn("ResizeObserver(scheduleFit)", source)
        self.assertIn("translate3d(", source)
        self.assertRegex(
            source,
            r"\.rotational-inertia-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;"
            r"[^}]*height:\s*\$\(FIGURE_HEIGHT\)px;",
        )

        self.assertIn("const syncWGLPointerScale = event =>", source)
        self.assertIn("event.target instanceof HTMLCanvasElement", source)
        self.assertIn("canvas.wglmakie_screen", source)
        self.assertIn("screen.__physicsBaseWinscale = screen.winscale", source)
        self.assertIn("screen.winscale = baseWinscale * layoutScale", source)
        self.assertRegex(source, r"layoutScale\s*=\s*scale;\s*page\.style\.transform")
        for event_name in ("mousemove", "mousedown", "pointerdown", "pointermove"):
            self.assertIn(f'"{event_name}"', source)
        self.assertRegex(source, r"capture:\s*true")

    def test_project_declares_reproducible_julia_dependencies(self):
        project = self._source(APP_DIR / "experiments" / "rotational_inertia" / "Project.toml")
        manifest = APP_DIR / "experiments" / "rotational_inertia" / "Manifest.toml"
        self.assertIn('Bonito = "824d6782-a2ef-11e9-3a09-e5662e0c26f8"', project)
        self.assertIn('WGLMakie = "276b4fcb-3e11-5398-bf8b-a0c2d153d008"', project)
        self.assertTrue(manifest.is_file())
        self.assertGreater(manifest.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
