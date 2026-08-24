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


class YoungModulusIntegrationTests(unittest.TestCase):
    """Expected integration contract for the Young-modulus experiment."""

    @staticmethod
    def _source(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @classmethod
    def _julia_source(cls) -> str:
        return cls._source(APP_DIR / "experiments" / "young_modulus" / "web.jl")

    @staticmethod
    def _julia_function(source: str, name: str) -> str:
        pattern = re.compile(
            rf"^function\s+{re.escape(name)}\b.*?(?=^function\s+|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        match = pattern.search(source)
        if match is None:
            raise AssertionError(f"Julia source does not define function {name}")
        return match.group(0)

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

    def test_service_contract_uses_private_port_9390(self):
        service = experiment_hub.YOUNG_MODULUS
        self.assertEqual(service.key, "young_modulus")
        self.assertEqual(service.title, "杨氏模量测定实验")
        self.assertEqual(service.project_dir, APP_DIR / "experiments" / "young_modulus")
        self.assertEqual(service.web_path, service.project_dir / "web.jl")
        self.assertEqual(service.port_env, "PHYSICS_YOUNG_MODULUS_PORT")
        self.assertEqual(service.default_port, 9390)
        self.assertEqual(service.julia_host_env, "YOUNG_MODULUS_WEB_HOST")
        self.assertEqual(service.julia_port_env, "YOUNG_MODULUS_WEB_PORT")
        self.assertEqual(service.julia_proxy_env, "YOUNG_MODULUS_WEB_PROXY_URL")
        self.assertEqual(service.ready_event, "young-modulus-wgl-ready")
        self.assertEqual(service.failed_event, "young-modulus-wgl-failed")
        self.assertEqual(service.identity_marker, "physics-experiment:young-modulus")
        self.assertIn("杨氏模量", service.root_marker)
        self.assertIs(experiment_hub.SERVICES.get("young_modulus"), service)

    def test_public_prefix_and_gateway_query_are_preserved(self):
        service = experiment_hub.YOUNG_MODULUS
        with patch.dict(
            os.environ,
            {"PHYSICS_PUBLIC_BASE_URL": "https://physics.example/agent/"},
        ):
            self.assertEqual(
                experiment_hub.service_browser_path(service, "/principle"),
                "/agent/experiments/young-modulus/principle",
            )
            self.assertEqual(
                experiment_hub.service_proxy_url(service),
                "https://physics.example/agent/experiments/young-modulus/",
            )

        request = SimpleNamespace(
            path="/agent/experiments/young-modulus/principle",
            query_string="attempt=42&theme=dark",
        )
        with patch.object(gateway, "PUBLIC_PATH_PREFIX", "/agent"):
            self.assertEqual(
                gateway.upstream_url(request),
                "http://127.0.0.1:9390/principle?attempt=42&theme=dark",
            )

    def test_invalid_port_is_rejected(self):
        with patch.dict(os.environ, {"PHYSICS_YOUNG_MODULUS_PORT": "70000"}):
            with self.assertRaises(ValueError):
                experiment_hub.service_port(experiment_hub.YOUNG_MODULUS)

    def test_start_command_is_argument_safe_and_uses_its_own_project(self):
        service = experiment_hub.YOUNG_MODULUS
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

    def test_hub_and_sidebar_expose_the_four_part_course_workflow(self):
        hub_source = self._source(APP_DIR / "experiment_hub.py")
        app_source = self._source(APP_DIR / "app.py")

        self.assertIn('"杨氏模量"', hub_source)
        for route in ("/principle", "/loading", "/fit", "/uncertainty"):
            self.assertRegex(hub_source, rf'"[^"\n]+"\s*:\s*"{re.escape(route)}"')
        self.assertIn('key="young_modulus_experiment_name"', hub_source)
        self.assertIn('key="sidebar_young_modulus"', app_source)
        self.assertIn('visual_experiment_name = "杨氏模量"', app_source)

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
                "/principle": "principle_figure",
                "/loading": "loading_figure",
                "/fit": "fit_figure",
                "/uncertainty": "uncertainty_figure",
            },
        )
        self.assertEqual(len(set(routes.values())), 4)
        self.assertIn("physics-experiment:young-modulus", source)
        self.assertIn("young-modulus-wgl-ready", source)
        self.assertIn("young-modulus-wgl-failed", source)
        self.assertIn('"--self-test"', source)

    def test_course_physics_covers_optical_lever_loading_fit_and_uncertainty(self):
        source = self._julia_source()
        compact = re.sub(r"\s+", "", source)

        extension_formulae = (
            "ΔL=bΔx/(2D)",
            "ΔL=bΔs/(2D)",
            r"\DeltaL=\frac{b\Delta x}{2D}",
            r"\DeltaL=\frac{b\Delta s}{2D}",
            r"\Delta L=\frac{b\Delta x}{2D}",
            r"\Delta L=\frac{b\Delta s}{2D}",
        )
        modulus_formulae = (
            "E=FL/(AΔL)",
            "E=4FL/(πd²ΔL)",
            "E=8FLD/(πd²bΔx)",
            "E=8MgLD/(πd²bΔs)",
            r"E=\frac{FL}{A\Delta L}",
            r"E=\frac{8FLD}{\pi d^2b\Delta x}",
            r"E=\frac{8MgLD}{\pi d^2b\Delta s}",
        )
        self.assertTrue(
            any(formula in compact for formula in extension_formulae),
            "实验必须展示光杠杆微小伸长换算式 ΔL=bΔs/(2D)",
        )
        self.assertTrue(
            any(formula in compact for formula in modulus_formulae),
            "实验必须展示由拉伸法求杨氏模量的核心公式",
        )
        for concept in ("加载", "卸载", "线性拟合", "不确定度"):
            self.assertIn(concept, source)

    def test_canvas_scales_to_the_embedded_viewport_and_stays_loopback_only(self):
        source = self._julia_source()
        width = int(self._number_constant(source, "FIGURE_WIDTH"))
        height = int(self._number_constant(source, "FIGURE_HEIGHT"))

        self.assertEqual((width, height), (960, 760))
        self.assertRegex(
            source,
            r'get\(ENV,\s*"YOUNG_MODULUS_WEB_HOST",\s*"127\.0\.0\.1"\)',
        )
        self.assertNotRegex(
            source,
            r'get\(ENV,\s*"YOUNG_MODULUS_WEB_HOST",\s*"0\.0\.0\.0"\)',
        )
        self.assertIn("window.visualViewport", source)
        self.assertIn("ResizeObserver(scheduleFit)", source)
        self.assertIn("translate3d(", source)
        self.assertRegex(
            source,
            r"\.young-modulus-lab\s*\{[^}]*width:\s*\$\(FIGURE_WIDTH\)px;"
            r"[^}]*height:\s*\$\(FIGURE_HEIGHT\)px;",
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

    def test_nested_iframe_accepts_messages_only_from_its_own_content_window(self):
        embed = experiment_hub._EMBED_HTML
        iframe_match = re.search(
            r'<iframe\b[^>]*\bid="experiment"[^>]*>', embed, re.IGNORECASE
        )
        self.assertIsNotNone(iframe_match)
        self.assertIn("event.source !== frame.contentWindow", embed)
        self.assertIn("!event.data", embed)
        self.assertIn("settings.readyEvent", embed)
        self.assertIn("settings.failedEvent", embed)


if __name__ == "__main__":
    unittest.main()
