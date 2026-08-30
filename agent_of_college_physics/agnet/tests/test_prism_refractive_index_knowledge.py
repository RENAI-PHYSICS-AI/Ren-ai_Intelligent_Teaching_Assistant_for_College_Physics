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

import build_prism_refractive_index_import


VARIANT_ROOT = APP_DIR.parent
MATERIAL_DIR = VARIANT_ROOT / "教学素材" / "物理实验" / "三棱镜折射率测定"
REFERENCE_DIR = MATERIAL_DIR / "ref"
IMPORT_DIR = APP_DIR / "knowledge_base" / "imports"
IMPORT_PATH = IMPORT_DIR / "prism_refractive_index.jsonl"
IMPORT_MANIFEST_PATH = IMPORT_DIR / "prism_refractive_index.manifest.json"
IMPORT_REPORT_PATH = IMPORT_DIR / "prism_refractive_index.extraction_report.json"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"

EXPECTED_PDFS = {
    "SCHOTT_TIE29_Refractive_Index_Dispersion.pdf",
    "SCHOTT_Optical_Glass_Pocket_Catalog.pdf",
    "UCI_Faraday_Prism_Refractometry.pdf",
    "CSM_Prism_Spectrometer_Lab06.pdf",
    "Rochester_Student_Spectrometer_Experiment14.pdf",
    "JCGM_100_2008_GUM.pdf",
}
EXPECTED_ROUTES = ["collimation", "apex", "minimum-deviation", "dispersion"]
REQUIRED_FIELDS = {"id", "source", "source_type", "page", "chunk", "text", "title", "year", "language", "topic", "locator"}


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


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


class PrismRefractiveIndexKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = [
            MATERIAL_DIR / "三棱镜折射率可视化实验方案.md",
            MATERIAL_DIR / "三棱镜折射率文献导读.md",
            MATERIAL_DIR / "manifest.json",
            MATERIAL_DIR / "sources.json",
            REFERENCE_DIR / "README.md",
            *(REFERENCE_DIR / name for name in EXPECTED_PDFS),
            IMPORT_PATH,
            IMPORT_MANIFEST_PATH,
            IMPORT_REPORT_PATH,
        ]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise AssertionError("三棱镜折射率知识库产物缺失：" + ", ".join(missing))
        cls.catalog = json.loads((MATERIAL_DIR / "sources.json").read_text(encoding="utf-8"))
        cls.rows = _read_jsonl(IMPORT_PATH)
        cls.manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.report = json.loads(IMPORT_REPORT_PATH.read_text(encoding="utf-8"))

    def test_builder_declares_stable_contract(self) -> None:
        self.assertEqual(build_prism_refractive_index_import.OUTPUT_STEM, "prism_refractive_index")
        self.assertEqual(build_prism_refractive_index_import.ROUTES, EXPECTED_ROUTES)
        self.assertEqual(build_prism_refractive_index_import.CHUNK_SIZE, 760)
        self.assertEqual(build_prism_refractive_index_import.CHUNK_OVERLAP, 120)
        self.assertEqual(set(build_prism_refractive_index_import.PDF_FILENAMES), EXPECTED_PDFS)
        self.assertEqual({path.name for path in build_prism_refractive_index_import.PDF_SPECS}, EXPECTED_PDFS)

    def test_exactly_ten_traceable_authoritative_references(self) -> None:
        self.assertEqual(len(self.catalog), 10)
        self.assertEqual(len({item["id"] for item in self.catalog}), 10)
        self.assertEqual(sum(item["local_file"] is not None for item in self.catalog), 6)
        for item in self.catalog:
            self.assertRegex(item["url"], r"^https://")
            self.assertGreaterEqual(int(item["year"]), 1704)
            self.assertTrue(item["title"].strip())
            self.assertTrue(item["topic"].strip())
        readme = (REFERENCE_DIR / "README.md").read_text(encoding="utf-8")
        numbers = re.findall(r"^### 2\.(\d+)\s", readme, flags=re.MULTILINE)
        self.assertEqual(numbers, [str(index) for index in range(1, 11)])

    def test_six_public_authoritative_pdfs_are_readable(self) -> None:
        self.assertEqual({path.name for path in REFERENCE_DIR.glob("*.pdf")}, EXPECTED_PDFS)
        for name in EXPECTED_PDFS:
            path = REFERENCE_DIR / name
            with path.open("rb") as handle:
                self.assertEqual(handle.read(5), b"%PDF-")
            self.assertGreater(len(PdfReader(str(path)).pages), 0)

    def test_import_schema_formula_and_subject_coverage(self) -> None:
        self.assertGreaterEqual(len(self.rows), 90)
        identifiers: list[str] = []
        for index, row in enumerate(self.rows, 1):
            self.assertEqual(set(row), REQUIRED_FIELDS, f"row {index}")
            self.assertRegex(row["id"], r"^[0-9a-f]{16}$")
            identifiers.append(row["id"])
            self.assertIn(row["source_type"], {"markdown", "pdf", "reference_metadata"})
            self.assertGreaterEqual(len(re.sub(r"\s+", "", str(row["text"]))), 35)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        corpus = re.sub(r"\s+", "", "\n".join(str(row["text"]) for row in self.rows))
        for term in ("分光计", "顶角", "最小偏向", "折射率", "Cauchy", "Sellmeier", "Abbe", "不确定度"):
            self.assertIn(term, corpus)
        self.assertRegex(corpus, r"n=.*sin.*A.*δ.*sin.*A")

    def test_manifest_and_extraction_report_match(self) -> None:
        self.assertEqual(self.manifest["topic"], "三棱镜折射率测定")
        self.assertEqual(self.manifest["routes"], EXPECTED_ROUTES)
        self.assertEqual(self.manifest["core_references"], 10)
        self.assertEqual(self.manifest["documents"], 10)
        self.assertEqual(self.manifest["markdown_documents"], 3)
        self.assertEqual(self.manifest["catalog_documents"], 1)
        self.assertEqual(self.manifest["pdf_documents"], 6)
        self.assertEqual(self.manifest["chunks"], len(self.rows))
        self.assertEqual(self.manifest["sources"], self.report)
        self.assertFalse(self.manifest["main_knowledge_base_modified"])
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row["source"]] = counts.get(row["source"], 0) + 1
        for item in self.report:
            self.assertEqual(item["chunks"], counts.get(item["source"], 0))
            if item["source_type"] == "pdf":
                path = REFERENCE_DIR / item["source"]
                self.assertEqual(item["bytes"], path.stat().st_size)
                self.assertEqual(item["sha256"], _sha256(path))
                self.assertEqual(item["pdf_signature"], "%PDF-")
                self.assertFalse(item["ocr_recommended"])

    def test_materials_builder_imports_and_tests_are_identical_in_both_trees(self) -> None:
        counterpart_material = COUNTERPART_ROOT / "教学素材" / "物理实验" / "三棱镜折射率测定"
        counterpart_app = COUNTERPART_ROOT / "agnet"
        counterpart_import = counterpart_app / "knowledge_base" / "imports"
        if not counterpart_material.is_dir():
            self.skipTest("counterpart tree is not present")
        self.assertEqual(_tree_hashes(MATERIAL_DIR), _tree_hashes(counterpart_material))
        self.assertEqual(_sha256(APP_DIR / "build_prism_refractive_index_import.py"), _sha256(counterpart_app / "build_prism_refractive_index_import.py"))
        self.assertEqual(_sha256(IMPORT_PATH), _sha256(counterpart_import / IMPORT_PATH.name))
        self.assertEqual(_sha256(IMPORT_REPORT_PATH), _sha256(counterpart_import / IMPORT_REPORT_PATH.name))
        left = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
        right = json.loads((counterpart_import / IMPORT_MANIFEST_PATH.name).read_text(encoding="utf-8"))
        left.pop("created_at", None)
        right.pop("created_at", None)
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
