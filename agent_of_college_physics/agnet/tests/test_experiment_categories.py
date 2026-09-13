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
        "气体γ常数测定",
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
        "光栅干涉",
        "光的偏振研究",
        "迈克尔逊干涉仪测波长",
    ),
    "近代物理实验": ("光电效应", "弗兰克-赫兹"),
}


class ExperimentCategoryTests(unittest.TestCase):
    def test_registry_is_the_single_source_for_hub_metadata(self) -> None:
        definitions = experiment_hub.EXPERIMENT_REGISTRY
        self.assertEqual(len(definitions), 22)
        self.assertEqual(len({definition.name for definition in definitions}), 22)
        self.assertEqual(len({definition.service.key for definition in definitions}), 22)

        projected_groups = {
            category: tuple(
                definition.name
                for definition in definitions
                if definition.category == category
            )
            for category in dict.fromkeys(
                definition.category for definition in definitions
            )
        }
        self.assertEqual(experiment_hub.EXPERIMENT_GROUPS, projected_groups)
        for definition in definitions:
            with self.subTest(experiment=definition.name):
                self.assertIs(
                    experiment_hub.EXPERIMENT_SERVICE_BY_NAME[definition.name],
                    definition.service,
                )
                self.assertIs(
                    experiment_hub.SERVICES[definition.service.key],
                    definition.service,
                )
                self.assertEqual(
                    experiment_hub.EXPERIMENT_CATEGORY_BY_NAME[definition.name],
                    definition.category,
                )

    def test_groups_match_the_course_taxonomy_without_duplicates(self) -> None:
        self.assertEqual(experiment_hub.EXPERIMENT_GROUPS, EXPECTED_GROUPS)
        self.assertEqual(list(experiment_hub.EXPERIMENT_GROUPS), list(EXPECTED_GROUPS))
        experiments = [
            definition.name for definition in experiment_hub.EXPERIMENT_REGISTRY
        ]
        self.assertEqual(len(experiments), 22)
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
            "sidebar_gas_gamma": ("气体γ常数测定", "热学实验"),
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
            "sidebar_grating_interference": ("光栅干涉", "光学实验"),
            "sidebar_light_polarization": ("光的偏振研究", "光学实验"),
            "sidebar_michelson_wavelength": ("迈克尔逊干涉仪测波长", "光学实验"),
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
