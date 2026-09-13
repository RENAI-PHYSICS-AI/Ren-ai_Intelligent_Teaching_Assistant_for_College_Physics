from __future__ import annotations

import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import visualization


class VisualizationExpressionSafetyTests(unittest.TestCase):
    def test_normal_physics_expression_remains_supported(self) -> None:
        values = visualization._values("sin(x) + x^2 - 1e-3", "x", [0.0, 2.0])
        self.assertAlmostEqual(values[0], -0.001)
        self.assertAlmostEqual(values[1], 4.0 + visualization.math.sin(2.0) - 0.001)

    def test_signed_constant_power_remains_supported(self) -> None:
        values = visualization._values("x**-2", "x", [2.0])
        self.assertEqual(values, [0.25])

    def test_scientific_notation_for_physics_constants_remains_supported(self) -> None:
        values = visualization._values("6.022e23 * x", "x", [0.0, 1.0])
        self.assertEqual(values, [0.0, 6.022e23])

    def test_nested_powers_are_rejected_in_either_operand(self) -> None:
        for expression in ("9**(9**9)", "(x**2)**3", "x**2**3"):
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(ValueError, "嵌套幂"):
                    visualization._compile_expression(expression, "x")

    def test_dynamic_and_oversized_exponents_are_rejected(self) -> None:
        for expression in ("2**x", "x**13", "x**-13"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    visualization._compile_expression(expression, "x")

    def test_giant_integer_literal_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "整数常量超出安全范围"):
            visualization._compile_expression("999999999999999999999999 + x", "x")

    def test_node_depth_and_operation_bombs_are_rejected(self) -> None:
        malicious = (
            "+" * 20 + "x",
            "+".join(["x"] * 40),
            "sin(" * 18 + "x" + ")" * 18,
        )
        for expression in malicious:
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    visualization._compile_expression(expression, "x")

    def test_non_numeric_constants_and_keyword_calls_are_rejected(self) -> None:
        for expression in ('"1"', "True", "sin(x=1)"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    visualization._compile_expression(expression, "x")


if __name__ == "__main__":
    unittest.main()
