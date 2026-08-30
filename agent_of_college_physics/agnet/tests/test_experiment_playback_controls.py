from __future__ import annotations

import re
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]

EXPERIMENT_BUILDERS = {
    "sound_speed": (
        "echo_figure",
        "dual_figure",
        "phase_figure",
        "standing_figure",
    ),
    "electron_em": (
        "circular_figure",
        "helmholtz_figure",
        "focus_figure",
        "thomson_figure",
    ),
    "photoelectric": (
        "iv_figure",
        "planck_figure",
        "threshold_figure",
        "uncertainty_figure",
    ),
    "biprism": (
        "geometry_figure",
        "fringes_figure",
        "separation_figure",
        "wavelength_figure",
    ),
    "newton_rings": (
        "formation_figure",
        "measurement_figure",
        "difference_figure",
        "fit_figure",
    ),
    "young_modulus": (
        "principle_figure",
        "loading_figure",
        "fit_figure",
        "uncertainty_figure",
    ),
    "rotational_inertia": (
        "torsion_figure",
        "trifilar_figure",
        "parallel_axis_figure",
        "pendulum_fit_figure",
    ),
    "viscosity": (
        "stokes_figure",
        "terminal_figure",
        "correction_figure",
        "fit_figure",
    ),
    "specific_heat": (
        "mixing_figure",
        "cooling_figure",
        "electrical_figure",
        "fit_figure",
    ),
    "franck_hertz": (
        "apparatus_figure",
        "curve_figure",
        "analysis_figure",
        "uncertainty_figure",
    ),
    "temperature_sensor": (
        "calibration_figure",
        "response_figure",
        "bridge_figure",
        "uncertainty_figure",
    ),
    "wheatstone_bridge": (
        "principle_figure",
        "balance_figure",
        "sensitivity_figure",
        "fit_figure",
    ),
    "hall_effect": (
        "calibration_figure",
        "scan_figure",
        "fit_figure",
        "uncertainty_figure",
    ),
    "magnetic_hysteresis": (
        "loop_figure",
        "apparatus_figure",
        "demagnetization_figure",
        "fit_figure",
    ),
    "thin_lens_focal": (
        "direct_figure",
        "autocollimation_figure",
        "displacement_figure",
        "uncertainty_figure",
    ),
    "prism_refractive_index": (
        "collimation_figure",
        "apex_figure",
        "minimum_deviation_figure",
        "dispersion_figure",
    ),
    "thermal_conductivity": (
        "steady_state_figure",
        "cooling_figure",
        "fit_figure",
        "uncertainty_figure",
    ),
}


def _julia_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^function\s+{re.escape(name)}\([^\n]*\)\s*$.*?(?=^function\s+|\Z)",
        source,
    )
    if match is None:
        raise AssertionError(f"Julia function {name!r} was not found")
    return match.group(0)


