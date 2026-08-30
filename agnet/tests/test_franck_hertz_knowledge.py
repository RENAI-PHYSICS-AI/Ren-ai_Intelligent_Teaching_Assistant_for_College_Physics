from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_kb
import build_franck_hertz_import
from rag import KnowledgeBase


EXPECTED_MARKDOWN = {
    "弗兰克-赫兹可视化实验方案.md",
    "弗兰克-赫兹文献导读.md",
    "README.md",
}
EXPECTED_PDFS = {
    "Franck_Hertz_1914_Mercury_Collisions.pdf",
    "James_Franck_1926_Nobel_Lecture.pdf",
    "Gustav_Hertz_1926_Nobel_Lecture.pdf",
    "MIT_OCW_Franck_Hertz_Lab_Guide.pdf",
    "NIST_Saloman_2006_Neutral_Mercury.pdf",
    "CODATA_2022_Fundamental_Constants.pdf",
}
EXPECTED_ROUTES = ["apparatus", "curve", "analysis", "uncertainty"]
MATERIAL_DIR = APP_DIR.parent / "教学素材" / "物理实验" / "弗兰克-赫兹实验"
REFERENCE_DIR = MATERIAL_DIR / "ref"
IMPORT_DIR = APP_DIR / "knowledge_base" / "imports"
IMPORT_PATH = IMPORT_DIR / "franck_hertz.jsonl"
IMPORT_MANIFEST_PATH = IMPORT_DIR / "franck_hertz.manifest.json"
IMPORT_REPORT_PATH = IMPORT_DIR / "franck_hertz.extraction_report.json"
MAIN_CHUNKS_PATH = APP_DIR / "knowledge_base" / "chunks.jsonl"
MAIN_MANIFEST_PATH = APP_DIR / "knowledge_base" / "manifest.json"
REQUIRED_FIELDS = {
    "id",
    "source",
    "source_type",
    "page",
    "chunk",
    "text",
    "title",
    "year",
    "language",
    "topic",
    "locator",
}


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class FranckHertzRegistrationTests(unittest.TestCase):
    def test_collection_uses_authoritative_modern_physics_chapter(self) -> None:
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("franck_hertz"),
            ("弗兰克-赫兹实验", "第12章 波和粒子"),
        )
        for alias in (
            "弗兰克-赫兹实验",
            "Franck-Hertz experiment",
            "第一激发电势",
            "汞原子能级",
            "电子与原子非弹性碰撞",
        ):
            self.assertEqual(build_kb.classify(alias), "第12章 波和粒子")

    def test_builder_declares_exact_source_and_route_contract(self) -> None:
        self.assertEqual(build_franck_hertz_import.OUTPUT_STEM, "franck_hertz")
        self.assertEqual(build_franck_hertz_import.CHUNK_SIZE, 760)
        self.assertEqual(build_franck_hertz_import.CHUNK_OVERLAP, 120)
        self.assertEqual(build_franck_hertz_import.ROUTES, EXPECTED_ROUTES)
        self.assertEqual(
            set(build_franck_hertz_import.PDF_FILENAMES), EXPECTED_PDFS
        )
        self.assertEqual(
            {path.name for path in build_franck_hertz_import.PDF_SPECS},
            EXPECTED_PDFS,
        )
        for spec in build_franck_hertz_import.PDF_SPECS.values():
            self.assertEqual(set(spec), {"title", "year", "topic", "pages", "url"})
            self.assertTrue(str(spec["title"]).strip())
            self.assertGreater(int(spec["year"]), 0)
            self.assertIn("弗兰克-赫兹", str(spec["topic"]))
            self.assertRegex(str(spec["url"]), r"^https://")
        codata = next(
            spec
            for path, spec in build_franck_hertz_import.PDF_SPECS.items()
            if path.name == "CODATA_2022_Fundamental_Constants.pdf"
        )
        self.assertEqual(codata["pages"], list(range(44, 52)))
        self.assertEqual(
            set(build_franck_hertz_import.MARKDOWN_TOPICS), EXPECTED_MARKDOWN
        )

    def test_missing_source_error_lists_every_missing_path(self) -> None:
        expected_paths = (
            [
                build_franck_hertz_import.SOURCE_DIR / "弗兰克-赫兹可视化实验方案.md",
                build_franck_hertz_import.SOURCE_DIR / "弗兰克-赫兹文献导读.md",
                build_franck_hertz_import.REF_DIR / "README.md",
            ]
            + list(build_franck_hertz_import.PDF_SPECS)
        )
        if all(path.is_file() for path in expected_paths):
            self.skipTest("文献资料已落盘，缺失资料契约不再适用")
        with self.assertRaisesRegex(FileNotFoundError, "弗兰克-赫兹") as context:
            build_franck_hertz_import.build()
        message = str(context.exception)
        for path in expected_paths:
            if not path.is_file():
                self.assertIn(path.name, message)


class FranckHertzImportArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = (
            MATERIAL_DIR / "弗兰克-赫兹可视化实验方案.md",
            MATERIAL_DIR / "弗兰克-赫兹文献导读.md",
            REFERENCE_DIR / "README.md",
            *(REFERENCE_DIR / name for name in EXPECTED_PDFS),
            IMPORT_PATH,
            IMPORT_MANIFEST_PATH,
            IMPORT_REPORT_PATH,
            MAIN_CHUNKS_PATH,
            MAIN_MANIFEST_PATH,
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise AssertionError("弗兰克-赫兹知识库产物尚未构建：" + ", ".join(missing))
        cls.rows = _read_jsonl(IMPORT_PATH)
        cls.manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.report = json.loads(IMPORT_REPORT_PATH.read_text(encoding="utf-8"))
        cls.main_rows = _read_jsonl(MAIN_CHUNKS_PATH)
        cls.main_manifest = json.loads(MAIN_MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.merged_rows = [
            row
            for row in cls.main_rows
            if str(row.get("id", "")).startswith("imported-franck_hertz-")
        ]

    def test_documents_define_four_routes_and_ten_core_references(self) -> None:
        plan = (MATERIAL_DIR / "弗兰克-赫兹可视化实验方案.md").read_text(
            encoding="utf-8"
        )
        guide = (MATERIAL_DIR / "弗兰克-赫兹文献导读.md").read_text(
            encoding="utf-8"
        )
        references = (REFERENCE_DIR / "README.md").read_text(encoding="utf-8")
        for route in EXPECTED_ROUTES:
            self.assertIn(f"/{route}", plan)
        for term in (
            "960 × 760",
            "非弹性碰撞",
            "第一激发电势",
            "峰谷",
            "接触电势",
            "不确定度",
        ):
            self.assertIn(term, plan + guide)
        headings = re.findall(r"(?m)^###\s+2\.(\d+)\s+", references)
        self.assertEqual(headings, [str(index) for index in range(1, 11)])
        self.assertLess(
            references.index("Franck-Hertz 1914：汞蒸气中的特征能量损失"),
            references.index("Franck 1926：Nobel lecture"),
        )

    def test_import_rows_and_manifest_follow_portable_contract(self) -> None:
        self.assertEqual(len(self.rows), self.manifest["chunks"])
        self.assertGreaterEqual(len(self.rows), 100)
        self.assertEqual(len({row["id"] for row in self.rows}), len(self.rows))
        self.assertTrue(all(REQUIRED_FIELDS <= row.keys() for row in self.rows))
        self.assertTrue(all(str(row["text"]).strip() for row in self.rows))
        self.assertEqual(self.manifest["topic"], "弗兰克-赫兹实验")
        self.assertEqual(self.manifest["routes"], EXPECTED_ROUTES)
        self.assertEqual(self.manifest["documents"], 9)
        self.assertEqual(self.manifest["markdown_documents"], 3)
        self.assertEqual(self.manifest["pdf_documents"], 6)
        self.assertEqual(
            {row["source"] for row in self.rows},
            EXPECTED_MARKDOWN | EXPECTED_PDFS,
        )

    def test_every_pdf_has_a_valid_text_layer_and_scoped_codata_pages(self) -> None:
        pdf_reports = [row for row in self.report if row["source_type"] == "pdf"]
        self.assertEqual(len(pdf_reports), 6)
        self.assertEqual(
            pdf_reports[0]["source"], "Franck_Hertz_1914_Mercury_Collisions.pdf"
        )
        for report in pdf_reports:
            self.assertEqual(report["pdf_signature"], "%PDF-")
            self.assertGreater(report["bytes"], 0)
            self.assertGreater(report["text_layer_pages"], 0)
            self.assertGreater(report["chunks"], 0)
            self.assertFalse(report["ocr_recommended"])
        codata = next(
            report
            for report in pdf_reports
            if report["source"] == "CODATA_2022_Fundamental_Constants.pdf"
        )
        self.assertEqual(codata["selected_pages"], list(range(44, 52)))

    def test_main_kb_contains_the_complete_collection_in_modern_physics(self) -> None:
        self.assertEqual(len(self.merged_rows), len(self.rows))
        self.assertTrue(
            all(row["chapter"] == "第12章 波和粒子" for row in self.merged_rows)
        )
        imported = {
            row["file"]: row
            for row in self.main_manifest["imported_knowledge_bases"]
        }
        entry = imported["franck_hertz.jsonl"]
        self.assertEqual(entry["collection"], "弗兰克-赫兹实验")
        self.assertEqual(entry["chunks"], len(self.rows))
        self.assertEqual(entry["duplicates_skipped"], 0)
        self.assertEqual(entry["invalid_skipped"], 0)

    def test_bm25_retrieval_finds_franck_hertz_evidence(self) -> None:
        kb = KnowledgeBase(MAIN_CHUNKS_PATH)
        results = kb.search("弗兰克-赫兹实验怎样由峰间距求第一激发电势", top_k=8)
        self.assertTrue(results)
        self.assertTrue(
            any(chunk.id.startswith("imported-franck_hertz-") for chunk, _ in results)
        )


if __name__ == "__main__":
    unittest.main()
