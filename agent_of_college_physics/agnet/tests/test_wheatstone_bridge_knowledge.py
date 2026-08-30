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
import build_wheatstone_bridge_import


VARIANT_ROOT = APP_DIR.parent
MATERIAL_DIR = VARIANT_ROOT / "教学素材" / "物理实验" / "惠斯通电桥测电阻"
REFERENCE_DIR = MATERIAL_DIR / "ref"
IMPORT_DIR = APP_DIR / "knowledge_base" / "imports"
IMPORT_PATH = IMPORT_DIR / "wheatstone_bridge.jsonl"
MANIFEST_PATH = IMPORT_DIR / "wheatstone_bridge.manifest.json"
REPORT_PATH = IMPORT_DIR / "wheatstone_bridge.extraction_report.json"
MAIN_CHUNKS_PATH = APP_DIR / "knowledge_base" / "chunks.jsonl"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"

EXPECTED_MARKDOWN = {
    "惠斯通电桥可视化实验方案.md",
    "惠斯通电桥文献导读.md",
    "README.md",
}
EXPECTED_ROUTES = ["principle", "balance", "sensitivity", "fit"]
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
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
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


class WheatstoneBridgeKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = _read_jsonl(IMPORT_PATH)
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    def test_builder_and_main_registration_contract(self) -> None:
        self.assertEqual(build_wheatstone_bridge_import.OUTPUT_STEM, "wheatstone_bridge")
        self.assertEqual(build_wheatstone_bridge_import.CHUNK_SIZE, 760)
        self.assertEqual(build_wheatstone_bridge_import.CHUNK_OVERLAP, 120)
        self.assertEqual(build_wheatstone_bridge_import.ROUTES, EXPECTED_ROUTES)
        self.assertEqual(build_wheatstone_bridge_import.CORE_REFERENCE_COUNT, 11)
        self.assertEqual(
            set(build_wheatstone_bridge_import.MARKDOWN_TOPICS),
            EXPECTED_MARKDOWN,
        )
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("wheatstone_bridge"),
            ("惠斯通电桥测电阻实验", "第6章 静电场"),
        )
        for alias in ("惠斯通", "电桥", "桥路", "平衡电桥", "测电阻"):
            self.assertEqual(build_kb.classify(alias), "第6章 静电场")

    def test_documents_define_four_pages_and_eleven_sources(self) -> None:
        plan = (MATERIAL_DIR / "惠斯通电桥可视化实验方案.md").read_text(
            encoding="utf-8"
        )
        guide = (MATERIAL_DIR / "惠斯通电桥文献导读.md").read_text(
            encoding="utf-8"
        )
        references = (REFERENCE_DIR / "README.md").read_text(encoding="utf-8")
        for route in EXPECTED_ROUTES:
            self.assertIn(f"/{route}", plan)
        for term in (
            "960 × 760",
            "指针",
            "播放/暂停",
            "重置",
            "零电流",
            "戴维南",
            "接触",
            "不确定度",
        ):
            self.assertIn(term, plan)
        for term in (
            "Christie",
            "Wheatstone",
            "Maxwell",
            "NIST",
            "零示法",
            "自热",
            "协方差",
        ):
            self.assertIn(term, guide)
        numbers = re.findall(r"^### 2\.(\d+)\s", references, flags=re.MULTILINE)
        self.assertEqual(numbers, [str(index) for index in range(1, 12)])
        self.assertGreaterEqual(
            len(set(re.findall(r"https?://[^\s）]+", references))),
            11,
        )
        for authority in ("Royal Society", "NIST", "OpenStax", "MIT", "JCGM"):
            self.assertIn(authority, references)

    def test_portable_import_schema_and_physics_coverage(self) -> None:
        self.assertGreaterEqual(len(self.rows), 25)
        identifiers: list[str] = []
        for index, row in enumerate(self.rows, 1):
            self.assertEqual(set(row), REQUIRED_FIELDS, f"row {index}")
            self.assertRegex(str(row["id"]), r"^[0-9a-f]{16}$")
            identifiers.append(str(row["id"]))
            self.assertEqual(row["source_type"], "markdown")
            self.assertTrue(str(row["source"]).strip())
            self.assertTrue(str(row["title"]).strip())
            self.assertTrue(str(row["topic"]).strip())
            self.assertTrue(str(row["locator"]).strip())
            self.assertGreaterEqual(len(re.sub(r"\s+", "", str(row["text"]))), 35)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        corpus = "\n".join(str(row["text"]) for row in self.rows)
        for term in (
            "惠斯通电桥",
            "平衡",
            "检流计",
            "戴维南",
            "接触电阻",
            "灵敏度",
            "不确定度",
            "Christie",
            "Wheatstone",
        ):
            self.assertIn(term, corpus)

    def test_manifest_and_report_match_import(self) -> None:
        self.assertEqual(self.manifest.get("topic"), "惠斯通电桥测电阻")
        self.assertEqual(self.manifest.get("measured_quantity"), "未知电阻 R_x")
        self.assertEqual(self.manifest.get("routes"), EXPECTED_ROUTES)
        self.assertEqual(self.manifest.get("documents"), 3)
        self.assertEqual(self.manifest.get("markdown_documents"), 3)
        self.assertEqual(self.manifest.get("pdf_documents"), 0)
        self.assertEqual(self.manifest.get("core_references"), 11)
        self.assertEqual(self.manifest.get("chunks"), len(self.rows))
        self.assertEqual(self.manifest.get("sources"), self.report)
        self.assertFalse(self.manifest.get("main_knowledge_base_modified"))
        self.assertEqual(
            {source["source"] for source in self.report},
            EXPECTED_MARKDOWN,
        )
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[str(row["source"])] = counts.get(str(row["source"]), 0) + 1
        for source in self.report:
            self.assertEqual(source["chunks"], counts[source["source"]])
            self.assertGreater(source["bytes"], 0)

    def test_materials_builder_and_outputs_match_both_trees(self) -> None:
        counterpart_material = (
            COUNTERPART_ROOT / "教学素材" / "物理实验" / "惠斯通电桥测电阻"
        )
        counterpart_app = COUNTERPART_ROOT / "agnet"
        self.assertEqual(_tree_hashes(MATERIAL_DIR), _tree_hashes(counterpart_material))
        self.assertEqual(
            _sha256(APP_DIR / "build_wheatstone_bridge_import.py"),
            _sha256(counterpart_app / "build_wheatstone_bridge_import.py"),
        )
        counterpart_import = counterpart_app / "knowledge_base" / "imports"
        self.assertEqual(
            _sha256(IMPORT_PATH),
            _sha256(counterpart_import / "wheatstone_bridge.jsonl"),
        )
        self.assertEqual(
            _sha256(REPORT_PATH),
            _sha256(counterpart_import / "wheatstone_bridge.extraction_report.json"),
        )
        self.assertEqual(
            _manifest_without_timestamp(MANIFEST_PATH),
            _manifest_without_timestamp(
                counterpart_import / "wheatstone_bridge.manifest.json"
            ),
        )

    def test_merged_main_kb_when_final_build_has_run(self) -> None:
        if not MAIN_CHUNKS_PATH.is_file():
            self.skipTest("main knowledge base has not been built yet")
        merged = [
            row
            for row in _read_jsonl(MAIN_CHUNKS_PATH)
            if str(row.get("id", "")).startswith("imported-wheatstone_bridge-")
        ]
        if not merged:
            self.skipTest("main agent has not run the final merged build yet")
        for row in merged:
            self.assertEqual(row.get("chapter"), "第6章 静电场")
            self.assertAlmostEqual(float(row.get("priority")), 0.9)
            self.assertTrue(
                str(row.get("source_type", "")).startswith(
                    "竞赛知识库·惠斯通电桥测电阻实验"
                )
            )


if __name__ == "__main__":
    unittest.main()
