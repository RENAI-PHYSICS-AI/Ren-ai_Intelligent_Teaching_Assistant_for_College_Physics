from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import experiment_hub


EXPECTED_GROUPS = {
    "力学实验": ("杨氏模量", "转动惯量", "粘滞系数测定"),
    "热学实验": (
        "固体比热容的测定",
        "温度传感器特性的测定",
        "固体热传导系数测定",
    ),
    "振动波动": ("声速测量", "李萨如图形"),
    "电磁实验": (
        "电子荷质比",
        "惠斯通电桥测电阻",
        "霍尔效应测磁场分布",
        "铁磁滞回线测定与观察",
    ),
    "光学实验": (
        "牛顿环",
        "双棱镜干涉",
        "薄透镜焦距的测定",
        "三棱镜折射率测定",
    ),
    "近代物理实验": ("光电效应", "弗兰克-赫兹"),
}


class ExperimentCategoryTests(unittest.TestCase):
    def test_groups_match_the_course_taxonomy_without_duplicates(self) -> None:
        self.assertEqual(experiment_hub.EXPERIMENT_GROUPS, EXPECTED_GROUPS)
        self.assertEqual(list(experiment_hub.EXPERIMENT_GROUPS), list(EXPECTED_GROUPS))
        experiments = [
            name
            for names in experiment_hub.EXPERIMENT_GROUPS.values()
            for name in names
        ]
        self.assertEqual(len(experiments), 18)
        self.assertEqual(len(experiments), len(set(experiments)))

    def test_biprism_uses_full_display_name_but_keeps_canonical_state(self) -> None:
        self.assertEqual(
            experiment_hub.EXPERIMENT_DISPLAY_NAMES["双棱镜干涉"],
            "双棱镜干涉测波长",
        )
        self.assertNotIn("双棱镜干涉测波长", experiment_hub.EXPERIMENT_CATEGORY_BY_NAME)

    def test_old_and_changed_session_states_are_normalized(self) -> None:
        self.assertEqual(
            experiment_hub.normalize_experiment_selection(None, "牛顿环"),
            ("光学实验", "牛顿环"),
        )
        self.assertEqual(
            experiment_hub.normalize_experiment_selection("力学实验", "光电效应"),
            ("力学实验", "杨氏模量"),
        )
        self.assertEqual(
            experiment_hub.normalize_experiment_selection("无效分类", "无效实验"),
            ("力学实验", "杨氏模量"),
        )

    def test_sidebar_buttons_update_experiment_and_category_together(self) -> None:
        source = (APP_DIR / "app.py").read_text(encoding="utf-8")
        expected_buttons = {
            "sidebar_young_modulus": ("杨氏模量", "力学实验"),
            "sidebar_rotational_inertia": ("转动惯量", "力学实验"),
            "sidebar_viscosity": ("粘滞系数测定", "力学实验"),
            "sidebar_specific_heat": ("固体比热容的测定", "热学实验"),
            "sidebar_temperature_sensor": ("温度传感器特性的测定", "热学实验"),
            "sidebar_thermal_conductivity": ("固体热传导系数测定", "热学实验"),
            "sidebar_sound_speed": ("声速测量", "振动波动"),
            "sidebar_lissajous": ("李萨如图形", "振动波动"),
            "sidebar_electron_em": ("电子荷质比", "电磁实验"),
            "sidebar_wheatstone_bridge": ("惠斯通电桥测电阻", "电磁实验"),
            "sidebar_hall_effect": ("霍尔效应测磁场分布", "电磁实验"),
            "sidebar_magnetic_hysteresis": ("铁磁滞回线测定与观察", "电磁实验"),
            "sidebar_newton_rings": ("牛顿环", "光学实验"),
            "sidebar_biprism": ("双棱镜干涉", "光学实验"),
            "sidebar_thin_lens_focal": ("薄透镜焦距的测定", "光学实验"),
            "sidebar_prism_refractive_index": ("三棱镜折射率测定", "光学实验"),
            "sidebar_photoelectric": ("光电效应", "近代物理实验"),
            "sidebar_franck_hertz": ("弗兰克-赫兹", "近代物理实验"),
        }
        for key, (experiment_name, category) in expected_buttons.items():
            pattern = re.compile(
                rf'key="{re.escape(key)}".*?'
                rf'visual_experiment_name = "{re.escape(experiment_name)}".*?'
                rf'visual_experiment_category = "{re.escape(category)}"',
                re.DOTALL,
            )
            self.assertRegex(source, pattern)

        for category in EXPECTED_GROUPS:
            self.assertIn(f'st.markdown("**{category}**")', source)

    def test_each_entry_to_visual_mode_starts_with_first_mechanics_experiment(self) -> None:
        source = (APP_DIR / "app.py").read_text(encoding="utf-8")
        self.assertRegex(
            source,
            re.compile(
                r'workspace_mode == "可视化实验".*?'
                r'previous_workspace_mode != "可视化实验".*?'
                r'visual_experiment_category = "力学实验".*?'
                r'visual_experiment_name = "杨氏模量"',
                re.DOTALL,
            ),
        )


if __name__ == "__main__":
    unittest.main()
