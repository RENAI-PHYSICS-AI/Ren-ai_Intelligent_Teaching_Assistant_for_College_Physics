from __future__ import annotations

import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = APP_DIR / "experiments"


class ExperimentPlaybackLifecycleContractTests(unittest.TestCase):
    def test_shared_helper_cancels_on_browser_and_session_lifecycle(self) -> None:
        source = (EXPERIMENTS_DIR / "playback_lifecycle.jl").read_text(
            encoding="utf-8"
        )
        self.assertIn("IdDict{Task, Vector{Function}}", source)
        self.assertIn("on(session, session.on_close)", source)
        self.assertIn("on(session, cancellation_requested)", source)
        self.assertIn("$(cancellation_requested).notify(true)", source)
        for browser_event in ("pagehide", "beforeunload", "visibilitychange"):
            self.assertIn(browser_event, source)

    def test_lissajous_and_young_modulus_apps_are_session_scoped(self) -> None:
        for experiment in ("lissajous", "young_modulus"):
            with self.subTest(experiment=experiment):
                source = (EXPERIMENTS_DIR / experiment / "web.jl").read_text(
                    encoding="utf-8"
                )
                self.assertIn('include(joinpath(@__DIR__, "..", "playback_lifecycle.jl"))', source)
                self.assertRegex(source, r"do session::Bonito\.Session")
                self.assertIn("build_with_playback_lifecycle(session, builder)", source)
                self.assertIn("playback.lifecycle_script", source)
                self.assertIn("register_playback_cancel!(cancel_playback!)", source)

    def test_parameter_lab_family_uses_same_session_lifecycle(self) -> None:
        source = (EXPERIMENTS_DIR / "parameter_lab.jl").read_text(encoding="utf-8")
        self.assertIn('include(joinpath(@__DIR__, "playback_lifecycle.jl"))', source)
        self.assertRegex(source, r"do session::Bonito\.Session")
        self.assertIn(
            "build_with_playback_lifecycle(session, () -> build_page(page))",
            source,
        )
        self.assertIn("register_playback_cancel!(cancel_playback!)", source)
        self.assertIn("playback.lifecycle_script", source)

        for experiment in (
            "gas_gamma",
            "grating_interference",
            "light_polarization",
            "michelson_wavelength",
        ):
            with self.subTest(experiment=experiment):
                entrypoint = (EXPERIMENTS_DIR / experiment / "web.jl").read_text(
                    encoding="utf-8"
                )
                self.assertIn('include(joinpath(@__DIR__, "..", "parameter_lab.jl"))', entrypoint)

    def test_each_covered_loop_has_generation_invalidation(self) -> None:
        for path, helper_name in (
            (EXPERIMENTS_DIR / "lissajous" / "web.jl", "bind_playback!"),
            (EXPERIMENTS_DIR / "young_modulus" / "web.jl", "bind_playback!"),
            (EXPERIMENTS_DIR / "parameter_lab.jl", "bind_transport!"),
        ):
            source = path.read_text(encoding="utf-8")
            helper = re.search(
                rf"(?ms)^function\s+{re.escape(helper_name)}\([^\n]*\)\s*$.*?(?=^function\s+|\Z)",
                source,
            )
            self.assertIsNotNone(helper, path)
            body = helper.group(0)
            self.assertIn("generation = Ref(0)", body)
            self.assertIn("generation[] += 1", body)
            self.assertIn("register_playback_cancel!(cancel_playback!)", body)


if __name__ == "__main__":
    unittest.main()
