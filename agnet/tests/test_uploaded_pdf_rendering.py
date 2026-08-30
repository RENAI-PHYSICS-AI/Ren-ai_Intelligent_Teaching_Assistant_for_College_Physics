from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import storage


APP_SOURCE = (APP_DIR / "app.py").read_text(encoding="utf-8")


def test_chat_input_accepts_pdf_without_removing_image_formats() -> None:
    assert 'file_type=["png", "jpg", "jpeg", "webp", "pdf"]' in APP_SOURCE
    assert "试卷图片或 PDF" in APP_SOURCE
    assert "请读取上传附件中的试题、答案或教学资料" in APP_SOURCE


def test_current_and_historical_messages_share_attachment_renderer() -> None:
    assert "def render_history_images(message: dict)" in APP_SOURCE
    assert 'render_history_images(user_message)' in APP_SOURCE
    assert '"📎 显示历史附件"' in APP_SOURCE


def test_pdf_text_and_rendered_pages_are_sent_to_the_models() -> None:
    assert "prepare_uploaded_documents(message_images)" in APP_SOURCE
    assert "model_images.extend(uploaded_document_bundle.vision_images)" in APP_SOURCE
    assert "context = context + (\"\\n\\n\" if context else \"\") + document_context" in APP_SOURCE
    assert "model_images," in APP_SOURCE


def test_uploaded_exam_answer_builds_answer_tex_and_pdf_without_exam_pipeline() -> None:
    assert "teacher_exam_request_kind == EXAM_REQUEST_SOURCE_MATERIAL" in APP_SOURCE
    assert "source_material_answer_requested(question)" in APP_SOURCE
    assert "if source_answer_artifacts_requested:" in APP_SOURCE
    assert "build_answer_artifact_bundle(" in APP_SOURCE
    assert '"name": answer_bundle.tex_name' in APP_SOURCE
    assert '"name": answer_bundle.pdf_name' in APP_SOURCE
    assert "generate_exam_artifacts=is_full_exam_generation" in APP_SOURCE


def test_teacher_artifact_renderer_is_not_limited_to_new_exam_files() -> None:
    assert 'st.caption("教研文件已在服务器端安全生成：")' in APP_SOURCE
    assert '"📎 加载教研文件"' in APP_SOURCE


def test_pdf_attachment_displays_name_and_download_button() -> None:
    assert 'pdf_attachment_data(image)' in APP_SOURCE
    assert 'st.caption(f"📄 PDF 附件：{name}")' in APP_SOURCE
    assert 'mime="application/pdf"' in APP_SOURCE
    assert 'key=f"download_message_pdf_{stable_key}_{index}"' in APP_SOURCE


def test_uploaded_pdf_round_trips_through_current_and_lazy_history_storage() -> None:
    payload = b"%PDF-1.7\nchat-upload\n%%EOF\n"
    upload = {"name": "大学物理试卷.pdf", "mime": "application/pdf", "data": payload}
    with tempfile.TemporaryDirectory() as temp_dir, patch.object(
        storage, "DB_FILE", Path(temp_dir) / "assistant.db"
    ):
        storage.init_db()
        user_id, _ = storage.create_user("pdf_upload_user", "strong-password")
        assert user_id is not None
        message_id = storage.save_message(
            user_id,
            {"role": "user", "content": "生成答案", "images": [upload]},
            agent_mode="teaching_exam",
        )

        current = storage.load_messages(user_id, agent_mode="teaching_exam")[0]
        assert current["images"] == [upload]

        history, has_more = storage.load_messages_page(
            user_id, agent_mode="teaching_exam"
        )
        assert not has_more
        assert history[0]["images"] == []
        assert history[0]["_has_images"] is True
        assert storage.load_message_images(
            user_id, message_id, agent_mode="teaching_exam"
        ) == [upload]


if __name__ == "__main__":
    for test_name, test_function in sorted(globals().copy().items()):
        if test_name.startswith("test_") and callable(test_function):
            test_function()
    print("uploaded PDF rendering tests: OK")
