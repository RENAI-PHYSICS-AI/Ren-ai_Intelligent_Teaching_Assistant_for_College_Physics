from __future__ import annotations

import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from exam_artifacts import validate_tex_document
from exam_blueprint import (
    EXAM_BLUEPRINT_FALLBACK_INSTRUCTIONS,
    EXAM_BLUEPRINT_JSON_SCHEMA,
    ChoiceOptionRepairSpec,
    ExamBlueprintError,
    FillBlankStemRepairSpec,
    TargetedExamRepairPlan,
    apply_choice_option_repairs,
    apply_targeted_exam_repairs,
    blueprint_to_dict,
    canonical_blueprint_json,
    choice_option_repair_specs,
    parse_exam_blueprint,
    render_exam_tex,
    targeted_exam_repair_plan,
    tex_escape,
)


def valid_blueprint_data() -> dict:
    answers = ("A", "B", "C", "D", "A", "B", "C", "D", "A", "B")
    questions = []
    choice_topics = (
        "质点运动学位移判断", "牛顿定律受力分析", "动量守恒碰撞过程",
        "功与机械能关系", "刚体定轴转动规律", "简谐振动相位关系",
        "机械波传播特征", "静电场高斯定理", "稳恒磁场洛伦兹力", "光的干涉条件",
    )
    for number, (topic, answer) in enumerate(zip(choice_topics, answers), 1):
        questions.append({
            "number": number,
            "type": "single_choice",
            "score": 3,
            "title": "",
            "stem": f"关于{topic}，下列四项结论中符合物理规律的是哪一项？",
            "options": [
                f"选项A给出{topic}的第一种关系",
                f"选项B给出{topic}的第二种关系",
                f"选项C给出{topic}的第三种关系",
                f"选项D给出{topic}的第四种关系",
            ],
            "answer": answer,
            "analysis": f"依据{topic}的定义和适用条件逐项核对，可确定答案为{answer}。",
            "rubric": [{"points": 3, "criterion": "正确选择唯一符合条件的选项"}],
            "chapter": f"章节{number}",
            "difficulty": "中等",
        })
    fill_topics = ("角动量", "理想气体", "电势能", "电磁感应", "薄膜干涉")
    for offset, topic in enumerate(fill_topics, 11):
        questions.append({
            "number": offset,
            "type": "fill_blank",
            "score": 4,
            "title": "",
            "stem": f"在{topic}的基本关系中，第一个关键量为[[BLANK]]，第二个关键量为[[BLANK]]。",
            "options": [],
            "answer": f"{topic}量甲；{topic}量乙",
            "analysis": f"由{topic}的定义式和方向约定可直接得到两空。",
            "rubric": [
                {"points": 2, "criterion": "第一空正确"},
                {"points": 2, "criterion": "第二空正确"},
            ],
            "chapter": topic,
            "difficulty": "基础",
        })
    calculation_topics = ("转动惯量", "热力学第一定律", "电场叠加", "磁场运动", "双缝干涉")
    for offset, topic in enumerate(calculation_topics, 16):
        questions.append({
            "number": offset,
            "type": "calculation",
            "score": 10,
            "title": f"{topic}计算题",
            "stem": f"给定一组互不相同的实验条件，建立{topic}模型并计算最终物理量，写明单位和方向。",
            "options": [],
            "answer": "SECRET_ANSWER_16" if offset == 16 else f"{topic}的数值结果与方向",
            "analysis": f"先选择{topic}的基本定律，再代入条件验算量纲和数量级。",
            "rubric": [
                {"points": 4, "criterion": "建立正确的物理模型和方程"},
                {"points": 4, "criterion": "代入数据并完成数值运算"},
                {"points": 2, "criterion": "单位、方向和有效数字正确"},
            ],
            "chapter": topic,
            "difficulty": "中等",
        })
    return {
        "schema_version": 1,
        "kind": "exam",
        "summary": "已按标准结构生成大学物理补考试卷。",
        "title": "2025—2026学年第二学期大学物理补考试卷",
        "course": "大学物理1",
        "academic_year": "2025—2026学年",
        "term": "第二学期",
        "exam_type": "补考",
        "exam_date": "2026年8月",
        "duration_minutes": 120,
        "total_score": 100,
        "questions": questions,
    }


def valid_blueprint_json() -> str:
    return json.dumps(valid_blueprint_data(), ensure_ascii=False)


def duplicate_choice_options_data() -> dict:
    data = valid_blueprint_data()
    data["questions"][0]["options"] = [
        "A. 动量守恒！",
        "B、动 量，守恒",
        "机械能不守恒",
        "机械能不守恒。",
    ]
    data["questions"][1]["options"][2:] = [
        "合外力为零",
        "合外力为零。",
    ]
    return data


