from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

from pypdf import PdfReader


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_kb
import build_viscosity_import
from rag import KnowledgeBase


VARIANT_ROOT = APP_DIR.parent
MATERIAL_DIR = VARIANT_ROOT / "教学素材" / "物理实验" / "粘滞系数测定"
REFERENCE_DIR = MATERIAL_DIR / "ref"
KB_DIR = APP_DIR / "knowledge_base"
IMPORT_DIR = KB_DIR / "imports"
IMPORT_PATH = IMPORT_DIR / "viscosity.jsonl"
IMPORT_MANIFEST_PATH = IMPORT_DIR / "viscosity.manifest.json"
IMPORT_REPORT_PATH = IMPORT_DIR / "viscosity.extraction_report.json"
MAIN_CHUNKS_PATH = KB_DIR / "chunks.jsonl"
MAIN_MANIFEST_PATH = KB_DIR / "manifest.json"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"

EXPECTED_MARKDOWN = {
    "粘滞系数可视化实验方案.md",
    "粘滞系数文献导读.md",
    "README.md",
}
EXPECTED_PDFS = {
    "Stokes_1845_Internal_Friction.pdf",
    "Stokes_1851_Pendulums_Internal_Friction.pdf",
    "Haberman_Sayre_1958_Cylindrical_Tubes.pdf",
    "Brizard_et_al_2005_High_Precision_Falling_Ball.pdf",
    "JCGM_100_2008_GUM.pdf",
    "NIST_TN1297_Uncertainty.pdf",
}
EXPECTED_ROUTES = ["stokes", "terminal", "correction", "fit"]
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
                raise AssertionError(f"{path.name}:{line_number} must contain an object")
            rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _manifest_without_timestamp(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("created_at", None)
    return payload


class ViscosityRegistrationTests(unittest.TestCase):
    """Static contract which can run before literature and KB artifacts exist."""

    def test_collection_uses_authoritative_mechanics_chapter(self):
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("viscosity"),
            ("粘滞系数测定实验", "第2章 力、动量、能量"),
        )
        for alias in ("粘滞", "黏滞", "粘度", "黏度", "斯托克斯", "Stokes", "雷诺数"):
            self.assertEqual(build_kb.classify(alias), "第2章 力、动量、能量")

    def test_builder_declares_exact_source_and_route_contract(self):
        self.assertEqual(build_viscosity_import.OUTPUT_STEM, "viscosity")
        self.assertEqual(build_viscosity_import.CHUNK_SIZE, 760)
        self.assertEqual(build_viscosity_import.CHUNK_OVERLAP, 120)
        self.assertEqual(
            {path.name for path in build_viscosity_import.PDF_SPECS},
            EXPECTED_PDFS,
        )
        for spec in build_viscosity_import.PDF_SPECS.values():
            self.assertEqual(set(spec), {"title", "year", "topic", "pages", "url"})
            self.assertTrue(str(spec["title"]).strip())
            self.assertGreater(int(spec["year"]), 0)
            self.assertIn("粘滞系数", str(spec["topic"]))
            self.assertRegex(str(spec["url"]), r"^https://")
        brizard = next(
            spec
            for path, spec in build_viscosity_import.PDF_SPECS.items()
            if path.name == "Brizard_et_al_2005_High_Precision_Falling_Ball.pdf"
        )
        self.assertEqual(brizard["url"], "https://hal.science/hal-00197586/document")
        self.assertEqual(
            build_viscosity_import.MARKDOWN_TOPICS.keys(),
            {
                "粘滞系数可视化实验方案.md",
                "粘滞系数文献导读.md",
                "README.md",
            },
        )
        self.assertEqual(build_viscosity_import.ROUTES, EXPECTED_ROUTES)


