from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace


APP_SOURCE = Path(__file__).resolve().parents[1] / "app.py"
if str(APP_SOURCE.parent) not in sys.path:
    sys.path.insert(0, str(APP_SOURCE.parent))

from exam_blueprint import ExamBlueprintError, parse_exam_blueprint


HELPERS = {
    "exam_output_looks_binary",
    "exam_response_summary",
    "exam_retrieval_task",
    "merge_exam_retrieval_results",
}
CONSTANTS = {
    "_EXAM_TEX_FENCE_RE",
    "_EXAM_TEX_LABEL_RE",
    "_EXAM_BINARY_MARKER_RE",
    "_EXAM_REVISION_WORDS",
}


def load_helpers() -> dict:
    tree = ast.parse(APP_SOURCE.read_text(encoding="utf-8"))
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id in CONSTANTS for target in targets):
                selected.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in HELPERS:
            selected.append(node)
    namespace = {"re": re}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(APP_SOURCE), "exec"), namespace)
    return namespace


def load_prepare_exam_response(**overrides) -> dict:
    tree = ast.parse(APP_SOURCE.read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "prepare_exam_response"
    ]
    namespace = {
        "ExamBlueprintError": type("ExamBlueprintError", (RuntimeError,), {}),
        **overrides,
    }
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(APP_SOURCE), "exec"),
        namespace,
    )
    return namespace


def test_exam_binary_stream_is_rejected_but_chinese_prose_is_not() -> None:
    helper = load_helpers()["exam_output_looks_binary"]
    ascii85_like = "(&9%!54<C,-;)#C@750G(D6\"-8C,B'>57%.C@2.20./0=D%'2," * 10

    assert helper("%PDF-1.7\n1 0 obj\nstream")
    assert helper("<~87cURD_*#TDfTZ)+T~>")
    assert helper(ascii85_like)
    assert helper("已生成试卷。\n" + ascii85_like)
    assert not helper("已按知识库重新命题，试卷与答案正在编译。")


def test_valid_blueprint_bypasses_generic_binary_density_heuristic() -> None:
    binary_checks = []
    events = []
    dense_summary = "(&9%!54<C,-;)#C@750G(D6\"-8C,B'>57%.C@2.20./0=D%'2," * 10
    raw = json.dumps({
        "schema_version": 1,
        "kind": "message",
        "summary": dense_summary,
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
    generic_binary_check = load_helpers()["exam_output_looks_binary"]
    assert generic_binary_check(raw)

    namespace = load_prepare_exam_response(
        ExamBlueprintError=ExamBlueprintError,
        parse_exam_blueprint=parse_exam_blueprint,
        exam_output_looks_binary=lambda raw: binary_checks.append(raw) or True,
        normalize_latex=lambda text: text,
    )

    response, artifacts, status = namespace["prepare_exam_response"](
        raw,
        progress_callback=events.append,
    )

    assert response == dense_summary
    assert artifacts == []
    assert status == ""
    assert binary_checks == []
    assert events == ["tex_validation_started", "artifact_generation_skipped"]


def test_unparseable_binary_stream_still_uses_generic_binary_guard() -> None:
    events = []
    error_type = type("ExamBlueprintError", (RuntimeError,), {})

    def reject_blueprint(_raw):
        raise error_type("not json")

    namespace = load_prepare_exam_response(
        ExamBlueprintError=error_type,
        parse_exam_blueprint=reject_blueprint,
        exam_output_looks_binary=lambda _raw: True,
    )

    response, artifacts, status = namespace["prepare_exam_response"](
        "%PDF-1.7\nstream",
        progress_callback=events.append,
    )

    assert "不可显示的文件数据流" in response
    assert artifacts == []
    assert status == "binary_output"
    assert events == ["tex_validation_started", "tex_validation_failed"]


def test_exam_summary_removes_named_tex_fences() -> None:
    helper = load_helpers()["exam_response_summary"]
    raw = (
        "已按要求修正重复题。\n\n文件：main.tex\n"
        "```latex\n\\documentclass{article}\n\\begin{document}题目\\end{document}\n```\n"
        "文件：answer.tex\n"
        "```tex\n\\documentclass{article}\n\\begin{document}答案\\end{document}\n```"
    )

    assert helper(raw) == "已按要求修正重复题。"


def test_short_exam_revision_retrieval_includes_previous_teacher_task() -> None:
    helper = load_helpers()["exam_retrieval_task"]
    history = [
        {"role": "user", "content": "请生成大学物理1补考试卷，总分100分。"},
        {"role": "assistant", "content": "已经生成。"},
    ]

    query = helper("题目有重复，计算题严格每题10分。", history)
    assert "上一轮教师命题任务" in query
    assert "请生成大学物理1补考试卷" in query
    assert "本轮修订要求" in query


def test_private_retrieval_results_stay_first_and_are_deduplicated() -> None:
    helper = load_helpers()["merge_exam_retrieval_results"]
    private = SimpleNamespace(relative_path="规范.md", locator="全文", text="命题规范")
    duplicate = SimpleNamespace(relative_path="规范.md", locator="全文", text="命题规范")
    public = SimpleNamespace(relative_path="教材.pdf", locator="第1页", text="教材内容")

    merged = helper([(private, 1.0)], [(duplicate, 9.0), (public, 2.0)])
    assert [item[0] for item in merged] == [private, public]
