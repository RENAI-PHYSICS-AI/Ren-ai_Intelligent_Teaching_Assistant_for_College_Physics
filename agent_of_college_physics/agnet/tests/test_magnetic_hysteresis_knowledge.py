from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_kb
import build_magnetic_hysteresis_import


VARIANT_ROOT = APP_DIR.parent
MATERIAL_DIR = VARIANT_ROOT / "\u6559\u5b66\u7d20\u6750" / "\u7269\u7406\u5b9e\u9a8c" / "\u94c1\u78c1\u6ede\u56de\u7ebf\u6d4b\u5b9a\u4e0e\u89c2\u5bdf"
REFERENCE_DIR = MATERIAL_DIR / "ref"
IMPORT_DIR = APP_DIR / "knowledge_base" / "imports"
IMPORT_PATH = IMPORT_DIR / "magnetic_hysteresis.jsonl"
MANIFEST_PATH = IMPORT_DIR / "magnetic_hysteresis.manifest.json"
REPORT_PATH = IMPORT_DIR / "magnetic_hysteresis.extraction_report.json"
MAIN_CHUNKS_PATH = APP_DIR / "knowledge_base" / "chunks.jsonl"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"

EXPECTED_MARKDOWN = {
    "\u94c1\u78c1\u6ede\u56de\u7ebf\u53ef\u89c6\u5316\u5b9e\u9a8c\u65b9\u6848.md",
    "\u94c1\u78c1\u6ede\u56de\u7ebf\u6587\u732e\u5bfc\u8bfb.md",
    "README.md",
}
EXPECTED_ROUTES = ["loop", "apparatus", "demagnetization", "fit"]
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
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise AssertionError(f"{path.name}:{line_number} must contain an object")
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


class MagneticHysteresisKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = _read_jsonl(IMPORT_PATH)
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    def test_builder_and_main_registration_contract(self) -> None:
        self.assertEqual(build_magnetic_hysteresis_import.OUTPUT_STEM, "magnetic_hysteresis")
        self.assertEqual(build_magnetic_hysteresis_import.CHUNK_SIZE, 760)
        self.assertEqual(build_magnetic_hysteresis_import.CHUNK_OVERLAP, 120)
        self.assertEqual(build_magnetic_hysteresis_import.ROUTES, EXPECTED_ROUTES)
        self.assertEqual(
            set(build_magnetic_hysteresis_import.MARKDOWN_TOPICS),
            EXPECTED_MARKDOWN,
        )
        self.assertEqual(len(build_magnetic_hysteresis_import.PDF_SPECS), 4)
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("magnetic_hysteresis"),
            ("\u94c1\u78c1\u6ede\u56de\u7ebf\u6d4b\u5b9a\u4e0e\u89c2\u5bdf\u5b9e\u9a8c", "\u7b2c7\u7ae0 \u6052\u5b9a\u78c1\u573a"),
        )
        for alias in ("\u78c1\u6ede", "\u94c1\u78c1", "\u77eb\u987d\u529b", "\u5269\u78c1", "Steinmetz"):
            self.assertEqual(build_kb.classify(alias), "\u7b2c7\u7ae0 \u6052\u5b9a\u78c1\u573a")

    def test_materials_define_four_pages_and_twelve_classic_references(self) -> None:
        plan = (MATERIAL_DIR / "\u94c1\u78c1\u6ede\u56de\u7ebf\u53ef\u89c6\u5316\u5b9e\u9a8c\u65b9\u6848.md").read_text(encoding="utf-8")
        guide = (MATERIAL_DIR / "\u94c1\u78c1\u6ede\u56de\u7ebf\u6587\u732e\u5bfc\u8bfb.md").read_text(encoding="utf-8")
        references = (REFERENCE_DIR / "README.md").read_text(encoding="utf-8")
        for route in EXPECTED_ROUTES:
            self.assertIn(f"/{route}", plan)
        for term in ("\u64ad\u653e", "\u91cd\u7f6e", "B-H", "RC \u79ef\u5206", "\u4ea4\u6d41\u9000\u78c1", "\u4e0d\u786e\u5b9a\u5ea6"):
            self.assertIn(term, plan)
        for term in (
            "Ewing",
            "Steinmetz",
            "Preisach",
            "Stoner-Wohlfarth",
            "Jiles-Atherton",
            "Bertotti",
            "IEC",
            "ASTM",
            "JCGM",
            "NIST",
        ):
            self.assertIn(term, guide + "\n" + references)
        numbers = re.findall(r"^## (\d+)\.\s", references, flags=re.MULTILINE)
        self.assertEqual(numbers, [str(index) for index in range(1, 13)])
        self.assertGreaterEqual(len(set(re.findall(r"https?://[^\s\uff09]+", references))), 10)

    def test_portable_import_schema_manifest_and_source_coverage(self) -> None:
        self.assertGreaterEqual(len(self.rows), 100)
        identifiers: list[str] = []
        for index, row in enumerate(self.rows, 1):
            self.assertEqual(set(row), REQUIRED_FIELDS, f"row {index}")
            self.assertRegex(str(row["id"]), r"^[0-9a-f]{16}$")
            identifiers.append(str(row["id"]))
            self.assertIn(row["source_type"], {"markdown", "pdf"})
            self.assertTrue(str(row["source"]).strip())
            self.assertTrue(str(row["topic"]).strip())
            self.assertGreaterEqual(len(re.sub(r"\s+", "", str(row["text"]))), 35)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual({row["source_type"] for row in self.rows}, {"markdown", "pdf"})
        corpus = "\n".join(str(row["text"]) for row in self.rows)
        for term in ("\u94c1\u78c1\u6ede\u56de\u7ebf", "\u77eb\u987d\u529b", "\u5269\u78c1", "\u793a\u6ce2\u5668", "Steinmetz", "\u4e0d\u786e\u5b9a\u5ea6"):
            self.assertIn(term, corpus)

        self.assertEqual(self.manifest.get("topic"), "\u94c1\u78c1\u6ede\u56de\u7ebf\u6d4b\u5b9a\u4e0e\u89c2\u5bdf")
        self.assertEqual(self.manifest.get("routes"), EXPECTED_ROUTES)
        self.assertEqual(self.manifest.get("documents"), 7)
        self.assertEqual(self.manifest.get("annotated_references"), 12)
        self.assertEqual(self.manifest.get("markdown_documents"), 3)
        self.assertEqual(self.manifest.get("pdf_documents"), 4)
        self.assertEqual(self.manifest.get("chunks"), len(self.rows))
        self.assertEqual(self.manifest.get("sources"), self.report)
        self.assertFalse(self.manifest.get("main_knowledge_base_modified"))
        self.assertEqual(sum(int(item["chunks"]) for item in self.report), len(self.rows))
        self.assertEqual({item["source"] for item in self.report[:3]}, EXPECTED_MARKDOWN)
        for item in self.report[3:]:
            pdf = REFERENCE_DIR / str(item["source"])
            self.assertTrue(pdf.is_file())
            self.assertGreater(pdf.stat().st_size, 100_000)
            self.assertEqual(pdf.read_bytes()[:5], b"%PDF-")
            self.assertEqual(_sha256(pdf), item["sha256"])

    def test_materials_builder_and_outputs_match_both_trees(self) -> None:
        counterpart_material = (
            COUNTERPART_ROOT / "\u6559\u5b66\u7d20\u6750" / "\u7269\u7406\u5b9e\u9a8c" / "\u94c1\u78c1\u6ede\u56de\u7ebf\u6d4b\u5b9a\u4e0e\u89c2\u5bdf"
        )
        counterpart_app = COUNTERPART_ROOT / "agnet"
        self.assertEqual(_tree_hashes(MATERIAL_DIR), _tree_hashes(counterpart_material))
        self.assertEqual(
            _sha256(APP_DIR / "build_magnetic_hysteresis_import.py"),
            _sha256(counterpart_app / "build_magnetic_hysteresis_import.py"),
        )
        counterpart_import = counterpart_app / "knowledge_base" / "imports"
        self.assertEqual(
            _sha256(IMPORT_PATH),
            _sha256(counterpart_import / "magnetic_hysteresis.jsonl"),
        )
        self.assertEqual(
            _sha256(REPORT_PATH),
            _sha256(counterpart_import / "magnetic_hysteresis.extraction_report.json"),
        )
        self.assertEqual(
            _manifest_without_timestamp(MANIFEST_PATH),
            _manifest_without_timestamp(counterpart_import / "magnetic_hysteresis.manifest.json"),
        )

    def test_merged_main_kb_when_final_build_has_run(self) -> None:
        if not MAIN_CHUNKS_PATH.is_file():
            self.skipTest("main knowledge base has not been built yet")
        merged = [
            row
            for row in _read_jsonl(MAIN_CHUNKS_PATH)
            if str(row.get("id", "")).startswith("imported-magnetic_hysteresis-")
        ]
        if not merged:
            self.skipTest("main agent has not run the final merged build yet")
        for row in merged:
            self.assertEqual(row.get("chapter"), "\u7b2c7\u7ae0 \u6052\u5b9a\u78c1\u573a")
            self.assertAlmostEqual(float(row.get("priority")), 0.9)
            self.assertTrue(
                str(row.get("source_type", "")).startswith(
                    "\u7ade\u8d5b\u77e5\u8bc6\u5e93\u00b7\u94c1\u78c1\u6ede\u56de\u7ebf\u6d4b\u5b9a\u4e0e\u89c2\u5bdf\u5b9e\u9a8c"
                )
            )


if __name__ == "__main__":
    unittest.main()