class ViscosityKnowledgeIntegrationTests(unittest.TestCase):
    """Regression contract for the falling-ball literature and merged KB."""

    @classmethod
    def setUpClass(cls) -> None:
        required = (
            MATERIAL_DIR / "粘滞系数可视化实验方案.md",
            MATERIAL_DIR / "粘滞系数文献导读.md",
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
            raise AssertionError("粘滞系数知识库产物尚未构建：" + ", ".join(missing))

        cls.import_rows = _read_jsonl(IMPORT_PATH)
        cls.import_manifest = json.loads(
            IMPORT_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        cls.extraction_report = json.loads(
            IMPORT_REPORT_PATH.read_text(encoding="utf-8")
        )
        cls.main_rows = _read_jsonl(MAIN_CHUNKS_PATH)
        cls.main_manifest = json.loads(MAIN_MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.merged_rows = [
            row
            for row in cls.main_rows
            if str(row.get("id", "")).startswith("imported-viscosity-")
        ]

    def test_documents_define_four_experiments_and_ten_core_references(self):
        plan = (MATERIAL_DIR / "粘滞系数可视化实验方案.md").read_text(
            encoding="utf-8"
        )
        guide = (MATERIAL_DIR / "粘滞系数文献导读.md").read_text(
            encoding="utf-8"
        )
        references = (REFERENCE_DIR / "README.md").read_text(encoding="utf-8")

        for route in EXPECTED_ROUTES:
            self.assertIn(f"/{route}", plan)
        for term in (
            "960 × 760",
            "指针",
            "斯托克斯",
            "终端速度",
            "雷诺数",
            "壁面",
            "不确定度",
        ):
            self.assertIn(term, plan)
        for term in (
            "动力黏度",
            "运动黏度",
            "终端速度",
            "雷诺数",
            "温度",
            "A 类",
            "B 类",
        ):
            self.assertIn(term, guide)

        core_numbers = re.findall(r"^### 2\.(\d+)\s", references, flags=re.MULTILINE)
        self.assertEqual(core_numbers, [str(index) for index in range(1, 11)])
        self.assertGreaterEqual(len(set(re.findall(r"https?://[^\s）]+", references))), 10)
        for pdf_name in EXPECTED_PDFS:
            self.assertIn(pdf_name, references)

    def test_six_local_pdfs_are_real_and_readable(self):
        actual_pdfs = {path.name for path in REFERENCE_DIR.glob("*.pdf")}
        self.assertEqual(actual_pdfs, EXPECTED_PDFS)
        for name in EXPECTED_PDFS:
            path = REFERENCE_DIR / name
            with path.open("rb") as handle:
                self.assertEqual(handle.read(5), b"%PDF-")
            self.assertGreater(len(PdfReader(str(path)).pages), 0)

    def test_portable_import_schema_ids_and_core_physics(self):
        self.assertGreaterEqual(len(self.import_rows), 40)
        identifiers: list[str] = []
        for index, row in enumerate(self.import_rows, 1):
            self.assertEqual(
                set(row),
                REQUIRED_FIELDS,
                f"viscosity.jsonl 第 {index} 条字段不符合契约",
            )
            identifier = str(row["id"])
            self.assertRegex(identifier, r"^[0-9a-f]{16}$")
            identifiers.append(identifier)
            self.assertIn(row["source_type"], {"markdown", "pdf"})
            self.assertTrue(str(row["source"]).strip())
            self.assertTrue(str(row["title"]).strip())
            self.assertTrue(str(row["topic"]).strip())
            self.assertTrue(str(row["locator"]).strip())
            self.assertGreaterEqual(len(re.sub(r"\s+", "", str(row["text"]))), 35)
            if row["source_type"] == "pdf":
                self.assertNotIn("<!doctype html", str(row["text"]).lower())
        self.assertEqual(len(identifiers), len(set(identifiers)))

        corpus = "\n".join(str(row["text"]) for row in self.import_rows)
        for term in (
            "Stokes",
            "斯托克斯",
            "终端速度",
            "雷诺数",
            "动力黏度",
            "运动黏度",
            "壁面修正",
            "温度",
            "不确定度",
        ):
            self.assertIn(term, corpus)

    def test_manifest_and_extraction_report_match_import(self):
        manifest = self.import_manifest
        self.assertEqual(manifest.get("topic"), "粘滞系数测定")
        self.assertIn("落球法", str(manifest.get("method")))
        self.assertIn("Stokes", str(manifest.get("method")))
        self.assertEqual(manifest.get("measured_quantity"), "液体动力黏度 η")
        self.assertEqual(manifest.get("routes"), EXPECTED_ROUTES)
        self.assertEqual(manifest.get("documents"), 9)
        self.assertEqual(manifest.get("markdown_documents"), 3)
        self.assertEqual(manifest.get("pdf_documents"), 6)
        self.assertEqual(manifest.get("chunks"), len(self.import_rows))
        self.assertEqual(manifest.get("chunk_size"), 760)
        self.assertEqual(manifest.get("chunk_overlap"), 120)
        self.assertEqual(
            manifest.get("output"), "agnet/knowledge_base/imports/viscosity.jsonl"
        )
        self.assertIs(manifest.get("main_knowledge_base_modified"), False)

        sources = manifest.get("sources", [])
        self.assertEqual(sources, self.extraction_report)
        self.assertEqual(len(sources), 9)
        self.assertEqual(
            {str(source.get("source")) for source in sources},
            EXPECTED_MARKDOWN | EXPECTED_PDFS,
        )
        counts: dict[str, int] = {}
        for row in self.import_rows:
            counts[str(row["source"])] = counts.get(str(row["source"]), 0) + 1
        for source in sources:
            name = str(source["source"])
            self.assertEqual(source.get("chunks"), counts.get(name, 0))
            if source.get("source_type") == "pdf":
                path = REFERENCE_DIR / name
                self.assertEqual(source.get("bytes"), path.stat().st_size)
                self.assertEqual(source.get("sha256"), _sha256(path))
                self.assertEqual(source.get("pdf_signature"), "%PDF-")
                self.assertGreater(int(source.get("pages", 0)), 0)
                self.assertIsInstance(source.get("empty_pages"), list)
                self.assertIsInstance(source.get("ocr_recommended"), bool)

    def test_main_kb_contains_collection_in_mechanics_chapter(self):
        imported = {
            entry.get("file"): entry
            for entry in self.main_manifest.get("imported_knowledge_bases", [])
        }
        self.assertIn("viscosity.jsonl", imported)
        entry = imported["viscosity.jsonl"]
        added = int(entry.get("chunks", -1))
        duplicates = int(entry.get("duplicates_skipped", -1))
        invalid = int(entry.get("invalid_skipped", -1))
        self.assertGreater(added, 0)
        self.assertEqual(invalid, 0)
        self.assertEqual(added + duplicates + invalid, len(self.import_rows))
        self.assertEqual(len(self.merged_rows), added)
        by_type = self.main_manifest.get("by_type", {})
        self.assertEqual(by_type.get("imported_viscosity_chunks"), added)
        self.assertEqual(by_type.get("imported_viscosity_duplicates"), duplicates)
        self.assertEqual(by_type.get("imported_viscosity_invalid"), invalid)
        self.assertEqual(self.main_manifest.get("chunks"), len(self.main_rows))
        self.assertFalse(
            [
                failure
                for failure in self.main_manifest.get("import_failures", [])
                if "viscosity" in str(failure.get("file", "")).lower()
            ]
        )
        for row in self.merged_rows:
            self.assertEqual(row.get("chapter"), "第2章 力、动量、能量")
            self.assertAlmostEqual(float(row.get("priority")), 0.9)
            self.assertTrue(
                str(row.get("source_type", "")).startswith("竞赛知识库·粘滞系数测定实验")
            )
            self.assertTrue(
                str(row.get("relative_path", "")).startswith(
                    "已整合知识库/粘滞系数测定实验/"
                )
            )

    def test_bm25_retrieval_finds_falling_ball_viscosity(self):
        knowledge_base = KnowledgeBase(MAIN_CHUNKS_PATH)
        results = knowledge_base.search(
            "落球法 斯托克斯阻力 终端速度 雷诺数 壁面修正 动力黏度 不确定度",
            chapter="第2章 力、动量、能量",
            top_k=15,
        )
        self.assertTrue(results)
        self.assertTrue(
            any(chunk.id.startswith("imported-viscosity-") for chunk, _ in results),
            "BM25 前 15 条没有命中粘滞系数专题知识",
        )

    def test_windows_and_rocky_materials_and_outputs_are_equivalent(self):
        counterpart_material = (
            COUNTERPART_ROOT / "教学素材" / "物理实验" / "粘滞系数测定"
        )
        counterpart_import_dir = COUNTERPART_ROOT / "agnet" / "knowledge_base" / "imports"
        counterpart_main_chunks = COUNTERPART_ROOT / "agnet" / "knowledge_base" / "chunks.jsonl"
        if not counterpart_material.is_dir():
            self.skipTest("当前部署只包含一个平台树，无法执行双镜像哈希比较")
        self.assertEqual(_tree_hashes(MATERIAL_DIR), _tree_hashes(counterpart_material))
        self.assertEqual(
            _sha256(IMPORT_PATH),
            _sha256(counterpart_import_dir / "viscosity.jsonl"),
        )
        self.assertEqual(
            _sha256(IMPORT_REPORT_PATH),
            _sha256(counterpart_import_dir / "viscosity.extraction_report.json"),
        )
        self.assertEqual(
            _manifest_without_timestamp(IMPORT_MANIFEST_PATH),
            _manifest_without_timestamp(
                counterpart_import_dir / "viscosity.manifest.json"
            ),
        )
        counterpart_rows = [
            row
            for row in _read_jsonl(counterpart_main_chunks)
            if str(row.get("id", "")).startswith("imported-viscosity-")
        ]
        self.assertEqual(self.merged_rows, counterpart_rows)


if __name__ == "__main__":
    unittest.main()