def _balanced_region(text: str, opening_index: int) -> str:
    pairs = {"(": ")", "[": "]", "{": "}"}
    opening = text[opening_index]
    closing = pairs[opening]
    depth = 0
    quote: str | None = None
    escaped = False

    for index in range(opening_index, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return text[opening_index : index + 1]
    raise AssertionError(f"Unbalanced Julia source starting at offset {opening_index}")


def _call_text(source: str, call_name: str, start: int = 0) -> str:
    match = re.search(rf"\b{re.escape(call_name)}\s*\(", source[start:])
    if match is None:
        raise AssertionError(f"Call {call_name!r} was not found")
    opening_index = start + match.end() - 1
    return call_name + _balanced_region(source, opening_index)


def _split_top_level(source: str) -> list[str]:
    parts: list[str] = []
    start = 0
    stack: list[str] = []
    pairs = {"(": ")", "[": "]", "{": "}"}
    quote: str | None = None
    escaped = False

    for index, character in enumerate(source):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character in pairs:
            stack.append(pairs[character])
        elif stack and character == stack[-1]:
            stack.pop()
        elif character == "," and not stack:
            parts.append(source[start:index].strip())
            start = index + 1

    parts.append(source[start:].strip())
    return parts


def _normalise_expression(expression: str) -> str:
    return re.sub(r"\s+", "", expression.rstrip(";,"))


def _slider_defaults(builder_source: str) -> dict[str, str]:
    assignment = re.compile(
        r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
        r"(add_slider!?|Slider)\s*\("
    )
    defaults: dict[str, str] = {}
    for match in assignment.finditer(builder_source):
        variable, constructor = match.groups()
        call = _call_text(builder_source, constructor, match.start(2))
        arguments = _split_top_level(call[call.index("(") + 1 : -1])
        if constructor.startswith("add_slider"):
            if len(arguments) < 5:
                raise AssertionError(
                    f"{variable} has no positional start value in {call!r}"
                )
            default = arguments[4]
        else:
            startvalue = next(
                (
                    argument.split("=", 1)[1]
                    for argument in arguments
                    if re.match(r"^startvalue\s*=", argument)
                ),
                None,
            )
            if startvalue is None:
                raise AssertionError(f"{variable} has no Slider startvalue")
            default = startvalue
        defaults[variable] = _normalise_expression(default)
    return defaults


def _reset_defaults(bind_call: str) -> dict[str, str]:
    reset_list: str | None = None
    for match in re.finditer(r"\[", bind_call):
        candidate = _balanced_region(bind_call, match.start())
        if re.search(r"\(\s*[A-Za-z_][A-Za-z0-9_]*\s*,", candidate):
            reset_list = candidate
            break
    if reset_list is None:
        raise AssertionError("bind_playback! has no reset-value list")

    defaults: dict[str, str] = {}
    for item in _split_top_level(reset_list[1:-1]):
        item = item.strip()
        if not item:
            continue
        if not (item.startswith("(") and item.endswith(")")):
            raise AssertionError(f"Invalid reset entry: {item!r}")
        pair = _split_top_level(item[1:-1])
        if len(pair) != 2 or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", pair[0]):
            raise AssertionError(f"Invalid reset pair: {item!r}")
        defaults[pair[0]] = _normalise_expression(pair[1])
    return defaults


class ExperimentPlaybackControlContractTests(unittest.TestCase):
    @staticmethod
    def _source(experiment: str) -> str:
        return (
            APP_DIR / "experiments" / experiment / "web.jl"
        ).read_text(encoding="utf-8")

    def test_all_non_lissajous_experiments_have_four_playable_route_builders(
        self,
    ) -> None:
        self.assertNotIn("lissajous", EXPERIMENT_BUILDERS)
        self.assertEqual(len(EXPERIMENT_BUILDERS), 17)

        route_pattern = re.compile(
            r'Bonito\.route!\(\s*server\s*,\s*"(/[^"/]+)"\s*=>\s*'
            r'(?:sound_speed_app|experiment_app)\(\s*"[^"]+"\s*,\s*'
            r'([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\)',
            re.S,
        )
        for experiment, expected_builders in EXPERIMENT_BUILDERS.items():
            with self.subTest(experiment=experiment):
                routes = route_pattern.findall(self._source(experiment))
                self.assertEqual(len(routes), 4)
                self.assertEqual(
                    {builder for _, builder in routes}, set(expected_builders)
                )
                self.assertEqual(len({route for route, _ in routes}), 4)

    def test_playback_helpers_toggle_pause_run_async_and_invalidate_old_loops(
        self,
    ) -> None:
        for experiment in EXPERIMENT_BUILDERS:
            with self.subTest(experiment=experiment):
                helper = _julia_function(
                    self._source(experiment), "bind_playback!"
                )
                for label in ('label = "播放"', '"暂停"', 'label = "重置"'):
                    self.assertIn(label, helper)
                self.assertIn("playing[] = !playing[]", helper)
                self.assertIn("@async begin", helper)
                self.assertRegex(helper, r"(?s)while\s+playing\[\].*?sleep\(")

                token_match = re.search(
                    r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*Ref\(0\)",
                    helper,
                )
                self.assertIsNotNone(token_match)
                token = token_match.group(1)
                captures = re.findall(
                    rf"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*{re.escape(token)}\[\]",
                    helper,
                )
                self.assertTrue(captures)
                self.assertGreaterEqual(
                    len(re.findall(rf"{re.escape(token)}\[\]\s*\+=\s*1", helper)),
                    2,
                )
                self.assertTrue(
                    any(
                        re.search(
                            rf"(?s)while\s+playing\[\].*?{re.escape(token)}\[\]\s*==\s*"
                            rf"{re.escape(capture)}",
                            helper,
                        )
                        for capture in captures
                    )
                )

                self.assertIn("on(reset_button.clicks)", helper)
                self.assertIn("playing[] = false", helper)
                self.assertIn('play_button.label[] = "播放"', helper)
                self.assertRegex(
                    helper,
                    r"for\s*\(slider,\s*value\)\s+in\s+reset_values\s*"
                    r"set_close_to!\(slider,\s*value\)",
                )

    def test_each_builder_binds_once_and_resets_every_slider_to_its_default(
        self,
    ) -> None:
        for experiment, builders in EXPERIMENT_BUILDERS.items():
            source = self._source(experiment)
            for builder in builders:
                with self.subTest(experiment=experiment, builder=builder):
                    body = _julia_function(source, builder)
                    self.assertEqual(
                        len(re.findall(r"\bbind_playback!\s*\(", body)), 1
                    )
                    slider_defaults = _slider_defaults(body)
                    self.assertTrue(slider_defaults)
                    bind_call = _call_text(body, "bind_playback!")
                    reset_defaults = _reset_defaults(bind_call)
                    self.assertEqual(
                        set(reset_defaults),
                        set(slider_defaults),
                        "reset list must include every slider and no stale slider",
                    )
                    self.assertEqual(reset_defaults, slider_defaults)


if __name__ == "__main__":
    unittest.main()
