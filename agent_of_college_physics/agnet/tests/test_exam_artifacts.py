from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import exam_artifacts
from exam_artifacts import (
    ExamArtifactBundle,
    ExamArtifactBundles,
    TexCompilationError,
    TexExtractionError,
    UnsafeTexError,
    build_exam_artifact_bundles,
    build_exam_artifacts,
    build_exam_download_archive,
    extract_named_tex_documents,
    extract_tex_document,
    find_tex_compiler,
    stabilize_exam_tex_layout,
    validate_tex_document,
)


MINIMAL_TEX = r"""\documentclass{article}
\usepackage[UTF8]{ctex}
\usepackage{amsmath}
\begin{document}
大学物理试卷：$E=mc^2$。
\end{document}
"""


class ExamArtifactTests(unittest.TestCase):
    def test_extracts_only_complete_fenced_document(self) -> None:
        response = f"先说明命题范围。\n```latex\n{MINIMAL_TEX}```\n后续说明"
        self.assertEqual(extract_tex_document(response), MINIMAL_TEX)

    def test_rejects_incomplete_or_binary_model_output(self) -> None:
        with self.assertRaises(TexExtractionError):
            extract_tex_document(r"\documentclass{article}\begin{document}未完成")
        with self.assertRaises(TexExtractionError):
            extract_tex_document("正常文本\x00%PDF-1.7")

    def test_explicitly_rejects_pdf_and_ascii85_stream_text(self) -> None:
        for payload, label in (
            ("%PDF-1.7\n1 0 obj\nstream\n...", "PDF 数据流"),
            ("<~87cURD_*#TDfTZ)+T~>", "ASCII85 压缩流"),
        ):
            with self.subTest(payload=payload), self.assertRaises(TexExtractionError) as raised:
                extract_tex_document(payload + "\n" + MINIMAL_TEX)
            self.assertIn(label, str(raised.exception))

    def test_extracts_named_main_and_answer_documents_in_required_order(self) -> None:
        answer = MINIMAL_TEX.replace("大学物理试卷", "参考答案")
        response = (
            "### main.tex\n```latex\n" + MINIMAL_TEX + "```\n"
            "```tex filename=answer.tex\n" + answer + "```"
        )
        documents = extract_named_tex_documents(response)
        self.assertEqual([item.name for item in documents], ["main.tex", "answer.tex"])
        self.assertIn("大学物理试卷", documents[0].source)
        self.assertIn("参考答案", documents[1].source)

    def test_named_extraction_rejects_missing_duplicate_and_arbitrary_names(self) -> None:
        with self.assertRaises(TexExtractionError):
            extract_named_tex_documents("```latex main.tex\n" + MINIMAL_TEX + "```")
        duplicate = (
            "```latex main.tex\n" + MINIMAL_TEX + "```\n"
            "```latex main.tex\n" + MINIMAL_TEX + "```\n"
            "```latex answer.tex\n" + MINIMAL_TEX + "```"
        )
        with self.assertRaises(TexExtractionError):
            extract_named_tex_documents(duplicate)
        with self.assertRaises(TexExtractionError):
            extract_named_tex_documents("```latex payload.tex\n" + MINIMAL_TEX + "```")

    def test_accepts_exam_template_packages_and_ignores_comments(self) -> None:
        source = MINIMAL_TEX.replace(
            r"\usepackage{amsmath}",
            r"""\usepackage{geometry,mdframed,tabularx}
\usepackage{enumerate,enumitem,multicol}
\usepackage{amsfonts,amssymb,amsthm,amsmath}
% \input{/etc/passwd} is only documentation""",
        )
        self.assertEqual(validate_tex_document(source), ())

    def test_accepts_safe_tikz_and_rejects_external_or_unlisted_features(self) -> None:
        safe = MINIMAL_TEX.replace(
            r"\usepackage{amsmath}",
            r"""\usepackage{amsmath,tikz}
\usetikzlibrary{arrows.meta,angles,quotes}""",
        ).replace(
            r"\end{document}",
            r"""\begin{tikzpicture}
\draw[-{Stealth}] (0,0) -- (2,0) node[right] {$x$};
\draw (0,0) circle (0.4);
\end{tikzpicture}
\end{document}""",
        )
        self.assertEqual(validate_tex_document(safe), ())

        for unsafe in (
            safe.replace("arrows.meta,angles,quotes", "external"),
            safe.replace(r"\begin{tikzpicture}", r"\tikzexternalize\begin{tikzpicture}"),
            safe.replace(r"\draw (0,0) circle (0.4);", r"\draw plot file {secret.dat};"),
        ):
            with self.subTest(unsafe=unsafe), self.assertRaises(UnsafeTexError):
                validate_tex_document(unsafe)

        missing_package = safe.replace(r"\usepackage{amsmath,tikz}", r"\usepackage{amsmath}")
        with self.assertRaises(UnsafeTexError):
            validate_tex_document(missing_package)

    def test_stabilizes_one_oversized_frame_wrapping_all_columns(self) -> None:
        body = "\n".join(["大学物理试题内容"] * 180)
        source = (
            MINIMAL_TEX.replace(
                "大学物理试卷：$E=mc^2$。",
                "共 3 页\\n\\begin{mdframed}[linewidth=2pt]"
                "\\n\\begin{multicols}{2}\\n" + body
                + "\\n\\end{multicols}\\n\\end{mdframed}",
            )
            .replace(r"\usepackage{amsmath}", r"\usepackage{amsmath,mdframed,multicol}")
        )
        stabilized = stabilize_exam_tex_layout(source)
        self.assertNotIn(r"\begin{mdframed}", stabilized)
        self.assertNotIn(r"\end{mdframed}", stabilized)
        self.assertIn(r"\begin{multicols}{2}", stabilized)
        self.assertIn("大学物理试题内容", stabilized)

    def test_keeps_independent_standard_page_frames(self) -> None:
        framed = (
            r"\begin{mdframed}\begin{multicols}{2}第一页\end{multicols}\end{mdframed}"
            "\n\\newpage\n"
            r"\begin{mdframed}\begin{multicols}{2}第二页\end{multicols}\end{mdframed}"
        )
        source = MINIMAL_TEX.replace("大学物理试卷：$E=mc^2$。", "共 2 页\n" + framed)
        self.assertEqual(stabilize_exam_tex_layout(source), source)

    def test_blocks_file_access_shell_and_dynamic_macro_primitives(self) -> None:
        for dangerous in (
            r"\input{/etc/passwd}",
            r"\write18{touch /tmp/owned}",
            r"\openout1=secret",
            r"\directlua{os.execute('id')}",
            r"\catcode`\%=12",
            r"\csname input\endcsname{/etc/passwd}",
            r"\begin{filecontents}{payload.tex}x\end{filecontents}",
            r"^^69nput{/etc/passwd}",
        ):
            source = MINIMAL_TEX.replace(r"\end{document}", dangerous + "\n" + r"\end{document}")
            with self.subTest(dangerous=dangerous), self.assertRaises(UnsafeTexError):
                validate_tex_document(source)

    def test_rejects_unknown_packages_and_untrusted_graphics(self) -> None:
        unknown = MINIMAL_TEX.replace(r"\usepackage{amsmath}", r"\usepackage{shellesc}")
        with self.assertRaises(UnsafeTexError):
            validate_tex_document(unknown)
        for reference in ("/etc/passwd", "../secret.png", "https://example.test/a.png"):
            graphic = MINIMAL_TEX.replace(
                r"\end{document}",
                rf"\includegraphics{{{reference}}}" + "\n" + r"\end{document}",
            )
            with self.subTest(reference=reference), self.assertRaises(UnsafeTexError):
                validate_tex_document(graphic, allow_graphics=True)

    def test_compilation_uses_fixed_no_shell_escape_command_and_cleans_workspace(self) -> None:
        observed: dict[str, object] = {}

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            workdir = Path(kwargs["cwd"])
            observed["command"] = command
            observed["environment"] = kwargs["env"]
            observed["workdir"] = workdir
            (workdir / "exam.pdf").write_bytes(b"%PDF-1.7\nmock")
            return subprocess.CompletedProcess(command, 0, stdout=b"ok")

        with (
            tempfile.TemporaryDirectory() as root,
            patch.object(exam_artifacts, "find_tex_compiler", return_value=Path("/usr/bin/xelatex")),
            patch.object(exam_artifacts.subprocess, "run", side_effect=fake_run),
        ):
            result = build_exam_artifacts(
                f"```tex\n{MINIMAL_TEX}```",
                filename_stem="大物1 补考/测试",
                work_root=root,
            )
            workdir = observed["workdir"]
            self.assertFalse(workdir.exists())

        command = observed["command"]
        environment = observed["environment"]
        self.assertIn("-no-shell-escape", command)
        self.assertNotIn("shell=True", command)
        self.assertEqual(environment["openin_any"], "p")
        self.assertEqual(environment["openout_any"], "p")
        self.assertEqual(environment["TECTONIC_UNTRUSTED_MODE"], "1")
        self.assertEqual(result.tex_name, "大物1_补考_测试.tex")
        self.assertEqual(result.pdf_name, "大物1_补考_测试.pdf")
        self.assertEqual(result.pdf_bytes, b"%PDF-1.7\nmock")

    def test_compilation_timeout_is_reported_without_partial_artifacts(self) -> None:
        with (
            patch.object(exam_artifacts, "find_tex_compiler", return_value=Path("/usr/bin/xelatex")),
            patch.object(
                exam_artifacts.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(["xelatex"], timeout=5),
            ),
            self.assertRaises(TexCompilationError) as raised,
        ):
            build_exam_artifacts(MINIMAL_TEX, timeout_seconds=1)
        self.assertIn("5 秒", str(raised.exception))

    def test_builds_iterable_main_and_answer_bundles_independently(self) -> None:
        answer = MINIMAL_TEX.replace("大学物理试卷", "参考答案")
        response = (
            "```latex main.tex\n" + MINIMAL_TEX + "```\n"
            "```latex answer.tex\n" + answer + "```"
        )
        workdirs: list[Path] = []

        def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
            workdir = Path(kwargs["cwd"])
            workdirs.append(workdir)
            (workdir / "exam.pdf").write_bytes(b"%PDF-1.7\nmock")
            return subprocess.CompletedProcess(command, 0, stdout=b"ok")

        with (
            patch.object(exam_artifacts, "find_tex_compiler", return_value=Path("/usr/bin/xelatex")),
            patch.object(exam_artifacts.subprocess, "run", side_effect=fake_run),
        ):
            bundles = build_exam_artifact_bundles(response)

        self.assertEqual([item.tex_name for item in bundles], ["main.tex", "answer.tex"])
        self.assertEqual(bundles.get("answer.tex").pdf_name, "answer.pdf")
        self.assertEqual(len(bundles), 2)
        self.assertEqual(len(set(workdirs)), 2)
        self.assertTrue(all(not path.exists() for path in workdirs))

    def test_builds_zip_only_when_trusted_images_are_referenced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            asset_root = Path(temporary)
            (asset_root / "fig").mkdir()
            (asset_root / "fig" / "diagram.png").write_bytes(b"trusted-png")
            main_source = MINIMAL_TEX.replace(
                r"\usepackage{amsmath}", r"\usepackage{amsmath,graphicx}"
            ).replace(
                r"\end{document}",
                r"\includegraphics[width=.4\textwidth]{fig/diagram}" + "\n" + r"\end{document}",
            )
            answer_source = MINIMAL_TEX.replace("大学物理试卷", "参考答案")
            bundles = ExamArtifactBundles((
                ExamArtifactBundle(
                    tex_name="main.tex",
                    tex_bytes=main_source.encode("utf-8"),
                    pdf_name="main.pdf",
                    pdf_bytes=b"%PDF-1.7\nmain",
                    compiler="xelatex",
                    elapsed_seconds=0.1,
                ),
                ExamArtifactBundle(
                    tex_name="answer.tex",
                    tex_bytes=answer_source.encode("utf-8"),
                    pdf_name="answer.pdf",
                    pdf_bytes=b"%PDF-1.7\nanswer",
                    compiler="xelatex",
                    elapsed_seconds=0.1,
                ),
            ))
            archive = build_exam_download_archive(
                bundles,
                asset_root=asset_root,
                filename_stem="大物1 补考/完整包",
            )

        self.assertIsNotNone(archive)
        assert archive is not None
        self.assertEqual(archive.zip_name, "大物1_补考_完整包.zip")
        self.assertEqual(archive.zip_mime, "application/zip")
        self.assertEqual(
            archive.member_names,
            ("main.tex", "main.pdf", "answer.tex", "answer.pdf", "fig/diagram.png"),
        )
        with zipfile.ZipFile(io.BytesIO(archive.zip_bytes)) as packaged:
            self.assertEqual(packaged.namelist(), list(archive.member_names))
            self.assertEqual(packaged.read("fig/diagram.png"), b"trusted-png")
            self.assertEqual(packaged.read("main.tex"), main_source.encode("utf-8"))

    def test_zip_is_omitted_without_images_and_rejects_untrusted_paths(self) -> None:
        bundle = ExamArtifactBundle(
            tex_name="main.tex",
            tex_bytes=MINIMAL_TEX.encode("utf-8"),
            pdf_name="main.pdf",
            pdf_bytes=b"%PDF-1.7\nmain",
            compiler="xelatex",
            elapsed_seconds=0.1,
        )
        self.assertIsNone(build_exam_download_archive((bundle,)))
        forced = build_exam_download_archive((bundle,), minimum_graphics=0)
        self.assertIsNotNone(forced)

        unsafe_source = MINIMAL_TEX.replace(
            r"\usepackage{amsmath}", r"\usepackage{amsmath,graphicx}"
        ).replace(
            r"\end{document}",
            r"\includegraphics{../secret.png}" + "\n" + r"\end{document}",
        )
        unsafe = ExamArtifactBundle(
            tex_name="main.tex",
            tex_bytes=unsafe_source.encode("utf-8"),
            pdf_name="main.pdf",
            pdf_bytes=b"%PDF-1.7\nmain",
            compiler="xelatex",
            elapsed_seconds=0.1,
        )
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(UnsafeTexError):
            build_exam_download_archive((unsafe,), asset_root=temporary)

    def test_tectonic_uses_v2_untrusted_cached_compile_command(self) -> None:
        command = exam_artifacts._compiler_command(
            Path("/opt/physics/.runtime/tectonic/tectonic"), Path("/tmp/exam"), "exam.tex"
        )
        self.assertEqual(Path(command[0]).name, "tectonic")
        self.assertEqual(command[1:3], ["-X", "compile"])
        self.assertIn("--untrusted", command)
        self.assertIn("--only-cached", command)
        self.assertEqual(command[-1], "exam.tex")

    def test_finds_project_parent_runtime_tectonic_before_path_compilers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app_dir = Path(temporary) / "project" / "agnet"
            runtime = app_dir.parent / ".runtime" / "tectonic" / "tectonic"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"test executable")
            runtime.chmod(0o755)
            with (
                patch.object(exam_artifacts, "__file__", str(app_dir / "exam_artifacts.py")),
                patch.object(exam_artifacts.shutil, "which", return_value=None),
                patch.dict(exam_artifacts.os.environ, {"PHYSICS_TEX_COMPILER": ""}),
            ):
                found = find_tex_compiler()
        self.assertEqual(found, runtime.resolve())


if __name__ == "__main__":
    unittest.main()
