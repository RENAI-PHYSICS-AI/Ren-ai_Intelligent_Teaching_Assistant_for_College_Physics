from pathlib import Path


APP_SOURCE = Path(__file__).resolve().parents[1] / "app.py"


def test_teacher_portal_is_authorized_before_history_and_ui_routing():
    source = APP_SOURCE.read_text(encoding="utf-8")

    gate = source.index("if is_verified_teacher(account_state):")
    history = source.index("load_initial_history(st.session_state.user_id, agent_mode)")
    assert gate < history
    assert "resolve_teacher_portal(" in source
    assert "render_teacher_portal_picker()" in source
    assert 'else ["智能助教", "可视化实验"]' in source


def test_teacher_portal_cards_keep_equal_height_on_desktop():
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert ".teacher-portal-card {box-sizing:border-box;display:flex;height:10.25rem" in source
    assert "@media (max-width:640px) {.teacher-portal-card {height:auto;min-height:0}}" in source


def test_exam_agent_prioritizes_private_kb_and_keeps_mode_isolated_calls():
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert "load_private_teacher_exam_kb(" in source
    assert "private_results = (" in source
    assert "public_results = kb.search(" in source
    assert source.index("private_results = (") < source.index("public_results = kb.search(")
    assert "max(top_k, 12)" not in source
    assert "exam_retrieval_task(" in source
    assert "agent_mode=agent_mode" in source
    assert "include_artifacts=agent_mode == PORTAL_TEACHING_EXAM" in source
    assert "TEACHER_EXAM_KB_FILE" in source
    assert "大学物理教研考试智能体" in source


def test_exam_agent_compiles_and_lazily_renders_named_downloads():
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert "build_exam_artifact_bundles(" in source
    assert 'for name in ("main.tex", "answer.tex")' in source
    assert "load_message_artifacts(" in source
    assert "render_message_artifacts(message)" in source
    assert "not is_full_exam_generation and now - last_render_at" in source
    assert "PDF/ASCII85 streams" in source


def test_exam_agent_has_fail_closed_structured_server_rendering():
    source = APP_SOURCE.read_text(encoding="utf-8")

    assert "parse_exam_blueprint(raw)" in source
    assert "render_exam_tex(blueprint)" in source
    assert '"name": "main.tex"' in source
    assert '"name": "answer.tex"' in source
    assert '"mime": "application/x-tex"' in source
    assert 'application/x-tex; charset=utf-8' not in source
    assert "结构、分值和重复题检查" in source
    assert "详细编译日志不会写入聊天正文" in source
