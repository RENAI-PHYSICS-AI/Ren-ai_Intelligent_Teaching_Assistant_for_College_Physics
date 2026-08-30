from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch


TEST_DIR = Path(__file__).resolve().parent
APP_DIR = TEST_DIR.parent
for candidate in (APP_DIR, TEST_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import llm
from exam_blueprint import parse_exam_blueprint
from teacher_exam import exam_direct_output_policy, exam_generation_metadata_prompt
from test_exam_blueprint import valid_blueprint_json


def _page_header(page_number: int) -> str:
    return rf"""\begin{{center}}
天津仁爱学院试卷专用纸\\
学院\underline{{\hspace{{2cm}}}}\quad
专业\underline{{\hspace{{2cm}}}}\quad
\underline{{\hspace{{1cm}}}}班\quad
年级\underline{{\hspace{{1.5cm}}}}\quad
学号\underline{{\hspace{{2cm}}}}\quad
姓名\underline{{\hspace{{2cm}}}}\quad
共 3 页\quad 第 {page_number} 页
\end{{center}}"""


def _page_frame(body: str) -> str:
    return rf"""\begin{{mdframed}}[linewidth=2pt,linecolor=black,
innerleftmargin=2pt,innerrightmargin=8pt,innerbottommargin=35pt]
\begin{{multicols}}{{2}}
{body}
\end{{multicols}}
\end{{mdframed}}"""


def _direct_tex(main_body: str) -> str:
    first_page = _page_frame(rf"""\begin{{center}}
2025-2026学年第一学期\\
{main_body}
\end{{center}}
\begin{{center}}
\begin{{tabular}}{{|c|c|c|c|c|c|c|c|c|}}
\hline 题号 & 一 & 二 & 三 & 四 & 五 & 六 & 七 & 总分\\
\hline 得分 & & & & & & & &\\
\hline 评分人 & & & & & & & &\\
\hline
\end{{tabular}}
\end{{center}}
\raggedright
\textbf{{一、单项选择题（每题 3 分，共 30 分）}}
\begin{{enumerate}}
\item 第1题。
\item 第2题。
\item 第3题。
\item 第4题。
\item 第5题。
\columnbreak
\item 第6题。
\item 第7题。
\item 第8题。
\item 第9题。
\item 第10题。
\end{{enumerate}}""")
    second_page = _page_frame(r"""\raggedright
\textbf{二、填空题（每空 2 分，共 20 分）}
第11--15题。
\textbf{三、电学计算题（共 10 分）}
计算题题干。
\vspace{8em}
\columnbreak
\textbf{四、质点动力学计算题（共 10 分）}
计算题题干。
\vspace{8em}""")
    third_page = _page_frame(r"""\raggedright
\textbf{五、质点运动学计算题（共 10 分）}
计算题题干。
\vspace{8em}
\textbf{六、刚体定轴转动计算题（共 10 分）}
计算题题干。
\vspace{8em}
\columnbreak
\textbf{七、磁学计算题（共 10 分）}
计算题题干。
\vspace{8em}""")
    return rf"""已完成。
```latex
% main.tex
\documentclass[12pt,onecolumn]{{article}}
\usepackage[top=1.2cm,bottom=1.2cm,left=2cm,right=2cm]{{geometry}}
\geometry{{paperwidth=380mm,paperheight=265mm}}
\usepackage[UTF8]{{ctex}}
\usepackage{{mdframed,multicol,tabularx}}
\pagestyle{{empty}}
\begin{{document}}
{_page_header(1)}
{first_page}
\newpage
{_page_header(2)}
{second_page}
\newpage
{_page_header(3)}
{third_page}
\end{{document}}
```
```latex
% answer.tex
\documentclass{{ctexart}}
\begin{{document}}
参考答案
\end{{document}}
```"""


def test_missing_exam_metadata_is_requested_before_generation():
    prompt = exam_generation_metadata_prompt(
        "请帮我生成一份大学物理1的试卷，请结合网络的信息。",
        [],
    )
    assert "学年" in prompt
    assert "学期" in prompt
    assert "考试名称或类型" in prompt
    assert "考试日期可以暂不填写" in prompt


def test_metadata_followup_is_merged_and_non_makeup_policy_is_explicit():
    history = [{
        "role": "user",
        "content": "请帮我生成一份大学物理1的试卷，请结合网络的信息。",
    }]
    followup = "2025—2026学年，第一学期，考试名称：大学物理1期末考试"
    assert exam_generation_metadata_prompt(followup, history) == ""
    assert exam_direct_output_policy(followup, history) == (False, True, False)


def test_makeup_and_explicit_exam_date_are_detected():
    request = (
        "请生成2025—2026学年第二学期大学物理1补考试卷，"
        "考试名称：大学物理1补考，考试日期为2026年8月30日。"
    )
    assert exam_generation_metadata_prompt(request, []) == ""
    assert exam_direct_output_policy(request, []) == (True, True, True)


def test_stream_guard_returns_before_any_model_configuration_or_request():
    with (
        patch.object(llm, "setting", side_effect=AssertionError("不应读取模型配置")),
        patch.object(llm.requests, "post") as post,
    ):
        result = "".join(llm.stream_answer(
            "请生成大学物理1试卷",
            "知识库",
            [],
            agent_mode="teaching_exam",
        ))
    assert "请补充以下信息" in result
    post.assert_not_called()


def test_app_runs_metadata_preflight_before_retrieval_and_web_search():
    source = (APP_DIR / "app.py").read_text(encoding="utf-8")
    preflight = source.index(
        "exam_metadata_prompt = (\n        exam_generation_metadata_prompt"
    )
    retrieval = source.index("    search_started = time.monotonic()", preflight)
    web_search = source.index("    web_search_required = should_search_web(web_query)", retrieval)
    assert preflight < retrieval < web_search
    assert "web_query = scoped_exam_task if agent_mode == PORTAL_TEACHING_EXAM else question" in source
    assert "web_results = search_web(web_query)" in source


def test_unprovided_exam_date_is_rejected_in_direct_tex_and_blueprint():
    direct = _direct_tex("大学物理1期末考试\\\\（考试时间：2026年3月20日）")
    assert not llm._valid_direct_exam_tex(
        direct,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )
    assert llm._valid_direct_exam_tex(
        direct,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=True,
    )

    blueprint = parse_exam_blueprint(valid_blueprint_json())
    assert not llm._valid_exam_blueprint_policy(
        blueprint,
        must_be_makeup=True,
        exclude_relativity=True,
        exam_date_provided=False,
    )
    assert llm._valid_exam_blueprint_policy(
        blueprint,
        must_be_makeup=True,
        exclude_relativity=True,
        exam_date_provided=True,
    )


def test_direct_exam_requires_five_consecutive_titled_calculation_sections():
    valid = _direct_tex("大学物理1期末考试")
    assert llm._valid_direct_exam_tex(
        valid,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    generic = valid.replace("三、电学计算题", "三、计算题")
    assert not llm._valid_direct_exam_tex(
        generic,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    skipped = valid.replace("五、质点运动学计算题", "八、质点运动学计算题")
    assert not llm._valid_direct_exam_tex(
        skipped,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )


def test_direct_exam_requires_standard_three_page_bordered_layout_and_spacing():
    valid = _direct_tex("大学物理1期末考试")
    assert llm._valid_direct_exam_tex(
        valid,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    missing_border = valid.replace("linewidth=2pt", "linewidth=0pt", 1)
    assert not llm._valid_direct_exam_tex(
        missing_border,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    unclosed_page_frame = valid.replace(r"\end{mdframed}", "", 1)
    assert not llm._valid_direct_exam_tex(
        unclosed_page_frame,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    extra_page_break = valid.replace(r"\columnbreak", r"\newpage", 1)
    assert not llm._valid_direct_exam_tex(
        extra_page_break,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    left_aligned_header = valid.replace(r"\begin{center}", r"\begin{flushleft}", 1)
    left_aligned_header = left_aligned_header.replace(
        r"\end{center}", r"\end{flushleft}", 1
    )
    assert not llm._valid_direct_exam_tex(
        left_aligned_header,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    insufficient_space = valid.replace(r"\vspace{8em}", r"\vspace{7em}", 1)
    assert not llm._valid_direct_exam_tex(
        insufficient_space,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    early_space = valid.replace(
        "计算题题干。\n\\vspace{8em}",
        "\\vspace{8em}\n计算题题干。",
        1,
    )
    assert not llm._valid_direct_exam_tex(
        early_space,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    first_frame = valid.index(r"\begin{mdframed}")
    title_start = valid.index(r"\begin{center}", first_frame)
    choice_start = valid.index(r"\raggedright", title_start)
    title_and_score = valid[title_start:choice_start]
    title_on_right = valid[:title_start] + valid[choice_start:]
    first_break = title_on_right.index(r"\columnbreak", first_frame) + len(
        r"\columnbreak"
    )
    title_on_right = (
        title_on_right[:first_break]
        + "\n"
        + title_and_score
        + title_on_right[first_break:]
    )
    assert not llm._valid_direct_exam_tex(
        title_on_right,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    second_page = valid.index("第 2 页")
    fill_start = valid.index(r"\raggedright", second_page)
    third_section = valid.index(r"\textbf{三、", fill_start)
    fill_section = valid[fill_start:third_section]
    fill_on_right = valid[:fill_start] + valid[third_section:]
    second_break = fill_on_right.index(r"\columnbreak", fill_start) + len(
        r"\columnbreak"
    )
    fill_on_right = (
        fill_on_right[:second_break]
        + "\n"
        + fill_section
        + fill_on_right[second_break:]
    )
    assert not llm._valid_direct_exam_tex(
        fill_on_right,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    wrong_choice_split = valid.replace(
        "\\item 第5题。\n\\columnbreak",
        "\\columnbreak\n\\item 第5题。",
        1,
    )
    assert not llm._valid_direct_exam_tex(
        wrong_choice_split,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    wrong_page_two_split = valid.replace(
        "\\vspace{8em}\n\\columnbreak\n\\textbf{四、质点动力学计算题",
        "\\vspace{8em}\n\\textbf{四、质点动力学计算题",
        1,
    ).replace(
        "\\textbf{三、电学计算题",
        "\\columnbreak\n\\textbf{三、电学计算题",
        1,
    )
    assert not llm._valid_direct_exam_tex(
        wrong_page_two_split,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )

    wrong_page_three_split = valid.replace(
        "\\vspace{8em}\n\\columnbreak\n\\textbf{七、磁学计算题",
        "\\vspace{8em}\n\\textbf{七、磁学计算题",
        1,
    ).replace(
        "\\textbf{六、刚体定轴转动计算题",
        "\\columnbreak\n\\textbf{六、刚体定轴转动计算题",
        1,
    )
    assert not llm._valid_direct_exam_tex(
        wrong_page_three_split,
        must_be_makeup=False,
        exclude_relativity=True,
        exam_date_provided=False,
    )


def test_teacher_prompt_pins_template_alignment_page_blocks_and_answer_space():
    prompt = llm.TEACHER_EXAM_SYSTEM_PROMPT
    for requirement in (
        "380mm×265mm",
        "天津仁爱学院试卷专用纸",
        "学院/专业/班/年级/学号/姓名",
        "两次 \\newpage",
        "每个页面外框内必须恰好使用一次 \\columnbreak",
        "左栏严格排第 1--5 题",
        "第三大题答题区之后、第四大题标题之前换栏",
        "第六大题答题区之后、第七大题标题之前换栏",
        "\\columnbreak",
        "2pt 黑色边框",
        "至少 \\vspace{8em}",
        "计算题干最多320字",
        "25262大物1补考/answer.tex",
        "题号/答案横表",
        "\\hfill(分值)",
    ):
        assert requirement in prompt
