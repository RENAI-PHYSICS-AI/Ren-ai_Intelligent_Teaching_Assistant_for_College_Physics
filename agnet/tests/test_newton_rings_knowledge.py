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
from rag import KnowledgeBase


KB_DIR = APP_DIR / "knowledge_base"
IMPORT_DIR = KB_DIR / "imports"
IMPORT_PATH = IMPORT_DIR / "newton_rings.jsonl"
IMPORT_MANIFEST_PATH = IMPORT_DIR / "newton_rings.manifest.json"
IMPORT_REPORT_PATH = IMPORT_DIR / "newton_rings.extraction_report.json"
MAIN_CHUNKS_PATH = KB_DIR / "chunks.jsonl"
MAIN_MANIFEST_PATH = KB_DIR / "manifest.json"


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AssertionError(
                    f"{path.name}:{line_number} is not valid JSON: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise AssertionError(
                    f"{path.name}:{line_number} must contain a JSON object"
                )
            rows.append(row)
    return rows


class NewtonRingsKnowledgeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = (
            IMPORT_PATH,
            IMPORT_MANIFEST_PATH,
            IMPORT_REPORT_PATH,
            MAIN_CHUNKS_PATH,
            MAIN_MANIFEST_PATH,
        )
        missing = [str(path.relative_to(APP_DIR)) for path in required if not path.is_file()]
        if missing:
            raise AssertionError("牛顿环知识库产物尚未构建：" + ", ".join(missing))

        cls.import_rows = _read_jsonl(IMPORT_PATH)
        cls.main_rows = _read_jsonl(MAIN_CHUNKS_PATH)
        cls.import_manifest = json.loads(
            IMPORT_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        cls.extraction_report = json.loads(
            IMPORT_REPORT_PATH.read_text(encoding="utf-8")
        )
        cls.main_manifest = json.loads(MAIN_MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.merged_newton_rows = [
            row
            for row in cls.main_rows
            if str(row.get("id", "")).startswith("imported-newton_rings-")
        ]

    def test_build_mapping_targets_wave_optics(self):
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("newton_rings"),
            ("牛顿环等厚干涉实验", "第11章 波动光学"),
        )

    def test_portable_import_schema_and_course_physics(self):
        self.assertGreater(len(self.import_rows), 0)
        required_fields = {
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
        ids: list[str] = []
        for index, row in enumerate(self.import_rows, 1):
            self.assertTrue(
                required_fields.issubset(row),
                f"newton_rings.jsonl 第 {index} 条缺少字段："
                f"{sorted(required_fields - set(row))}",
            )
            identifier = str(row["id"]).strip()
            self.assertTrue(identifier, f"newton_rings.jsonl 第 {index} 条 id 为空")
            ids.append(identifier)
            for field in ("source", "text", "title", "topic", "locator"):
                self.assertTrue(
                    str(row[field]).strip(),
                    f"newton_rings.jsonl 第 {index} 条 {field} 为空",
                )
            self.assertIn(row["source_type"], {"markdown", "pdf"})
            self.assertIsInstance(row["page"], int)
            self.assertIsInstance(row["chunk"], int)

        self.assertEqual(len(ids), len(set(ids)), "newton_rings.jsonl 存在重复 id")

        corpus = "\n".join(str(row["text"]) for row in self.import_rows)
        for expected in ("牛顿环", "钠黄光", "589.3", "曲率半径", "逐差", "m-n=15"):
            self.assertIn(expected, corpus)
        for order in (5, 10, 15, 20, 25, 30):
            self.assertRegex(corpus, rf"(?<!\d){order}(?!\d)")

        formula_corpus = re.sub(r"\s+", "", corpus)
        self.assertIn(r"D_m^2=\frac{4m\lambdaR}{\mu}", formula_corpus)
        self.assertIn(
            r"\frac{\mu\left(D_{m+p}^2-D_m^2\right)}{4p\lambda}",
            formula_corpus,
        )
        self.assertIn(r"2\mut=m\lambda", formula_corpus)

    def test_import_manifest_and_extraction_report_match_jsonl(self):
        manifest = self.import_manifest
        self.assertEqual(manifest.get("chunks"), len(self.import_rows))
        self.assertEqual(manifest.get("chunk_size"), 760)
        self.assertEqual(manifest.get("chunk_overlap"), 120)
        self.assertGreater(manifest.get("documents", 0), 0)
        self.assertEqual(
            manifest.get("markdown_documents", 0) + manifest.get("pdf_documents", 0),
            manifest.get("documents"),
        )
        self.assertEqual(manifest.get("known_wavelength_nm"), 589.3)
        self.assertEqual(manifest.get("measured_quantity"), "平凸透镜曲率半径 R")
        self.assertEqual(manifest.get("dark_ring_orders"), [5, 10, 15, 20, 25, 30])
        self.assertEqual(manifest.get("successive_difference"), 15)

        sources = manifest.get("sources", [])
        self.assertEqual(len(sources), manifest.get("documents"))
        self.assertEqual(sum(int(source.get("chunks", 0)) for source in sources), len(self.import_rows))
        self.assertIsInstance(self.extraction_report, list)
        self.assertEqual(len(self.extraction_report), len(sources))
        for report in self.extraction_report:
            self.assertTrue(str(report.get("source", "")).strip())
            self.assertIn(report.get("source_type"), {"markdown", "pdf"})
            self.assertIsInstance(report.get("chunks"), int)
            if report.get("source_type") == "pdf":
                self.assertIsInstance(report.get("pages"), int)
                self.assertIsInstance(report.get("empty_pages"), list)
                self.assertIsInstance(report.get("ocr_recommended"), bool)

    def test_main_manifest_and_merged_chunk_counts_are_consistent(self):
        imported = {
            entry.get("file"): entry
            for entry in self.main_manifest.get("imported_knowledge_bases", [])
        }
        self.assertIn(
            "newton_rings.jsonl",
            imported,
            "牛顿环专题已构建但尚未合并到主知识库",
        )
        newton_entry = imported["newton_rings.jsonl"]
        added = int(newton_entry.get("chunks", -1))
        duplicates = int(newton_entry.get("duplicates_skipped", -1))
        invalid = int(newton_entry.get("invalid_skipped", -1))

        self.assertEqual(invalid, 0)
        self.assertGreater(added, 0)
        self.assertEqual(added + duplicates + invalid, len(self.import_rows))
        self.assertEqual(len(self.merged_newton_rows), added)
        by_type = self.main_manifest.get("by_type", {})
        self.assertEqual(by_type.get("imported_newton_rings_chunks"), added)
        self.assertEqual(by_type.get("imported_newton_rings_duplicates"), duplicates)
        self.assertEqual(by_type.get("imported_newton_rings_invalid"), invalid)
        self.assertEqual(self.main_manifest.get("chunks"), len(self.main_rows))
        self.assertEqual(
            self.main_manifest.get("chunks"),
            self.main_manifest.get("base_chunks")
            + sum(
                int(entry.get("chunks", 0))
                for entry in self.main_manifest.get("imported_knowledge_bases", [])
            ),
        )
        failures = self.main_manifest.get("import_failures", [])
        self.assertFalse(
            [
                failure
                for failure in failures
                if "newton_rings" in str(failure.get("file", "")).lower()
            ]
        )

    def test_merged_rows_keep_collection_metadata_and_priority(self):
        self.assertGreater(len(self.merged_newton_rows), 0)
        for row in self.merged_newton_rows:
            self.assertEqual(row.get("chapter"), "第11章 波动光学")
            self.assertAlmostEqual(float(row.get("priority")), 0.9)
            self.assertTrue(
                str(row.get("source_type", "")).startswith(
                    "竞赛知识库·牛顿环等厚干涉实验"
                )
            )
            self.assertTrue(
                str(row.get("relative_path", "")).startswith(
                    "已整合知识库/牛顿环等厚干涉实验/"
                )
            )
            self.assertTrue(str(row.get("locator", "")).strip())

    def test_bm25_retrieval_finds_sodium_newton_ring_radius_measurement(self):
        knowledge_base = KnowledgeBase(MAIN_CHUNKS_PATH)
        results = knowledge_base.search(
            "牛顿环 钠黄光 589.3 暗环直径 15级逐差 曲率半径",
            chapter="第11章 波动光学",
            top_k=10,
        )
        self.assertTrue(results)
        self.assertTrue(
            any(
                chunk.id.startswith("imported-newton_rings-")
                for chunk, _ in results
            ),
            "BM25 前 10 条没有命中牛顿环专题知识",
        )


if __name__ == "__main__":
    unittest.main()
