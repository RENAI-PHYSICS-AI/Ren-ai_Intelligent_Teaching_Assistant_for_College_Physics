from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


APP_SOURCE = Path(__file__).resolve().parents[1] / "app.py"


class ExamBlueprintError(ValueError):
    pass


class ExamArtifactError(RuntimeError):
    pass


def load_prepare_exam_response(*, compile_fails: bool = False):
    tree = ast.parse(APP_SOURCE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "prepare_exam_response"
    )

    def build_bundles(_source: str):
        if compile_fails:
            raise ExamArtifactError("compile failed")
        return [
            SimpleNamespace(
                pdf_name="main.pdf",
                pdf_mime="application/pdf",
                pdf_bytes=b"%PDF-test",
            ),
            SimpleNamespace(
                pdf_name="answer.pdf",
                pdf_mime="application/pdf",
                pdf_bytes=b"%PDF-answer",
            ),
        ]

    namespace = {
        "ExamArtifactError": ExamArtifactError,
        "ExamBlueprintError": ExamBlueprintError,
        "TEACHER_EXAM_TEMPLATE_FILE": Path("missing-template/main.tex"),
        "build_exam_artifact_bundles": build_bundles,
        "build_exam_download_archive": lambda _bundles, **_kwargs: None,
        "_append_exam_download_archive": lambda _artifacts, _archive: None,
        "exam_output_looks_binary": lambda _raw: False,
        "normalize_latex": lambda text: text,
        "parse_exam_blueprint": lambda _raw: SimpleNamespace(
            kind="exam",
            summary="已完成命题",
        ),
        "render_exam_tex": lambda _blueprint: (
            "\\documentclass{ctexart}\\begin{document}试卷\\end{document}",
            "\\documentclass{ctexart}\\begin{document}答案\\end{document}",
        ),
        "stabilize_exam_tex_layout": lambda source: source,
        "validate_tex_document": lambda _source: (),
    }
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(APP_SOURCE), "exec"),
        namespace,
    )
    return namespace["prepare_exam_response"]


def test_exam_progress_events_follow_real_validation_and_compile_order() -> None:
    prepare = load_prepare_exam_response()
    events: list[str] = []

    response, artifacts, status = prepare("{}", progress_callback=events.append)

    assert events == [
        "tex_validation_started",
        "tex_validation_complete",
        "pdf_compile_started",
        "pdf_compile_complete",
    ]
    assert status == ""
    assert "已完成命题" in response
    assert [item["name"] for item in artifacts] == [
        "main.tex",
        "answer.tex",
        "main.pdf",
        "answer.pdf",
    ]


def test_exam_progress_reports_pdf_failure_instead_of_completion() -> None:
    prepare = load_prepare_exam_response(compile_fails=True)
    events: list[str] = []

    _response, artifacts, status = prepare("{}", progress_callback=events.append)

    assert events[-2:] == ["pdf_compile_started", "pdf_compile_failed"]
    assert "pdf_compile_complete" not in events
    assert status == "pdf_compile_failed"
    assert [item["name"] for item in artifacts] == ["main.tex", "answer.tex"]


def test_exam_ui_creates_progress_before_retrieval_and_names_all_five_steps() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")

    request_block = source[source.index("if question:"):]
    assert request_block.index('exam_assistant_container = st.chat_message("assistant")') < request_block.index(
        "search_started = time.monotonic()"
    )
    for label in (
        "步骤 1/5：正在检索知识库与教师命题资料",
        "步骤 2/5：正在按需联网补充并整理命题依据",
        "步骤 3/5：正在生成结构化试题、参考答案与评分标准",
        "步骤 4/5：正在校验结构、分值并套用固定 TeX 模板",
        "步骤 5/5：正在编译试卷与参考答案 PDF",
    ):
        assert label in request_block
    assert "模型只生成一次结构化题目与答案" in request_block
    assert "内部推理约" in request_block
    assert "已接收结构化内容约" in request_block
    assert "字符/秒" in request_block
    assert "正在等待专用命题模型空闲" in request_block
    assert "前一份完成后本任务会自动开始" in request_block
    assert "命题模型排队耗时" in request_block
    assert "generation_lock.release()" in request_block
    assert "isinstance(exc, ExamGenerationError)" in request_block
    assert "结构化试卷未通过校验或超过时限" in request_block
    assert "progress_callback=(" in request_block
    assert "def update_exam_generation_event(" in request_block
    assert 'event == "choice_option_repair_started"' in request_block
    assert 'event == "choice_option_repair_completed"' in request_block
    assert 'event == "choice_option_repair_failed"' in request_block
    assert "仅局部修复冲突选项" in request_block
    assert "其余试题不会重新生成" in request_block
    assert "正在重新校验整卷" in request_block
    assert "exam_event_callback=(" in request_block
    assert "update_exam_generation_event" in request_block
    assert "progress_callback=update_exam_artifact_progress" in request_block


def test_exam_ui_reports_targeted_structural_repairs_without_regenerating_content() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    request_block = source[source.index("if question:"):]

    for event in (
        "targeted_exam_repair_started",
        "targeted_exam_repair_completed",
        "targeted_exam_repair_failed",
    ):
        assert f'event == "{event}"' in request_block
    assert 'payload.get("choice_question_numbers", ())' in request_block
    assert 'payload.get("fill_question_numbers", ())' in request_block
    assert "重复选项" in request_block
    assert "填空标记" in request_block
    assert "仅修复以上列出的结构字段" in request_block
    assert "其他题目、答案和评分标准均不重新生成" in request_block
    assert "修复后将重新校验完整试卷" in request_block
    assert "正在重新校验完整试卷" in request_block

    # Legacy choice-only callbacks remain available during rolling deployment.
    for event in (
        "choice_option_repair_started",
        "choice_option_repair_completed",
        "choice_option_repair_failed",
    ):
        assert f'event == "{event}"' in request_block


def test_only_full_exam_intent_enters_blueprint_and_artifact_pipeline() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    request_block = source[source.index("if question:"):]

    assert "classify_teacher_exam_request(" in request_block
    assert "has_attachments=bool(message_images)" in request_block
    assert "teacher_exam_request_kind == EXAM_REQUEST_FULL_GENERATION" in request_block
    assert "if is_full_exam_generation:" in request_block
    assert "generate_exam_artifacts=is_full_exam_generation" in request_block
    assert "if not is_full_exam_generation:" in request_block


def test_all_teacher_exam_requests_share_the_single_deepseek_queue() -> None:
    source = APP_SOURCE.read_text(encoding="utf-8")
    request_block = source[source.index("if question:"):]
    tracked_start = request_block.index("def tracked_stream():")
    tracked_block = request_block[
        tracked_start:request_block.index("        try:\n            last_render_at", tracked_start)
    ]

    assert "uses_dedicated_exam_model = agent_mode == PORTAL_TEACHING_EXAM" in request_block
    assert "if uses_dedicated_exam_model:" in tracked_block
    assert "generation_lock = exam_generation_lock()" in tracked_block
    assert "generation_lock.acquire(timeout=1.0)" in tracked_block
    assert "正在等待教研模型空闲" in tracked_block
    assert "generation_lock.release()" in request_block
    assert "if is_full_exam_generation:\n                    generation_lock" not in tracked_block
