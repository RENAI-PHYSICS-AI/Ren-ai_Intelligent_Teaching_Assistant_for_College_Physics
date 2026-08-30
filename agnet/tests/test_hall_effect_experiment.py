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

import build_hall_effect_import
import build_kb
from rag import KnowledgeBase


VARIANT_ROOT = APP_DIR.parent
MATERIAL_DIR = VARIANT_ROOT / "教学素材" / "物理实验" / "霍尔效应测磁场分布"
REFERENCE_DIR = MATERIAL_DIR / "ref"
WEB_PATH = APP_DIR / "experiments" / "hall_effect" / "web.jl"
IMPORT_DIR = APP_DIR / "knowledge_base" / "imports"
IMPORT_PATH = IMPORT_DIR / "hall_effect.jsonl"
IMPORT_MANIFEST_PATH = IMPORT_DIR / "hall_effect.manifest.json"
IMPORT_REPORT_PATH = IMPORT_DIR / "hall_effect.extraction_report.json"
MAIN_CHUNKS_PATH = APP_DIR / "knowledge_base" / "chunks.jsonl"
MAIN_MANIFEST_PATH = APP_DIR / "knowledge_base" / "manifest.json"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"

EXPECTED_ROUTES = ["calibration", "scan", "fit", "uncertainty"]
EXPECTED_PDFS = set(build_hall_effect_import.PDF_FILENAMES)
EXPECTED_MARKDOWN = {
    "霍尔效应测磁场分布可视化实验方案.md",
    "霍尔效应测磁场分布文献导读.md",
    "README.md",
}
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
                raise AssertionError(f"{path.name}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise AssertionError(f"{path.name}:{line_number} must be an object")
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


class HallEffectWebContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WEB_PATH.read_text(encoding="utf-8")

    def test_project_manifest_and_entrypoint_exist(self) -> None:
        self.assertTrue(WEB_PATH.is_file())
        self.assertTrue((WEB_PATH.parent / "Project.toml").is_file())
        self.assertTrue((WEB_PATH.parent / "Manifest.toml").is_file())

    def test_four_routes_health_and_private_runtime_contract(self) -> None:
        self.assertIn('const HEALTH_MARKER = "physics-experiment:hall-effect"', self.source)
        self.assertIn('get(ENV, "HALL_EFFECT_WEB_HOST", "127.0.0.1")', self.source)
        self.assertIn('get(ENV, "HALL_EFFECT_WEB_PORT", "9397")', self.source)
        self.assertIn('get(ENV, "HALL_EFFECT_WEB_PROXY_URL", ".")', self.source)
        self.assertIn('Bonito.route!(server, "/__physics_health__" => health_app())', self.source)
        for route in EXPECTED_ROUTES:
            self.assertIn(f'Bonito.route!(server, "/{route}"', self.source)
        self.assertIn('send("hall-effect-wgl-ready", glStatus)', self.source)
        self.assertIn('send("hall-effect-wgl-failed", detail)', self.source)

    def test_every_page_has_sliders_playback_and_reset(self) -> None:
        self.assertGreaterEqual(self.source.count("add_slider!(controls,"), 26)
        self.assertEqual(self.source.count("bind_playback!("), 5)  # helper plus four pages
        for label in ('label = "播放"', 'label = "重置"', '"暂停"'):
            self.assertIn(label, self.source)
        self.assertIn('play_button.label[] = "播放"', self.source)
        for builder in (
            "calibration_figure",
            "scan_figure",
            "fit_figure",
            "uncertainty_figure",
        ):
            self.assertIn(f"function {builder}()", self.source)
        self.assertIn(
            "for builder in (calibration_figure, scan_figure, fit_figure, uncertainty_figure)",
            self.source,
        )

    def test_physics_contract_covers_calibration_scan_fit_and_uncertainty(self) -> None:
        compact = re.sub(r"\s+", "", self.source)
        self.assertIn("returnMU0*turns*current/(2length_m)*(left-right)", compact)
        self.assertIn("effective_sensitivity=nominal_sensitivity*sensor_current_ma/10.0", compact)
        self.assertIn("estimated_field=(current_voltage-fit.intercept)/fit.slope", compact)
        self.assertIn("uniformity=(maximum(center_fields)-minimum(center_fields))", compact)
        self.assertIn("slope_se=residual_sd/sqrt(denominator)", compact)
        self.assertIn("combined=sqrt(sum(components.^2))", compact)
        for term in ("自由截距", "残差", "有限长线圈", "位置零点", "k=2"):
            self.assertIn(term, self.source)

    def test_layout_and_scaled_pointer_mapping(self) -> None:
        self.assertIn("const FIGURE_WIDTH = 960", self.source)
        self.assertIn("const FIGURE_HEIGHT = 760", self.source)
        self.assertIn('document.querySelector(".hall-effect-lab")', self.source)
        self.assertIn('"pointerdown"', self.source)
        self.assertIn("screen.winscale = baseWinscale * layoutScale", self.source)
        self.assertIn("availableWidth / $(FIGURE_WIDTH)", self.source)
        self.assertIn("availableHeight / $(FIGURE_HEIGHT)", self.source)
        self.assertIn(r"\\nWebGL 状态", self.source)
        self.assertIn(r"\\n页面地址", self.source)


class HallEffectKnowledgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.import_rows = _read_jsonl(IMPORT_PATH)
        cls.import_manifest = json.loads(IMPORT_MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.report = json.loads(IMPORT_REPORT_PATH.read_text(encoding="utf-8"))

    def test_builder_source_route_and_collection_contract(self) -> None:
        self.assertEqual(build_hall_effect_import.OUTPUT_STEM, "hall_effect")
        self.assertEqual(build_hall_effect_import.ROUTES, EXPECTED_ROUTES)
        self.assertEqual(build_hall_effect_import.CHUNK_SIZE, 760)
        self.assertEqual(build_hall_effect_import.CHUNK_OVERLAP, 120)
        self.assertEqual(set(build_hall_effect_import.PDF_SPECS), {
            REFERENCE_DIR / filename for filename in EXPECTED_PDFS
        })
        self.assertEqual(set(build_hall_effect_import.MARKDOWN_TOPICS), EXPECTED_MARKDOWN)
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("hall_effect"),
            ("霍尔效应测磁场分布实验", "第7章 恒定磁场"),
        )
        for alias in ("霍尔效应", "霍尔电压", "霍尔探头", "霍尔磁场分布", "van der Pauw 霍尔"):
            self.assertEqual(build_kb.classify(alias), "第7章 恒定磁场")

    def test_documents_define_four_pages_and_ten_core_references(self) -> None:
        plan = (MATERIAL_DIR / "霍尔效应测磁场分布可视化实验方案.md").read_text(encoding="utf-8")
        guide = (MATERIAL_DIR / "霍尔效应测磁场分布文献导读.md").read_text(encoding="utf-8")
        references = (REFERENCE_DIR / "README.md").read_text(encoding="utf-8")
        source_manifest = json.loads((REFERENCE_DIR / "source_manifest.json").read_text(encoding="utf-8"))

        for route in EXPECTED_ROUTES:
            self.assertIn(f"/{route}", plan)
        for term in (
            "有限长螺线管",
            "霍尔电压",
            "自由截距",
            "残差",
            "A 类",
            "B 类",
            "播放/暂停",
            "重置",
        ):
            self.assertIn(term, plan)
        for term in ("Hall 1879", "van der Pauw", "NIST", "Boero", "Gerken", "GUM"):
            self.assertIn(term, guide + references)

        core_numbers = re.findall(r"^### 2\.(\d+)\s", references, flags=re.MULTILINE)
        self.assertEqual(core_numbers, [str(index) for index in range(1, 11)])
        self.assertEqual(source_manifest.get("core_reference_count"), 10)
        self.assertEqual(source_manifest.get("local_pdf_count"), 8)
        self.assertGreaterEqual(len(set(re.findall(r"https?://[^\s）]+", references))), 10)

    def test_eight_local_pdfs_are_real_and_readable(self) -> None:
        actual = {path.name for path in REFERENCE_DIR.glob("*.pdf")}
        self.assertEqual(actual, EXPECTED_PDFS)
        for name in EXPECTED_PDFS:
            path = REFERENCE_DIR / name
            with path.open("rb") as handle:
                self.assertEqual(handle.read(5), b"%PDF-")
            self.assertGreater(len(PdfReader(str(path)).pages), 0)

    def test_import_schema_manifest_and_core_physics(self) -> None:
        self.assertGreaterEqual(len(self.import_rows), 100)
        identifiers: list[str] = []
        for index, row in enumerate(self.import_rows, 1):
            self.assertEqual(set(row), REQUIRED_FIELDS, f"row {index}")
            self.assertRegex(str(row["id"]), r"^[0-9a-f]{16}$")
            identifiers.append(str(row["id"]))
            self.assertIn(row["source_type"], {"markdown", "pdf"})
            self.assertTrue(str(row["text"]).strip())
            self.assertTrue(str(row["topic"]).strip())
        self.assertEqual(len(identifiers), len(set(identifiers)))

        corpus = "\n".join(str(row["text"]) for row in self.import_rows)
        for term in (
            "霍尔效应",
            "霍尔电压",
            "磁场分布",
            "有限长螺线管",
            "零场偏置",
            "残差",
            "不确定度",
        ):
            self.assertIn(term, corpus)

        manifest = self.import_manifest
        self.assertEqual(manifest.get("topic"), "霍尔效应测磁场分布")
        self.assertEqual(manifest.get("routes"), EXPECTED_ROUTES)
        self.assertEqual(manifest.get("core_references"), 10)
        self.assertEqual(manifest.get("documents"), 11)
        self.assertEqual(manifest.get("markdown_documents"), 3)
        self.assertEqual(manifest.get("pdf_documents"), 8)
        self.assertEqual(manifest.get("chunks"), len(self.import_rows))
        self.assertEqual(manifest.get("sources"), self.report)

    def test_main_kb_contains_hall_effect_collection(self) -> None:
        main_rows = _read_jsonl(MAIN_CHUNKS_PATH)
        merged = [
            row for row in main_rows
            if str(row.get("id", "")).startswith("imported-hall_effect-")
        ]
        self.assertGreater(len(merged), 0)
        self.assertTrue(all(row.get("chapter") == "第7章 恒定磁场" for row in merged))
        self.assertTrue(
            all(
                str(row.get("source_type", "")).startswith(
                    "竞赛知识库·霍尔效应测磁场分布实验"
                )
                for row in merged
            )
        )

        main_manifest = json.loads(MAIN_MANIFEST_PATH.read_text(encoding="utf-8"))
        imports = {
            item.get("file"): item
            for item in main_manifest.get("imported_knowledge_bases", [])
        }
        self.assertIn("hall_effect.jsonl", imports)
        entry = imports["hall_effect.jsonl"]
        self.assertGreater(int(entry.get("chunks", 0)), 0)

        kb = KnowledgeBase(APP_DIR / "knowledge_base" / "chunks.jsonl")
        results = kb.search(
            "霍尔探头沿有限长螺线管轴线扫描磁场分布", top_k=10
        )
        self.assertTrue(
            any(chunk.id.startswith("imported-hall_effect-") for chunk, _ in results)
        )

    def test_two_code_trees_are_byte_identical_for_topic_files(self) -> None:
        counterpart_app = COUNTERPART_ROOT / "agnet"
        counterpart_material = COUNTERPART_ROOT / "教学素材" / "物理实验" / "霍尔效应测磁场分布"
        self.assertEqual(
            _tree_hashes(APP_DIR / "experiments" / "hall_effect"),
            _tree_hashes(counterpart_app / "experiments" / "hall_effect"),
        )
        self.assertEqual(_tree_hashes(MATERIAL_DIR), _tree_hashes(counterpart_material))
        for filename in (
            "build_hall_effect_import.py",
            "knowledge_base/imports/hall_effect.jsonl",
            "knowledge_base/imports/hall_effect.manifest.json",
            "knowledge_base/imports/hall_effect.extraction_report.json",
            "tests/test_hall_effect_experiment.py",
        ):
            self.assertEqual(
                _sha256(APP_DIR / filename),
                _sha256(counterpart_app / filename),
                filename,
            )


if __name__ == "__main__":
    unittest.main()
