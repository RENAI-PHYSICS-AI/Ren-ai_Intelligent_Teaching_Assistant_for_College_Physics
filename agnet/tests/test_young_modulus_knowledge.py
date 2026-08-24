from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path, PurePosixPath


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_kb
from rag import KnowledgeBase


KB_DIR = APP_DIR / "knowledge_base"
IMPORT_DIR = KB_DIR / "imports"
IMPORT_PATH = IMPORT_DIR / "young_modulus.jsonl"
IMPORT_MANIFEST_PATH = IMPORT_DIR / "young_modulus.manifest.json"
IMPORT_REPORT_PATH = IMPORT_DIR / "young_modulus.extraction_report.json"
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


class YoungModulusKnowledgeIntegrationTests(unittest.TestCase):
    """Expected literature/import contract for the Young-modulus topic."""

    @classmethod
    def setUpClass(cls) -> None:
        required = (
            IMPORT_PATH,
            IMPORT_MANIFEST_PATH,
            IMPORT_REPORT_PATH,
            MAIN_CHUNKS_PATH,
            MAIN_MANIFEST_PATH,
        )
        missing = [
            str(path.relative_to(APP_DIR)) for path in required if not path.is_file()
        ]
        if missing:
            raise AssertionError(
                "杨氏模量知识库产物尚未构建：" + ", ".join(missing)
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
        cls.merged_rows = [
            row
            for row in cls.main_rows
            if str(row.get("id", "")).startswith("imported-young_modulus-")
        ]

    def test_build_mapping_uses_the_existing_mechanics_chapter(self):
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("young_modulus"),
            ("杨氏模量测定实验", "第2章 牛顿运动定律"),
        )

    def test_portable_import_schema_ids_and_core_course_content(self):
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
        identifiers: list[str] = []
        for index, row in enumerate(self.import_rows, 1):
            self.assertTrue(
                required_fields.issubset(row),
                f"young_modulus.jsonl 第 {index} 条缺少字段："
                f"{sorted(required_fields - set(row))}",
            )
            identifier = str(row["id"]).strip()
            self.assertTrue(identifier, f"第 {index} 条 id 为空")
            identifiers.append(identifier)
            for field in ("source", "text", "title", "topic", "locator"):
                self.assertTrue(
                    str(row[field]).strip(),
                    f"young_modulus.jsonl 第 {index} 条 {field} 为空",
                )
            self.assertIn(row["source_type"], {"markdown", "pdf"})
            self.assertTrue(row["page"] is None or isinstance(row["page"], int))
            self.assertIsInstance(row["chunk"], int)

        self.assertEqual(
            len(identifiers),
            len(set(identifiers)),
            "young_modulus.jsonl 存在重复 id",
        )

        corpus = "\n".join(str(row["text"]) for row in self.import_rows)
        for expected in (
            "杨氏模量",
            "金属丝",
            "光杠杆",
            "胡克定律",
            "加载",
            "卸载",
            "线性拟合",
            "不确定度",
        ):
            self.assertIn(expected, corpus)

        compact = re.sub(r"[\s$]", "", corpus)
        extension_formulae = (
            "ΔL=bΔx/(2D)",
            "ΔL=bΔs/(2D)",
            r"\DeltaL=\frac{b\Deltax}{2D}",
            r"\DeltaL=\frac{b\Deltas}{2D}",
            r"\DeltaL=\frac{b\Delta x}{2D}",
            r"\DeltaL=\frac{b\Delta s}{2D}",
        )
        modulus_formulae = (
            "E=FL/(AΔL)",
            "E=4FL/(πd²ΔL)",
            "E=8FLD/(πd²bΔx)",
            "E=8MgLD/(πd²bΔs)",
            r"E=\frac{FL}{A\DeltaL}",
            r"E=\frac{4FL}{\pid^2\DeltaL}",
            r"E=\frac{8FLD}{\pid^2b\Deltax}",
            r"E=\frac{8MgLD}{\pid^2b\Deltas}",
        )
        self.assertTrue(
            any(formula in compact for formula in extension_formulae),
            "专题知识必须包含光杠杆换算式 ΔL=bΔs/(2D)",
        )
        self.assertTrue(
            any(formula in compact for formula in modulus_formulae),
            "专题知识必须包含拉伸法杨氏模量公式",
        )

    def test_manifest_has_course_metadata_and_about_ten_traceable_sources(self):
        manifest = self.import_manifest
        self.assertEqual(manifest.get("chunks"), len(self.import_rows))
        self.assertEqual(manifest.get("chunk_size"), 760)
        self.assertEqual(manifest.get("chunk_overlap"), 120)
        self.assertEqual(manifest.get("method"), "静态拉伸法（光杠杆）")
        self.assertEqual(manifest.get("measured_quantity"), "金属丝杨氏模量 E")
        self.assertEqual(
            manifest.get("routes"),
            ["principle", "loading", "fit", "uncertainty"],
        )
        self.assertGreaterEqual(
            int(manifest.get("documents", 0)),
            8,
            "杨氏模量专题应整理约 10 篇可追溯文献/实验资料",
        )
        self.assertLessEqual(
            int(manifest.get("documents", 0)),
            12,
            "专题导入清单应保持在约 10 篇核心资料，避免无边界扩张",
        )
        self.assertGreater(int(manifest.get("pdf_documents", 0)), 0)

        sources = manifest.get("sources", [])
        self.assertEqual(len(sources), manifest.get("documents"))
        self.assertEqual(
            sum(int(source.get("chunks", 0)) for source in sources),
            len(self.import_rows),
        )
        self.assertTrue(any(source.get("source_type") == "markdown" for source in sources))
        self.assertTrue(any(source.get("source_type") == "pdf" for source in sources))
        drive_path = re.compile(r"^[A-Za-z]:[\\/]")
        for source in sources:
            source_path = str(source.get("source_path", "")).strip()
            self.assertTrue(source_path)
            self.assertFalse(drive_path.match(source_path))
            self.assertFalse(source_path.startswith(("/", "\\", "file:")))
            self.assertNotIn("..", PurePosixPath(source_path.replace("\\", "/")).parts)
            if source.get("source_type") == "pdf":
                self.assertGreater(int(source.get("pages", 0)), 0)
                self.assertRegex(str(source.get("sha256", "")), r"^[0-9a-f]{64}$")

    def test_extraction_report_matches_the_manifest_and_flags_ocr_explicitly(self):
        self.assertIsInstance(self.extraction_report, list)
        self.assertEqual(
            len(self.extraction_report), self.import_manifest.get("documents")
        )
        report_sources = set()
        for report in self.extraction_report:
            source = str(report.get("source", "")).strip()
            self.assertTrue(source)
            report_sources.add(source)
            self.assertIn(report.get("source_type"), {"markdown", "pdf"})
            self.assertIsInstance(report.get("chunks"), int)
            if report.get("source_type") == "pdf":
                self.assertIsInstance(report.get("pages"), int)
                self.assertIsInstance(report.get("empty_pages"), list)
                self.assertIsInstance(report.get("ocr_recommended"), bool)

        manifest_sources = {
            str(source.get("source", "")).strip()
            for source in self.import_manifest.get("sources", [])
        }
        self.assertEqual(report_sources, manifest_sources)

    def test_main_manifest_and_merged_chunk_counts_are_consistent(self):
        imported = {
            entry.get("file"): entry
            for entry in self.main_manifest.get("imported_knowledge_bases", [])
        }
        self.assertIn(
            "young_modulus.jsonl",
            imported,
            "杨氏模量专题已构建但尚未合并到主知识库",
        )
        entry = imported["young_modulus.jsonl"]
        added = int(entry.get("chunks", -1))
        duplicates = int(entry.get("duplicates_skipped", -1))
        invalid = int(entry.get("invalid_skipped", -1))

        self.assertEqual(invalid, 0)
        self.assertGreater(added, 0)
        self.assertEqual(added + duplicates + invalid, len(self.import_rows))
        self.assertEqual(len(self.merged_rows), added)

        by_type = self.main_manifest.get("by_type", {})
        self.assertEqual(by_type.get("imported_young_modulus_chunks"), added)
        self.assertEqual(by_type.get("imported_young_modulus_duplicates"), duplicates)
        self.assertEqual(by_type.get("imported_young_modulus_invalid"), invalid)
        self.assertEqual(self.main_manifest.get("chunks"), len(self.main_rows))
        self.assertEqual(
            self.main_manifest.get("chunks"),
            self.main_manifest.get("base_chunks")
            + sum(
                int(item.get("chunks", 0))
                for item in self.main_manifest.get("imported_knowledge_bases", [])
            ),
        )
        self.assertFalse(
            [
                failure
                for failure in self.main_manifest.get("import_failures", [])
                if "young_modulus" in str(failure.get("file", "")).lower()
            ]
        )

    def test_merged_rows_keep_authoritative_collection_metadata(self):
        self.assertGreater(len(self.merged_rows), 0)
        for row in self.merged_rows:
            self.assertEqual(row.get("chapter"), "第2章 牛顿运动定律")
            self.assertAlmostEqual(float(row.get("priority")), 0.9)
            self.assertTrue(
                str(row.get("source_type", "")).startswith(
                    "竞赛知识库·杨氏模量测定实验"
                )
            )
            self.assertTrue(
                str(row.get("relative_path", "")).startswith(
                    "已整合知识库/杨氏模量测定实验/"
                )
            )
            self.assertTrue(str(row.get("locator", "")).strip())

    def test_bm25_retrieval_finds_optical_lever_modulus_measurement(self):
        knowledge_base = KnowledgeBase(MAIN_CHUNKS_PATH)
        results = knowledge_base.search(
            "杨氏模量 金属丝 拉伸 光杠杆 加载 卸载 线性拟合 不确定度",
            chapter="第2章 牛顿运动定律",
            top_k=10,
        )
        self.assertTrue(results)
        self.assertTrue(
            any(
                chunk.id.startswith("imported-young_modulus-")
                for chunk, _ in results
            ),
            "BM25 前 10 条没有命中杨氏模量专题知识",
        )


if __name__ == "__main__":
    unittest.main()
