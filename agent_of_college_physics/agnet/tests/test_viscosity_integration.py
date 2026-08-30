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


class ViscosityIntegrationTests(unittest.TestCase):
    """Integration and physics contract for the falling-ball viscosity lab."""

    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @classmethod
    def _julia_source(cls) -> str:
        return cls._source(APP_DIR / "experiments" / "viscosity" / "web.jl")

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

    def test_service_contract_uses_private_port_9392(self) -> None:
        service = experiment_hub.VISCOSITY
        self.assertEqual(service.key, "viscosity")
        self.assertEqual(service.title, "粘滞系数测定实验")
        self.assertEqual(service.project_dir, APP_DIR / "experiments" / "viscosity")
        self.assertEqual(service.web_path, service.project_dir / "web.jl")
        self.assertEqual(service.port_env, "PHYSICS_VISCOSITY_PORT")
        self.assertEqual(service.default_port, 9392)
        self.assertEqual(service.julia_host_env, "VISCOSITY_WEB_HOST")
        self.assertEqual(service.julia_port_env, "VISCOSITY_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "VISCOSITY_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "viscosity-wgl-ready")
        self.assertEqual(service.failed_event, "viscosity-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:viscosity")
        self.assertIn("粘滞系数", service.root_marker)
        self.assertIs(experiment_hub.SERVICES.get("viscosity"), service)

    def test_public_prefix_and_gateway_query_are_preserved(self) -> None:
        service = experiment_hub.VISCOSITY
        with patch.dict(os.environ, {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"}):
            self.assertEqual(
                experiment_hub.service_browser_path(service, "/stokes"),
                "/agent/experiments/viscosity/stokes",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(service),
                "https://physics.example/agent/experiments/viscosity/",
            )

        request = SimpleNamespace(
            path="/agent/experiments/viscosity/terminal",
            query_string="attempt=42&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9392/terminal?attempt=42&theme=dark",
            )

    def test_start_command_is_argument_safe_and_uses_its_own_project(self) -> None:
        service = experiment_hub.VISCOSITY
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

    def test_invalid_port_is_rejected(self) -> None:
        with patch.dict(os.environ, {"PHYSICS_VISCOSITY_PORT": "70000"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.VISCOSITY)

    def test_hub_and_sidebar_expose_the_four_part_workflow(self) -> None:
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")

        self.assertIn('"粘滞系数测定"', hub_source)
        for route in ("/stokes", "/terminal", "/correction", "/fit"):
            self.assertRegex(hub_source, rf'"[^"\n]+"\s*:\s*"{re.escape(route)}"')
        self.assertIn('key="viscosity_experiment_name"', hub_source)
        self.assertIn('key="sidebar_viscosity"', app_source)
        self.assertIn('visual_experiment_name = "粘滞系数测定"', app_source)

    def test_julia_service_declares_four_independent_routes_and_markers(self) -> None:
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
                "/stokes": "stokes_figure",
                "/terminal": "terminal_figure",
                "/correction": "correction_figure",
                "/fit": "fit_figure",
            },
        )
        self.assertEqual(len(set(routes.values())), 4)
        self.assertIn("physics-experiment:viscosity", source)
        self.assertIn("viscosity-wgl-ready", source)
        self.assertIn("viscosity-wgl-failed", source)
        self.assertIn('"--self-test"', source)

    def test_course_physics_covers_the_full_falling_ball_workflow(self) -> None:
        source = self._julia_source()
        compact = re.sub(r"\s+", "", source)

        for function_name in (
            "stokes_terminal_velocity",
            "stokes_reynolds",
            "terminal_model",
            "correction_model",
            "fit_model",
        ):
            self.assertRegex(
                source,
                re.compile(rf"^function\s+{function_name}\b", re.MULTILINE),
            )

        self.assertIn("Fη=6πηrv", compact)
        self.assertIn("η=2r²g(ρs-ρl)/(9v∞)", compact)
        self.assertIn("v=v∞(1-e^{-t/τ})", compact)
        self.assertIn("λ=d/D", compact)
        self.assertIn("1.0-2.1044*ratio+2.0888*ratio^3-0.9480*ratio^5", compact)
        self.assertIn("corrected_viscosity=apparent_viscosity*faxen_factor", compact)
        self.assertIn("fitted_viscosity=2.0*GRAVITY*density_difference/(9.0*fit.slope)", compact)
        for concept in ("斯托克斯", "终端速度", "Faxén", "Re=", "不确定度"):
            self.assertIn(concept, source)
        self.assertIn("粘滞系数", source)
        self.assertIn("黏度", source)

    def test_canvas_scaling_and_pointer_compensation_match_wglmakie(self) -> None:
        source = self._julia_source()
        self.assertEqual(
            (
                int(self._number_constant(source, "FIGURE_WIDTH")),
                int(self._number_constant(source, "FIGURE_HEIGHT")),
            ),
            (960, 760),
        )
        self.assertRegex(source, r'get\(ENV,\s*"VISCOSITY_WEB_HOST",\s*"127\.0\.0\.1"\)')
        self.assertNotRegex(source, r'get\(ENV,\s*"VISCOSITY_WEB_HOST",\s*"0\.0\.0\.0"\)')
        self.assertIn("window.visualViewport", source)
        self.assertIn("ResizeObserver(scheduleFit)", source)
        self.assertIn("translate3d(", source)
        self.assertRegex(
            source,
            r"\.viscosity-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;"
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

    def test_project_declares_reproducible_julia_dependencies(self) -> None:
        project = self._source(APP_DIR / "experiments" / "viscosity" / "Project.toml")
        manifest = APP_DIR / "experiments" / "viscosity" / "Manifest.toml"
        self.assertIn('Bonito = "824d6782-a2ef-11e9-3a09-e5662e0c26f8"', project)
        self.assertIn('WGLMakie = "276b4fcb-3e11-5398-bf8b-a0c2d153d008"', project)
        self.assertTrue(manifest.is_file())
        self.assertGreater(manifest.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