def duplicate_choice_options_json() -> str:
    return json.dumps(duplicate_choice_options_data(), ensure_ascii=False)


def complete_option_repairs() -> dict:
    data = duplicate_choice_options_data()
    return {
        "repairs": [
            {
                "number": 1,
                "options": [
                    data["questions"][0]["options"][0],
                    "动量随时间改变",
                    data["questions"][0]["options"][2],
                    "机械能守恒",
                ],
            },
            {
                "number": 2,
                "options": [
                    data["questions"][1]["options"][0],
                    data["questions"][1]["options"][1],
                    data["questions"][1]["options"][2],
                    "合外力恒定且不为零",
                ],
            },
        ],
    }


def combined_targeted_repair_data() -> dict:
    data = valid_blueprint_data()
    data["questions"][4]["options"][3] = (
        data["questions"][4]["options"][1] + "。"
    )
    data["questions"][10]["stem"] = "在角动量的基本关系中，关键量为[[BLANK]]。"
    return data


def complete_targeted_repairs() -> dict:
    data = combined_targeted_repair_data()
    repaired_options = list(data["questions"][4]["options"])
    repaired_options[3] = "选项D给出刚体定轴转动规律的独立干扰关系"
    return {
        "choice_repairs": [{"number": 5, "options": repaired_options}],
        "fill_stem_repairs": [{
            "number": 11,
            "stem": "在角动量的基本关系中，第一个关键量为[[BLANK]]，"
                    "第二个关键量为[[BLANK]]。",
        }],
    }


