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
IMPORT_PATH = IMPORT_DIR / "biprism.jsonl"
IMPORT_MANIFEST_PATH = IMPORT_DIR / "biprism.manifest.json"
IMPORT_REPORT_PATH = IMPORT_DIR / "biprism.extraction_report.json"
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


class BiprismKnowledgeIntegrationTests(unittest.TestCase):
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
            raise AssertionError(
                "双棱镜知识库产物尚未构建：" + ", ".join(missing)
            )

        cls.import_rows = _read_jsonl(IMPORT_PATH)
        cls.main_rows = _read_jsonl(MAIN_CHUNKS_PATH)
        cls.import_manifest = json.loads(
            IMPORT_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        cls.extraction_report = json.loads(
            IMPORT_REPORT_PATH.read_text(encoding="utf-8")
        )
        cls.main_manifest = json.loads(
            MAIN_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        cls.merged_biprism_rows = [
            row
            for row in cls.main_rows
            if str(row.get("id", "")).startswith("imported-biprism-")
        ]

    def test_build_mapping_targets_wave_optics(self):
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("biprism"),
            ("双棱镜干涉测波长实验", "第11章 波动光学"),
        )

    def test_portable_import_schema_ids_and_core_sodium_content(self):
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
                f"biprism.jsonl 第 {index} 条缺少字段："
                f"{sorted(required_fields - set(row))}",
            )
            identifier = str(row["id"]).strip()
            self.assertTrue(identifier, f"biprism.jsonl 第 {index} 条 id 为空")
            ids.append(identifier)
            for field in ("source", "text", "title", "topic", "locator"):
                self.assertTrue(
                    str(row[field]).strip(),
                    f"biprism.jsonl 第 {index} 条 {field} 为空",
                )
            self.assertIn(row["source_type"], {"markdown", "pdf"})
            self.assertIsInstance(row["page"], int)
            self.assertIsInstance(row["chunk"], int)

        self.assertEqual(len(ids), len(set(ids)), "biprism.jsonl 存在重复 id")

        corpus = "\n".join(str(row["text"]) for row in self.import_rows)
        for expected in ("双棱镜", "钠黄光", "589.3", "二次成像"):
            self.assertIn(expected, corpus)
        formula_corpus = re.sub(r"\s+", "", corpus)
        self.assertTrue(
            "λ=βd/D" in formula_corpus
            or "\\lambda=\\frac{\\betad}{D}" in formula_corpus,
            "专题知识必须包含 λ=βd/D 波长公式",
        )
        self.assertTrue(
            "d=√(d₁d₂)" in formula_corpus
            or "d=\\sqrt{d_1d_2}" in formula_corpus
            or "d=\\sqrt{s_{\\mathrm{big}}s_{\\mathrm{small}}}" in formula_corpus,
            "专题知识必须包含 d=√(d₁d₂) 二次成像公式",
        )

    def test_import_manifest_and_extraction_report_match_jsonl(self):
        self.assertEqual(self.import_manifest.get("chunks"), len(self.import_rows))
        self.assertEqual(self.import_manifest.get("chunk_size"), 760)
        self.assertEqual(self.import_manifest.get("chunk_overlap"), 120)
        self.assertGreater(self.import_manifest.get("documents", 0), 0)
        self.assertGreaterEqual(
            self.import_manifest.get("documents", 0),
            self.import_manifest.get("pdf_documents", 0),
        )
        self.assertIsInstance(
            self.import_manifest.get("ocr_recommended_documents"), list
        )
        self.assertIsInstance(self.extraction_report, list)
        for report in self.extraction_report:
            self.assertTrue(str(report.get("source", "")).strip())
            self.assertIsInstance(report.get("pages"), int)
            self.assertIsInstance(report.get("chunks"), int)
            self.assertIsInstance(report.get("empty_pages"), list)
            self.assertIsInstance(report.get("ocr_recommended"), bool)

    def test_main_manifest_and_merged_chunk_counts_are_consistent(self):
        imported = {
            entry.get("file"): entry
            for entry in self.main_manifest.get("imported_knowledge_bases", [])
        }
        self.assertIn("biprism.jsonl", imported)
        biprism_entry = imported["biprism.jsonl"]
        added = int(biprism_entry.get("chunks", -1))
        duplicates = int(biprism_entry.get("duplicates_skipped", -1))
        invalid = int(biprism_entry.get("invalid_skipped", -1))

        self.assertEqual(invalid, 0)
        self.assertGreater(added, 0)
        self.assertEqual(added + duplicates + invalid, len(self.import_rows))
        self.assertEqual(len(self.merged_biprism_rows), added)
        self.assertEqual(
            self.main_manifest.get("by_type", {}).get("imported_biprism_chunks"),
            added,
        )
        self.assertEqual(
            self.main_manifest.get("by_type", {}).get("imported_biprism_duplicates"),
            duplicates,
        )
        self.assertEqual(
            self.main_manifest.get("by_type", {}).get("imported_biprism_invalid"),
            invalid,
        )
        self.assertEqual(self.main_manifest.get("chunks"), len(self.main_rows))
        self.assertEqual(
            self.main_manifest.get("chunks"),
            self.main_manifest.get("base_chunks")
            + sum(
                int(entry.get("chunks", 0))
                for entry in self.main_manifest.get(
                    "imported_knowledge_bases", []
                )
            ),
        )
        failures = self.main_manifest.get("import_failures", [])
        self.assertFalse(
            [
                failure
                for failure in failures
                if "biprism" in str(failure.get("file", "")).lower()
            ]
        )

    def test_merged_rows_keep_collection_metadata_and_priority(self):
        self.assertGreater(len(self.merged_biprism_rows), 0)
        for row in self.merged_biprism_rows:
            self.assertEqual(row.get("chapter"), "第11章 波动光学")
            self.assertAlmostEqual(float(row.get("priority")), 0.9)
            self.assertTrue(
                str(row.get("source_type", "")).startswith(
                    "竞赛知识库·双棱镜干涉测波长实验"
                )
            )
            self.assertTrue(
                str(row.get("relative_path", "")).startswith(
                    "已整合知识库/双棱镜干涉测波长实验/"
                )
            )
            self.assertTrue(str(row.get("locator", "")).strip())

    def test_bm25_retrieval_finds_biprism_sodium_measurement(self):
        knowledge_base = KnowledgeBase(MAIN_CHUNKS_PATH)
        results = knowledge_base.search(
            "双棱镜 钠黄光 二次成像 虚光源间距 条纹间距 波长",
            chapter="第11章 波动光学",
            top_k=10,
        )
        self.assertTrue(results)
        self.assertTrue(
            any(chunk.id.startswith("imported-biprism-") for chunk, _ in results),
            "BM25 前 10 条没有命中双棱镜专题知识",
        )


if __name__ == "__main__":
    unittest.main()
