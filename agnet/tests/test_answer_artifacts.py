from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import answer_artifacts
from exam_artifacts import ExamArtifactBundle, TexCompilationError, validate_tex_document


class AnswerArtifactsTests(unittest.TestCase):
    def test_untrusted_tex_commands_and_special_characters_are_escaped(self) -> None:
        source = answer_artifacts.render_answer_tex(
            r"\input{secret.tex} 与 \end{document}；50% $x_1$ #1 & A^2 ~ ok",
            title=r"答案 \input{title}",
        )

        self.assertNotIn(r"\input{secret.tex}", source)
        self.assertNotIn(r"\input{title}", source)
        self.assertIn(r"\textbackslash{}input\{secret.tex\}", source)
        self.assertIn(r"\textbackslash{}end\{document\}", source)
        self.assertIn(r"50\% $x_1$ \#1 \& A\textasciicircum{}2", source)
        self.assertEqual(validate_tex_document(source), ())

    def test_safe_physics_math_is_typeset_but_unsafe_math_is_escaped(self) -> None:
        source = answer_artifacts.render_answer_tex(
            r"由 $F=ma$ 得 $$a=\frac{F}{m}\approx 9.8\,\mathrm{m/s^2}$$；"
            r"恶意片段 $\input{secret.tex}$ 必须原样显示。"
        )

        self.assertIn("$F=ma$", source)
        self.assertIn(r"\[" + "\n" + r"a=\frac{F}{m}\approx 9.8\,\mathrm{m/s^2}", source)
        self.assertNotIn(r"$\input{secret.tex}$", source)
        self.assertIn(r"\$\textbackslash{}input\{secret.tex\}\$", source)
        self.assertEqual(validate_tex_document(source), ())

    def test_markdown_headings_and_lists_use_only_trusted_structure(self) -> None:
        source = answer_artifacts.render_answer_tex(
            "# 参考答案\n## 一、选择题\n- A\n- B\n\n1. 第一步\n2. 第二步"
        )

        self.assertIn(r"\section*{参考答案}", source)
        self.assertIn(r"\subsection*{一、选择题}", source)
        self.assertIn("\\begin{itemize}\n\\item A\n\\item B\n\\end{itemize}", source)
        self.assertIn("\\begin{enumerate}\n\\item 第一步\n\\item 第二步\n\\end{enumerate}", source)

    def test_answer_filename_uses_pdf_name_and_handles_multiple_files(self) -> None:
        self.assertEqual(answer_artifacts.answer_filename_stem(None), "大学物理参考答案")
        self.assertEqual(
            answer_artifacts.answer_filename_stem([r"C:\upload\25262大物1补考试卷.pdf"]),
            "25262大物1补考试卷_参考答案",
        )
        self.assertEqual(
            answer_artifacts.answer_filename_stem(["试卷 A.pdf", "../试卷B.PDF"]),
            "试卷_A_等2份_参考答案",
        )
        self.assertEqual(
            answer_artifacts.answer_filename_stem("已有参考答案.pdf"),
            "已有_参考答案",
        )

    def test_build_prefers_explicit_complete_safe_answer_tex(self) -> None:
        response = (
            "答案文件如下。\n"
            "```latex answer.tex\n"
            "\\documentclass{article}\n"
            "\\usepackage{amsmath}\n"
            "\\begin{document}\n"
            "\\[\\begin{aligned}E&=mc^2\\\\p&=h/\\lambda\\end{aligned}\\]\n"
            "\\end{document}\n"
            "```\n"
        )
        expected = ExamArtifactBundle(
            tex_name="期末试卷_参考答案.tex",
            tex_bytes=b"tex",
            pdf_name="期末试卷_参考答案.pdf",
            pdf_bytes=b"%PDF-test",
            compiler="xelatex",
            elapsed_seconds=0.2,
        )
        with (
            patch.object(
                answer_artifacts,
                "stabilize_exam_tex_layout",
                wraps=answer_artifacts.stabilize_exam_tex_layout,
            ) as stabilize,
            patch.object(
                answer_artifacts,
                "validate_tex_document",
                wraps=answer_artifacts.validate_tex_document,
            ) as validate,
            patch.object(
                answer_artifacts, "build_exam_artifacts", return_value=expected
            ) as build,
        ):
            result = answer_artifacts.build_answer_artifact_bundle(
                response,
                pdf_names=["期末试卷.pdf"],
            )

        self.assertIs(result, expected)
        source = build.call_args.args[0]
        self.assertTrue(source.startswith(r"\documentclass{article}"))
        self.assertIn(r"\begin{aligned}E&=mc^2", source)
        self.assertIn(r"p&=h/\lambda\end{aligned}", source)
        self.assertNotIn("答案文件如下", source)
        stabilize.assert_called_once()
        validate.assert_called_once_with(source)

    def test_unsafe_named_answer_tex_falls_back_to_escaped_markdown(self) -> None:
        response = (
            "```latex answer.tex\n"
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\input{secret.tex}\n"
            "\\end{document}\n"
            "```\n"
        )
        expected = ExamArtifactBundle(
            tex_name="大学物理参考答案.tex",
            tex_bytes=b"tex",
            pdf_name="大学物理参考答案.pdf",
            pdf_bytes=b"%PDF-test",
            compiler="xelatex",
            elapsed_seconds=0.2,
        )
        with patch.object(
            answer_artifacts, "build_exam_artifacts", return_value=expected
        ) as build:
            result = answer_artifacts.build_answer_artifact_bundle(response)

        self.assertIs(result, expected)
        source = build.call_args.args[0]
        self.assertTrue(source.startswith(r"\documentclass[UTF8,a4paper,12pt]{ctexart}"))
        self.assertNotIn(r"\input{secret.tex}", source)
        self.assertIn(r"\textbackslash{}input\{secret.tex\}", source)
        self.assertNotIn(r"\ttfamily", source)
        self.assertIn(r"\rmfamily", source)
        self.assertEqual(validate_tex_document(source), ())

    def test_incomplete_named_answer_tex_falls_back_to_markdown(self) -> None:
        response = "```latex answer.tex\n只有片段 $I^2/2$\n```"
        expected = ExamArtifactBundle(
            tex_name="大学物理参考答案.tex",
            tex_bytes=b"tex",
            pdf_name="大学物理参考答案.pdf",
            pdf_bytes=b"%PDF-test",
            compiler="xelatex",
            elapsed_seconds=0.2,
        )
        with patch.object(
            answer_artifacts, "build_exam_artifacts", return_value=expected
        ) as build:
            answer_artifacts.build_answer_artifact_bundle(response)

        source = build.call_args.args[0]
        self.assertTrue(source.startswith(r"\documentclass[UTF8,a4paper,12pt]{ctexart}"))
        self.assertIn("$I^2/2$", source)
        self.assertEqual(validate_tex_document(source), ())

    def test_unnamed_or_graphics_dependent_tex_falls_back_safely(self) -> None:
        complete = (
            "\\documentclass{article}\n"
            "\\begin{document}\nAnswer\n\\end{document}\n"
        )
        cases = {
            "unnamed": f"```latex\n{complete}```",
            "graphics": (
                "```latex answer.tex\n"
                "\\documentclass{article}\n"
                "\\usepackage{graphicx}\n"
                "\\begin{document}\n"
                "\\includegraphics{question.png}\n"
                "\\end{document}\n"
                "```"
            ),
            "duplicate": (
                f"```latex answer.tex\n{complete}```\n"
                f"```latex answer.tex\n{complete}```"
            ),
        }
        expected = ExamArtifactBundle(
            tex_name="大学物理参考答案.tex",
            tex_bytes=b"tex",
            pdf_name="大学物理参考答案.pdf",
            pdf_bytes=b"%PDF-test",
            compiler="xelatex",
            elapsed_seconds=0.2,
        )
        for label, response in cases.items():
            with self.subTest(label=label), patch.object(
                answer_artifacts, "build_exam_artifacts", return_value=expected
            ) as build:
                answer_artifacts.build_answer_artifact_bundle(response)
                source = build.call_args.args[0]
                self.assertTrue(
                    source.startswith(r"\documentclass[UTF8,a4paper,12pt]{ctexart}")
                )
                self.assertEqual(validate_tex_document(source), ())

    def test_valid_named_tex_compile_failure_propagates_without_fallback(self) -> None:
        response = (
            "```latex answer.tex\n"
            "\\documentclass{article}\n"
            "\\begin{document}\nAnswer\n\\end{document}\n"
            "```"
        )
        with (
            patch.object(
                answer_artifacts,
                "render_answer_tex",
                wraps=answer_artifacts.render_answer_tex,
            ) as fallback,
            patch.object(
                answer_artifacts,
                "build_exam_artifacts",
                side_effect=TexCompilationError("compile failed"),
            ),
        ):
            with self.assertRaisesRegex(TexCompilationError, "compile failed"):
                answer_artifacts.build_answer_artifact_bundle(response)
        fallback.assert_not_called()

    def test_legacy_row_breaks_and_unbreakable_answer_frames_are_stabilized(self) -> None:
        response = (
            "```latex answer.tex\n"
            "\\documentclass{article}\n"
            "\\usepackage{mdframed,multicol}\n"
            "\\begin{document}\n"
            "Title\\\n$$\n2pt]\n"
            "\\begin{mdframed}[linewidth=2pt]\n"
            "\\begin{multicols}{2}\nAnswer\n\\end{multicols}\n"
            "\\end{mdframed}\n"
            "\\end{document}\n"
            "```"
        )
        expected = ExamArtifactBundle(
            tex_name="大学物理参考答案.tex",
            tex_bytes=b"tex",
            pdf_name="大学物理参考答案.pdf",
            pdf_bytes=b"%PDF-test",
            compiler="tectonic",
            elapsed_seconds=0.2,
        )
        with patch.object(
            answer_artifacts, "build_exam_artifacts", return_value=expected
        ) as build:
            answer_artifacts.build_answer_artifact_bundle(response)

        source = build.call_args.args[0]
        self.assertIn("Title" + r"\\[2pt]", source)
        self.assertNotIn("Title\\\n$$\n2pt]", source)
        self.assertNotIn(r"\begin{mdframed}", source)
        self.assertNotIn(r"\end{mdframed}", source)
        self.assertIn(r"\begin{multicols}{2}", source)
        self.assertIn("Answer frame removed server-side", source)
        self.assertEqual(validate_tex_document(source), ())

    def test_build_delegates_safe_source_to_existing_exam_builder(self) -> None:
        expected = ExamArtifactBundle(
            tex_name="期末试卷_参考答案.tex",
            tex_bytes=b"tex",
            pdf_name="期末试卷_参考答案.pdf",
            pdf_bytes=b"%PDF-test",
            compiler="xelatex",
            elapsed_seconds=0.2,
        )
        with patch.object(
            answer_artifacts, "build_exam_artifacts", return_value=expected
        ) as build:
            result = answer_artifacts.build_answer_artifact_bundle(
                r"答案中出现 \write18 也只能作为文本",
                pdf_names=["期末试卷.pdf"],
                title="参考答案",
                compiler="xelatex",
                work_root="work",
                timeout_seconds=30,
            )

        self.assertIs(result, expected)
        source = build.call_args.args[0]
        self.assertIn(r"\textbackslash{}write18", source)
        self.assertNotIn(r"\write18", source)
        self.assertEqual(build.call_args.kwargs, {
            "filename_stem": "期末试卷_参考答案",
            "compiler": "xelatex",
            "work_root": "work",
            "timeout_seconds": 30,
        })


if __name__ == "__main__":
    unittest.main()