class ExamBlueprintTests(unittest.TestCase):
    def test_options_schema_rejects_exact_duplicates_without_breaking_empty_arrays(self):
        options_schema = (
            EXAM_BLUEPRINT_JSON_SCHEMA["properties"]["questions"]["items"]
            ["properties"]["options"]
        )
        self.assertTrue(options_schema["uniqueItems"])
        self.assertEqual(options_schema["maxItems"], 4)
        self.assertNotIn("minItems", options_schema)
        self.assertIn(
            "忽略大小写、空格、标点和选项序号后仍须互不相同",
            EXAM_BLUEPRINT_FALLBACK_INSTRUCTIONS,
        )

        blueprint = parse_exam_blueprint(valid_blueprint_json())
        self.assertTrue(all(not item.options for item in blueprint.questions[10:]))

    def test_standard_blueprint_round_trips_and_renders_safe_tex(self):
        blueprint = parse_exam_blueprint(valid_blueprint_json())
        self.assertEqual(blueprint.total_score, 100)
        self.assertEqual(len(blueprint.questions), 20)
        self.assertEqual(parse_exam_blueprint(canonical_blueprint_json(blueprint)), blueprint)

        main_tex, answer_tex = render_exam_tex(blueprint)
        validate_tex_document(main_tex)
        validate_tex_document(answer_tex)
        self.assertEqual(main_tex.count("\\newpage"), 2)
        self.assertEqual(main_tex.count(r"\begin{mdframed}["), 3)
        self.assertNotIn(r"\begin{minipage}[t][", main_tex)
        self.assertEqual(main_tex.count(r"\begin{minipage}[t]{\linewidth}"), 5)
        self.assertIn("每空 2 分，共 20 分", main_tex)
        expected_main_calculation_titles = (
            "三、转动惯量计算题（共 10 分）",
            "四、热力学第一定律计算题（共 10 分）",
            "五、电场叠加计算题（共 10 分）",
            "六、磁场运动计算题（共 10 分）",
            "七、双缝干涉计算题（共 10 分）",
        )
        expected_answer_calculation_titles = (
            "三.转动惯量计算题(本题10分)",
            "四.热力学第一定律计算题(本题10分)",
            "五.电场叠加计算题(本题10分)",
            "六.磁场运动计算题(本题10分)",
            "七.双缝干涉计算题(本题10分)",
        )
        for title in expected_main_calculation_titles:
            self.assertIn(title, main_tex)
        for title in expected_answer_calculation_titles:
            self.assertIn(title, answer_tex)
        positions = [main_tex.index(title) for title in expected_main_calculation_titles]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("三、计算题参考答案", answer_tex)
        self.assertNotIn("SECRET_ANSWER_16", main_tex)
        self.assertIn(r"SECRET\_ANSWER\_16", answer_tex)

        self.assertTrue(answer_tex.startswith(r"\documentclass[a4paper]{ctexart}"))
        self.assertIn(
            r"\usepackage[a4paper,top=2.54cm,bottom=2.54cm]{geometry}",
            answer_tex,
        )
        self.assertIn(r"\setlength{\parindent}{0pt}", answer_tex)
        self.assertIn(r"\section*{2025—2026学年第二学期大学物理补考试卷解析}", answer_tex)
        self.assertIn(r"\subsection*{一.单选题(每题3分，共计30分)}", answer_tex)
        self.assertIn(r"题号 & 1 & 2 & 3 & 4 & 5 & 6 & 7 & 8 & 9 & 10", answer_tex)
        self.assertIn(r"选项 & A & B & C & D & A & B & C & D & A & B", answer_tex)
        self.assertIn(r"\subsection*{二.填空题(每空2分，共计20分)}", answer_tex)
        self.assertIn(r"题号 & 1 & 2 & 3 & 4 & 5", answer_tex)
        self.assertEqual(answer_tex.count(r"\begin{table}[htbp]"), 2)
        self.assertEqual(answer_tex.count(r"\subsection*{"), 7)
        self.assertNotIn(r"\begin{enumerate}", answer_tex)
        self.assertNotIn(r"\begin{mdframed}", answer_tex)
        self.assertNotIn(r"\bibliography", answer_tex)
        self.assertIn(r"\hfill(4分)\\", answer_tex)

    def test_main_paper_uses_template_page_frames_alignment_and_answer_space(self):
        blueprint = parse_exam_blueprint(valid_blueprint_json())
        main_tex, _ = render_exam_tex(blueprint)
        pages = main_tex.split("\\newpage")

        self.assertEqual(len(pages), 3)
        self.assertEqual(main_tex.count(r"\columnbreak"), 3)
        for page_number, page in enumerate(pages, 1):
            self.assertIn(f"共 3 页　第 {page_number} 页", page)
            self.assertEqual(page.count(r"\begin{mdframed}["), 1)
            self.assertEqual(page.count(r"\end{mdframed}"), 1)
            self.assertIn("linewidth=2pt, linecolor=black", page)
            self.assertIn("innerleftmargin=2pt,innerrightmargin=8pt", page)
            self.assertIn("innerbottommargin=35pt", page)
            self.assertIn(
                r"\begin{tabularx}{\textwidth}{@{}lX lX lX lX lX lX r@{}}",
                page,
            )

        first_page = pages[0]
        self.assertEqual(first_page.count(r"\begin{multicols}{2}"), 1)
        self.assertLess(first_page.index(r"\begin{mdframed}["), first_page.index("《大学物理1》"))
        self.assertLess(first_page.index(r"\begin{multicols}{2}"), first_page.index("《大学物理1》"))
        self.assertLess(first_page.index("《大学物理1》"), first_page.index("题号 & 一 & 二"))
        self.assertLess(first_page.index("题号 & 一 & 二"), first_page.index("一、单项选择题"))
        self.assertLess(first_page.index("一、单项选择题"), first_page.index(r"\columnbreak"))
        self.assertLess(first_page.index(r"\columnbreak"), first_page.index("start=6"))
        self.assertIn("start=6", first_page)
        self.assertNotIn("《大学物理1》（共 3 页）", pages[1])
        self.assertNotIn("《大学物理1》（共 3 页）", pages[2])

        for answer_space in ("12em", "40em", "11em", "10em"):
            self.assertIn(f"\\vspace*{{{answer_space}}}", main_tex)
        self.assertGreaterEqual(main_tex.count(r"\vspace*{40em}"), 2)
        self.assertNotIn(r"\par\medskip", main_tex)
        self.assertEqual(main_tex.count(r"\vspace*{0.6em}\noindent"), 5)

    def test_layout_guards_reject_unsafe_lengths_before_tex_render(self):
        too_long = valid_blueprint_data()
        too_long["questions"][15]["stem"] = "计算题已知条件" + "甲" * 450
        with self.assertRaisesRegex(ExamBlueprintError, "超过 320 字符限制"):
            parse_exam_blueprint(json.dumps(too_long, ensure_ascii=False))

        oversized_choices = valid_blueprint_data()
        for number, question in enumerate(oversized_choices["questions"][:10], 1):
            question["stem"] = f"第{number}题的独立物理情景" + "甲" * 55
            question["options"] = [
                f"选项{label}的独立结论" + label * 25
                for label in ("A", "B", "C", "D")
            ]
        with self.assertRaisesRegex(ExamBlueprintError, "选择题总文本超出.*版面预算"):
            parse_exam_blueprint(json.dumps(oversized_choices, ensure_ascii=False))

        oversized_page_three = valid_blueprint_data()
        for index, marker in ((17, "甲"), (18, "乙")):
            prefix = f"第{index + 1}题独立计算条件"
            oversized_page_three["questions"][index]["stem"] = prefix + marker * (270 - len(prefix))
        with self.assertRaisesRegex(ExamBlueprintError, "第三页左栏题干超出版面预算"):
            parse_exam_blueprint(json.dumps(oversized_page_three, ensure_ascii=False))

    def test_boundary_length_calculation_uses_at_least_eight_em_answer_space(self):
        data = valid_blueprint_data()
        prefix = "第十六题边界长度独立计算条件"
        data["questions"][15]["stem"] = prefix + "甲" * (320 - len(prefix))
        blueprint = parse_exam_blueprint(json.dumps(data, ensure_ascii=False))
        main_tex, _ = render_exam_tex(blueprint)
        self.assertNotIn(r"\begin{minipage}[t][", main_tex)
        self.assertIn(r"\vspace*{8em}", main_tex)
        self.assertEqual(main_tex.count("\\newpage"), 2)

    def test_calculation_titles_are_explicit_and_do_not_embed_number_or_score(self):
        bad = valid_blueprint_data()
        bad["questions"][15]["title"] = ""
        with self.assertRaisesRegex(ExamBlueprintError, "独立的计算题 title"):
            parse_exam_blueprint(json.dumps(bad, ensure_ascii=False))

        bad = valid_blueprint_data()
        bad["questions"][15]["title"] = "三、电学计算题"
        with self.assertRaisesRegex(ExamBlueprintError, "不得自带大题序号"):
            parse_exam_blueprint(json.dumps(bad, ensure_ascii=False))

        bad = valid_blueprint_data()
        bad["questions"][15]["title"] = "电学计算题（共10分）"
        with self.assertRaisesRegex(ExamBlueprintError, "不得自带分值"):
            parse_exam_blueprint(json.dumps(bad, ensure_ascii=False))

        bad = valid_blueprint_data()
        bad["questions"][0]["title"] = "单项选择题"
        with self.assertRaisesRegex(ExamBlueprintError, "title 必须为空字符串"):
            parse_exam_blueprint(json.dumps(bad, ensure_ascii=False))

    def test_model_text_is_escaped_before_tex_validation(self):
        data = valid_blueprint_data()
        data["questions"][0]["stem"] += r" \input{/etc/passwd} & 100%"
        blueprint = parse_exam_blueprint(json.dumps(data, ensure_ascii=False))
        main_tex, answer_tex = render_exam_tex(blueprint)
        validate_tex_document(main_tex)
        validate_tex_document(answer_tex)
        self.assertNotIn(r"\input{/etc/passwd}", main_tex)
        self.assertIn(r"\textbackslash{}input\{/etc/passwd\}", main_tex)
        self.assertIn(r"100\%", main_tex)

    def test_physics_notation_is_rendered_in_math_mode_and_miu_is_normalized(self):
        rendered = tex_escape(r"运动方程 x=6t-2t^2，磁场为 \miu_0 I/(2r)。")
        self.assertIn(r"\(x=6t-2t^2\)", rendered)
        self.assertIn(r"\(\mu_0 I/(2r)\)", rendered)
        self.assertNotIn(r"\textasciicircum", rendered)
        self.assertNotIn("miu", rendered)
        self.assertEqual(tex_escape("I^2/2"), r"\(I^2/2\)")
        self.assertEqual(tex_escape("I ^2/2"), r"\(I^2/2\)")
        self.assertEqual(tex_escape("q1 与 q2"), r"\(q_{1}\) 与 \(q_{2}\)")
        self.assertEqual(tex_escape("Iω²/2"), r"\(I\omega^{2}/2\)")
        self.assertEqual(tex_escape("μ₀I/(2r)"), r"\(\mu_{0}I/(2r)\)")
        self.assertEqual(tex_escape("Iω^2/2"), r"\(I\omega^2/2\)")
        self.assertEqual(tex_escape("μ0I/(2πr)"), r"\(\mu_{0}I/(2\pi r)\)")
        self.assertEqual(tex_escape("μ0I/(4πr^2)"), r"\(\mu_{0}I/(4\pi r^2)\)")
        self.assertEqual(tex_escape("F=kq1q2/r^2"), r"\(F=kq_{1}q_{2}/r^2\)")
        self.assertEqual(tex_escape("Ek=Iω^2/2"), r"\(E_{k}=I\omega^2/2\)")

        data = valid_blueprint_data()
        data["questions"][0]["stem"] = r"质点运动方程为 x=6t-2t^2（SI）。"
        data["questions"][5]["options"] = [
            r"\miu_0 I/(2r)", "Iω²/2",
            "I ^2/4", "μ₀I/(4r²)",
        ]
        main_tex, answer_tex = render_exam_tex(
            parse_exam_blueprint(json.dumps(data, ensure_ascii=False))
        )
        validate_tex_document(main_tex)
        validate_tex_document(answer_tex)
        self.assertIn(r"\(x=6t-2t^2\)", main_tex)
        self.assertIn(r"\(\mu_0 I/(2r)\)", main_tex)
        self.assertIn(r"\(I\omega^{2}/2\)", main_tex)
        self.assertIn(r"\(I^2/4\)", main_tex)
        self.assertIn(r"\(\mu_{0}I/(4r^{2})\)", main_tex)
        self.assertNotIn(r"\textbackslash{}miu", main_tex)

    def test_rejects_binary_duplicate_keys_and_incomplete_json(self):
        with self.assertRaisesRegex(ExamBlueprintError, "PDF"):
            parse_exam_blueprint("%PDF-1.7\nxref")
        with self.assertRaisesRegex(ExamBlueprintError, "字段重复"):
            parse_exam_blueprint('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ExamBlueprintError, "单个 JSON"):
            parse_exam_blueprint('{"schema_version":1')

    def test_rejects_wrong_structure_and_rubric(self):
        bad = valid_blueprint_data()
        bad["questions"] = bad["questions"][:-1]
        with self.assertRaisesRegex(ExamBlueprintError, "20 题"):
            parse_exam_blueprint(json.dumps(bad, ensure_ascii=False))

        bad = valid_blueprint_data()
        bad["questions"][15]["rubric"] = [{"points": 9, "criterion": "不足十分"}]
        with self.assertRaisesRegex(ExamBlueprintError, "评分点合计"):
            parse_exam_blueprint(json.dumps(bad, ensure_ascii=False))

    def test_accepts_bounded_choice_distribution_with_one_triple(self):
        data = valid_blueprint_data()
        answers = ("A", "A", "A", "B", "A", "B", "B", "C", "C", "D")
        for question, answer in zip(data["questions"][:10], answers):
            question["answer"] = answer

        blueprint = parse_exam_blueprint(json.dumps(data, ensure_ascii=False))

        self.assertEqual(
            tuple(question.answer for question in blueprint.questions[:10]),
            answers,
        )

    def test_accepts_single_label_choice_answer_distribution(self):
        data = valid_blueprint_data()
        answers = ("A",) * 10
        for question, answer in zip(data["questions"][:10], answers):
            question["answer"] = answer

        blueprint = parse_exam_blueprint(json.dumps(data, ensure_ascii=False))

        self.assertEqual(
            tuple(question.answer for question in blueprint.questions[:10]),
            answers,
        )

    def test_accepts_choice_answer_distribution_with_missing_label(self):
        data = valid_blueprint_data()
        answers = ("B", "C", "D", "B", "C", "D", "B", "C", "D", "B")
        for question, answer in zip(data["questions"][:10], answers):
            question["answer"] = answer

        blueprint = parse_exam_blueprint(json.dumps(data, ensure_ascii=False))

        self.assertNotIn("A", tuple(question.answer for question in blueprint.questions[:10]))

    def test_accepts_four_consecutive_choice_answers(self):
        data = valid_blueprint_data()
        answers = ("A", "A", "A", "A", "B", "B", "B", "C", "C", "D")
        for question, answer in zip(data["questions"][:10], answers):
            question["answer"] = answer

        blueprint = parse_exam_blueprint(json.dumps(data, ensure_ascii=False))

        self.assertEqual(
            tuple(question.answer for question in blueprint.questions[:10]),
            answers,
        )

    def test_rejects_exact_and_near_duplicate_stems(self):
        bad = valid_blueprint_data()
        bad["questions"][1]["stem"] = bad["questions"][0]["stem"]
        with self.assertRaisesRegex(ExamBlueprintError, "重复"):
            parse_exam_blueprint(json.dumps(bad, ensure_ascii=False))

        bad = valid_blueprint_data()
        original = bad["questions"][0]["stem"]
        bad["questions"][1]["stem"] = original.replace("哪一项", "哪一个选项")
        with self.assertRaisesRegex(ExamBlueprintError, "疑似重复"):
            parse_exam_blueprint(json.dumps(bad, ensure_ascii=False))

    def test_rejects_exact_and_normalized_duplicate_choice_options(self):
        exact = valid_blueprint_data()
        exact["questions"][0]["options"][1] = exact["questions"][0]["options"][0]
        with self.assertRaisesRegex(ExamBlueprintError, "第 1 题存在重复选项"):
            parse_exam_blueprint(json.dumps(exact, ensure_ascii=False))

        normalized = duplicate_choice_options_data()
        with self.assertRaisesRegex(ExamBlueprintError, "第 1 题存在重复选项"):
            parse_exam_blueprint(json.dumps(normalized, ensure_ascii=False))

    def test_choice_option_repair_specs_lock_correct_and_keeper_options(self):
        specs = choice_option_repair_specs(duplicate_choice_options_json())
        self.assertEqual(tuple(spec.number for spec in specs), (1, 2))
        self.assertTrue(all(isinstance(spec, ChoiceOptionRepairSpec) for spec in specs))

        first, second = specs
        self.assertEqual(first.options, tuple(duplicate_choice_options_data()["questions"][0]["options"]))
        self.assertEqual(first.answer, "A")
        self.assertIn("答案为A", first.analysis)
        self.assertEqual(first.editable_labels, ("B", "D"))
        self.assertEqual(first.keeper_labels, ("A", "C"))
        self.assertEqual(first.locked_labels, ("A", "C"))
        self.assertEqual(second.answer, "B")
        self.assertEqual(second.editable_labels, ("D",))
        self.assertEqual(second.keeper_labels, ("C",))
        self.assertEqual(second.locked_labels, ("A", "B", "C"))
        with self.assertRaises(FrozenInstanceError):
            first.number = 9  # type: ignore[misc]

    def test_choice_option_repair_specs_require_all_other_validation_to_pass(self):
        invalid = duplicate_choice_options_data()
        invalid["questions"][15]["rubric"] = [
            {"points": 9, "criterion": "评分点总和不足十分"}
        ]
        with self.assertRaisesRegex(ExamBlueprintError, "评分点合计"):
            choice_option_repair_specs(json.dumps(invalid, ensure_ascii=False))

        self.assertEqual(choice_option_repair_specs(
            json.dumps({
                "schema_version": 1,
                "kind": "message",
                "summary": "只说明命题原则。",
                "title": "",
                "course": "",
                "academic_year": "",
                "term": "",
                "exam_type": "",
                "exam_date": "",
                "duration_minutes": 0,
                "total_score": 0,
                "questions": [],
            }, ensure_ascii=False)
        ), ())

    def test_choice_option_repair_specs_ignore_answer_distribution_outlier(self):
        data = duplicate_choice_options_data()
        for question in data["questions"][:10]:
            question["answer"] = "B"
        raw = json.dumps(data, ensure_ascii=False)

        specs = choice_option_repair_specs(raw)

        self.assertEqual(tuple(spec.number for spec in specs), (1, 2))
        self.assertEqual(tuple(spec.answer for spec in specs), ("B", "B"))

        repair = complete_option_repairs()
        repair["repairs"][0]["options"] = [
            "动量随时间改变",
            data["questions"][0]["options"][1],
            data["questions"][0]["options"][2],
            "机械能守恒",
        ]
        repaired = apply_choice_option_repairs(
            raw,
            json.dumps(repair, ensure_ascii=False),
        )
        self.assertEqual(
            tuple(question.answer for question in repaired.questions[:10]),
            ("B",) * 10,
        )
        self.assertEqual(repaired.questions[0].analysis, data["questions"][0]["analysis"])
        self.assertEqual(repaired.questions[0].rubric[0].criterion,
                         data["questions"][0]["rubric"][0]["criterion"])

    def test_apply_choice_option_repairs_changes_only_authorized_options(self):
        repaired = apply_choice_option_repairs(
            duplicate_choice_options_json(),
            json.dumps(complete_option_repairs(), ensure_ascii=False),
        )
        repaired_dict = blueprint_to_dict(repaired)
        baseline = blueprint_to_dict(parse_exam_blueprint(valid_blueprint_json()))
        self.assertEqual(repaired_dict["questions"][0]["options"][1], "动量随时间改变")
        self.assertEqual(repaired_dict["questions"][0]["options"][3], "机械能守恒")
        self.assertEqual(repaired_dict["questions"][1]["options"][3], "合外力恒定且不为零")
        self.assertEqual(repaired_dict["questions"][2:], baseline["questions"][2:])
        self.assertEqual(
            parse_exam_blueprint(canonical_blueprint_json(repaired)),
            repaired,
        )

    def test_apply_choice_option_repairs_restores_locked_option_changes(self):
        repair = complete_option_repairs()
        repair["repairs"][0]["options"][0] = "更改了正确选项"
        repaired = apply_choice_option_repairs(
            duplicate_choice_options_json(),
            json.dumps(repair, ensure_ascii=False),
        )
        original = duplicate_choice_options_data()
        self.assertEqual(repaired.questions[0].options[0], original["questions"][0]["options"][0])
        self.assertEqual(repaired.questions[0].options[1], repair["repairs"][0]["options"][1])

        repair = complete_option_repairs()
        repair["repairs"][0]["options"][2] += " "
        repaired = apply_choice_option_repairs(
            duplicate_choice_options_json(),
            json.dumps(repair, ensure_ascii=False),
        )
        self.assertEqual(repaired.questions[0].options[2], original["questions"][0]["options"][2])

    def test_apply_choice_option_repairs_requires_exact_spec_coverage(self):
        missing = complete_option_repairs()
        missing["repairs"] = missing["repairs"][:1]
        with self.assertRaisesRegex(ExamBlueprintError, "未覆盖全部重复题.*第 2 题"):
            apply_choice_option_repairs(
                duplicate_choice_options_json(),
                json.dumps(missing, ensure_ascii=False),
            )

        extra = complete_option_repairs()
        extra["repairs"].append({
            "number": 3,
            "options": duplicate_choice_options_data()["questions"][2]["options"],
        })
        with self.assertRaisesRegex(ExamBlueprintError, "未授权的第 3 题"):
            apply_choice_option_repairs(
                duplicate_choice_options_json(),
                json.dumps(extra, ensure_ascii=False),
            )

        duplicate = complete_option_repairs()
        duplicate["repairs"].append(duplicate["repairs"][0].copy())
        with self.assertRaisesRegex(ExamBlueprintError, "重复提交第 1 题"):
            apply_choice_option_repairs(
                duplicate_choice_options_json(),
                json.dumps(duplicate, ensure_ascii=False),
            )

    def test_apply_choice_option_repairs_runs_full_exam_revalidation(self):
        still_duplicate = complete_option_repairs()
        still_duplicate["repairs"][0]["options"][1] = "动量 守恒"
        with self.assertRaisesRegex(ExamBlueprintError, "第 1 题存在重复选项"):
            apply_choice_option_repairs(
                duplicate_choice_options_json(),
                json.dumps(still_duplicate, ensure_ascii=False),
            )

        forbidden_topic = complete_option_repairs()
        forbidden_topic["repairs"][0]["options"][1] = "狭义相对论适用"
        with self.assertRaisesRegex(ExamBlueprintError, "不涉及相对论"):
            apply_choice_option_repairs(
                duplicate_choice_options_json(),
                json.dumps(forbidden_topic, ensure_ascii=False),
            )

    def test_targeted_exam_repair_plan_collects_combined_supported_issues(self):
        raw = json.dumps(combined_targeted_repair_data(), ensure_ascii=False)
        plan = targeted_exam_repair_plan(raw)

        self.assertIsInstance(plan, TargetedExamRepairPlan)
        self.assertEqual(tuple(spec.number for spec in plan.choice_repairs), (5,))
        self.assertEqual(tuple(spec.number for spec in plan.fill_stem_repairs), (11,))
        self.assertIsInstance(plan.choice_repairs[0], ChoiceOptionRepairSpec)
        self.assertIsInstance(plan.fill_stem_repairs[0], FillBlankStemRepairSpec)
        self.assertEqual(plan.choice_repairs[0].editable_labels, ("D",))
        self.assertEqual(plan.choice_repairs[0].locked_labels, ("A", "B", "C"))
        fill_spec = plan.fill_stem_repairs[0]
        self.assertEqual(fill_spec.stem.count("[[BLANK]]"), 1)
        self.assertEqual(fill_spec.answer, "角动量量甲；角动量量乙")
        self.assertIn("角动量", fill_spec.analysis)
        self.assertEqual(fill_spec.chapter, "角动量")
        self.assertEqual(fill_spec.difficulty, "基础")
        with self.assertRaises(FrozenInstanceError):
            plan.fill_stem_repairs = ()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            fill_spec.stem = "不允许修改"  # type: ignore[misc]

    def test_targeted_exam_repair_plan_allows_only_supported_defects(self):
        with self.assertRaisesRegex(ExamBlueprintError, "不存在可局部修复"):
            targeted_exam_repair_plan(valid_blueprint_json())

        invalid = combined_targeted_repair_data()
        invalid["questions"][15]["rubric"] = [
            {"points": 9, "criterion": "评分点总和不足十分"}
        ]
        with self.assertRaisesRegex(ExamBlueprintError, "评分点合计"):
            targeted_exam_repair_plan(json.dumps(invalid, ensure_ascii=False))

        message = {
            "schema_version": 1,
            "kind": "message",
            "summary": "只说明命题原则。",
            "title": "",
            "course": "",
            "academic_year": "",
            "term": "",
            "exam_type": "",
            "exam_date": "",
            "duration_minutes": 0,
            "total_score": 0,
            "questions": [],
        }
        with self.assertRaisesRegex(ExamBlueprintError, "不是可局部修复"):
            targeted_exam_repair_plan(json.dumps(message, ensure_ascii=False))

    def test_apply_targeted_exam_repairs_changes_only_authorized_fields(self):
        source = combined_targeted_repair_data()
        repairs = complete_targeted_repairs()
        repaired = apply_targeted_exam_repairs(
            json.dumps(source, ensure_ascii=False),
            json.dumps(repairs, ensure_ascii=False),
        )
        repaired_data = blueprint_to_dict(repaired)

        for index, original_question in enumerate(source["questions"]):
            for field, value in original_question.items():
                if (index, field) in {(4, "options"), (10, "stem")}:
                    continue
                self.assertEqual(
                    repaired_data["questions"][index][field],
                    value,
                    f"第 {index + 1} 题字段 {field} 不应被局部修复改动",
                )
        self.assertEqual(
            repaired_data["questions"][4]["options"],
            repairs["choice_repairs"][0]["options"],
        )
        self.assertEqual(
            repaired_data["questions"][10]["stem"],
            repairs["fill_stem_repairs"][0]["stem"],
        )
        self.assertEqual(parse_exam_blueprint(canonical_blueprint_json(repaired)), repaired)

    def test_apply_targeted_exam_repairs_rejects_coverage_and_malformed_data(self):
        raw = json.dumps(combined_targeted_repair_data(), ensure_ascii=False)

        missing_choice = complete_targeted_repairs()
        missing_choice["choice_repairs"] = []
        with self.assertRaisesRegex(ExamBlueprintError, "未覆盖全部重复选项题.*第 5 题"):
            apply_targeted_exam_repairs(raw, json.dumps(missing_choice, ensure_ascii=False))

        missing_fill = complete_targeted_repairs()
        missing_fill["fill_stem_repairs"] = []
        with self.assertRaisesRegex(ExamBlueprintError, "未覆盖全部填空题题干.*第 11 题"):
            apply_targeted_exam_repairs(raw, json.dumps(missing_fill, ensure_ascii=False))

        extra = complete_targeted_repairs()
        extra["fill_stem_repairs"].append({
            "number": 12,
            "stem": "第一空[[BLANK]]，第二空[[BLANK]]。",
        })
        with self.assertRaisesRegex(ExamBlueprintError, "未授权的第 12 题填空题题干"):
            apply_targeted_exam_repairs(raw, json.dumps(extra, ensure_ascii=False))

        duplicate = complete_targeted_repairs()
        duplicate["fill_stem_repairs"].append(duplicate["fill_stem_repairs"][0].copy())
        with self.assertRaisesRegex(ExamBlueprintError, "重复提交第 11 题填空题题干"):
            apply_targeted_exam_repairs(raw, json.dumps(duplicate, ensure_ascii=False))

        locked = complete_targeted_repairs()
        locked["choice_repairs"][0]["options"][0] = "更改了已锁定选项"
        repaired = apply_targeted_exam_repairs(raw, json.dumps(locked, ensure_ascii=False))
        repaired_data = blueprint_to_dict(repaired)
        self.assertEqual(repaired_data["questions"][4]["options"][0],
                         combined_targeted_repair_data()["questions"][4]["options"][0])
        self.assertEqual(repaired_data["questions"][4]["options"][3],
                         locked["choice_repairs"][0]["options"][3])

        malformed = complete_targeted_repairs()
        malformed["fill_stem_repairs"][0]["stem"] = "修复后仍只有[[BLANK]]一个占位符。"
        with self.assertRaisesRegex(ExamBlueprintError, "必须且只能包含两个"):
            apply_targeted_exam_repairs(raw, json.dumps(malformed, ensure_ascii=False))

        wrong_shape = {"choice_repairs": [], "fill_stem_repairs": [], "extra": []}
        with self.assertRaisesRegex(ExamBlueprintError, "未允许字段.*extra"):
            apply_targeted_exam_repairs(raw, json.dumps(wrong_shape, ensure_ascii=False))

    def test_apply_targeted_exam_repairs_runs_final_full_validation(self):
        repairs = complete_targeted_repairs()
        source = combined_targeted_repair_data()
        repairs["choice_repairs"][0]["options"][3] = (
            source["questions"][4]["options"][1].replace("。", "")
        )
        with self.assertRaisesRegex(ExamBlueprintError, "第 5 题存在重复选项"):
            apply_targeted_exam_repairs(
                json.dumps(source, ensure_ascii=False),
                json.dumps(repairs, ensure_ascii=False),
            )


if __name__ == "__main__":
    unittest.main()
