from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import uploaded_documents


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PDF = b"%PDF-1.7\nmock"


class _Page:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self):
        return self.text


class UploadedDocumentTests(unittest.TestCase):
    def test_attachment_types_use_signatures(self) -> None:
        pdf = {"name": "试卷.pdf", "mime": "application/pdf", "data": PDF}
        image = {"name": "题图.png", "mime": "image/png", "data": PNG}
        self.assertTrue(uploaded_documents.is_pdf_attachment(pdf))
        self.assertFalse(uploaded_documents.is_pdf_attachment({**pdf, "data": b"not-pdf"}))
        self.assertTrue(uploaded_documents.is_raster_image_attachment(image))
        self.assertEqual(uploaded_documents.raster_image_attachments([pdf, image]), [image])

    @patch.object(uploaded_documents, "_render_pdf_pages")
    @patch.object(uploaded_documents, "PdfReader")
    def test_pdf_text_and_page_images_are_prepared_for_models(self, reader, render) -> None:
        reader.return_value = SimpleNamespace(
            is_encrypted=False,
            pages=[_Page("一、选择题\n1. 质点运动"), _Page("二、计算题")],
        )
        render.return_value = [{"name": "试卷.pdf｜第1页.png", "mime": "image/png", "data": PNG}]
        result = uploaded_documents.prepare_uploaded_documents([
            {"name": "试卷.pdf", "mime": "application/pdf", "data": PDF}
        ])
        self.assertIn("试卷.pdf", result.context)
        self.assertIn("[第 1 页]", result.context)
        self.assertIn("质点运动", result.context)
        self.assertEqual(result.pdf_names, ("试卷.pdf",))
        self.assertEqual(len(result.vision_images), 1)
        self.assertEqual(result.warnings, ())

    @patch.object(uploaded_documents, "PdfReader")
    @patch.dict(
        "os.environ",
        {"PHYSICS_PDF_PASSWORDS": "wrong, correct-secret", "PHYSICS_EXAM_SOURCE_PASSWORDS": ""},
        clear=False,
    )
    def test_configured_passwords_are_tried_for_encrypted_pdf(self, reader) -> None:
        attempts: list[str] = []

        def decrypt(password: str) -> int:
            attempts.append(password)
            return 1 if password == "correct-secret" else 0

        reader.return_value = SimpleNamespace(
            is_encrypted=True,
            decrypt=decrypt,
            pages=[_Page("加密试卷")],
        )
        pages, password, count = uploaded_documents._extract_pdf_pages(PDF)
        self.assertEqual(password, "correct-secret")
        self.assertEqual(attempts, ["", "wrong", "correct-secret"])
        self.assertEqual(pages, ["加密试卷"])
        self.assertEqual(count, 1)

    @patch.dict(
        "os.environ",
        {"PHYSICS_PDF_PASSWORDS": "do-not-echo", "PHYSICS_EXAM_SOURCE_PASSWORDS": ""},
        clear=False,
    )
    @patch.object(uploaded_documents, "PdfReader")
    def test_pdf_password_failure_does_not_echo_secret(self, reader) -> None:
        reader.return_value = SimpleNamespace(
            is_encrypted=True,
            decrypt=lambda _password: 0,
            pages=[],
        )
        with self.assertRaisesRegex(ValueError, "本地配置的口令无法解锁") as caught:
            uploaded_documents._extract_pdf_pages(PDF)
        self.assertNotIn("do-not-echo", str(caught.exception))

    @patch.object(uploaded_documents, "_render_pdf_pages", return_value=[])
    @patch.object(uploaded_documents, "PdfReader")
    def test_scan_only_pdf_reports_actionable_warning(self, reader, _render) -> None:
        reader.return_value = SimpleNamespace(is_encrypted=False, pages=[_Page("")])
        result = uploaded_documents.prepare_uploaded_documents([
            {"name": "扫描卷.pdf", "mime": "application/pdf", "data": PDF}
        ])
        self.assertFalse(result.context)
        self.assertTrue(any("未提取到可用文字" in item for item in result.warnings))
        self.assertTrue(any("无法渲染页面图" in item for item in result.warnings))

    @patch.object(uploaded_documents, "PdfReader")
    def test_oversized_pdf_page_is_rejected_before_rendering(self, reader) -> None:
        page = _Page("异常页面")
        page.mediabox = SimpleNamespace(width=50_000, height=50_000)
        reader.return_value = SimpleNamespace(is_encrypted=False, pages=[page])
        with self.assertRaisesRegex(ValueError, "尺寸异常"):
            uploaded_documents._extract_pdf_pages(PDF)

    @patch.object(uploaded_documents, "_render_pdf_pages", return_value=[])
    @patch.object(uploaded_documents, "PdfReader")
    def test_multiple_pdfs_share_one_bundle_page_budget(self, reader, _render) -> None:
        reader.return_value = SimpleNamespace(
            is_encrypted=False,
            pages=[_Page("第一页"), _Page("第二页")],
        )
        attachments = [
            {"name": f"试卷{index}.pdf", "mime": "application/pdf", "data": PDF}
            for index in range(3)
        ]
        with patch.object(uploaded_documents, "MAX_BUNDLE_PDF_PAGES", 3):
            result = uploaded_documents.prepare_uploaded_documents(attachments)
        self.assertIn("试卷0.pdf", result.context)
        self.assertIn("试卷1.pdf", result.context)
        self.assertTrue(any("总页数" in item for item in result.warnings))


if __name__ == "__main__":
    unittest.main()
