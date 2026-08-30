from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path, PurePosixPath

from pypdf import PdfReader


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_kb
from rag import KnowledgeBase


VARIANT_ROOT = APP_DIR.parent
MATERIAL_DIR = VARIANT_ROOT / "教学素材" / "物理实验" / "转动惯量测定"
REFERENCE_DIR = MATERIAL_DIR / "ref"
KB_DIR = APP_DIR / "knowledge_base"
IMPORT_DIR = KB_DIR / "imports"
IMPORT_PATH = IMPORT_DIR / "rotational_inertia.jsonl"
IMPORT_MANIFEST_PATH = IMPORT_DIR / "rotational_inertia.manifest.json"
IMPORT_REPORT_PATH = IMPORT_DIR / "rotational_inertia.extraction_report.json"
MAIN_CHUNKS_PATH = KB_DIR / "chunks.jsonl"
MAIN_MANIFEST_PATH = KB_DIR / "manifest.json"

if VARIANT_ROOT.name == "agent_of_college_physics":
    COUNTERPART_ROOT = VARIANT_ROOT.parent
else:
    COUNTERPART_ROOT = VARIANT_ROOT / "agent_of_college_physics"

EXPECTED_PDFS = {
    "Blanes_et_al_2022_Inertial_Properties_Padel_Racket.pdf": (
        22,
        "521e7db5b4386e22197f012936314515aee025ec1b5d435c3e58877014a0ae81",
    ),
    "JCGM_100_2008_GUM.pdf": (
        134,
        "41bbf068fbc0d7986c98691b2d1af6680cb3044f6a1a89b3560933ed9ef9626c",
    ),
    "Meywerk_Hellberg_2024_Trifilar_Nonlinearities.pdf": (
        12,
        "5728a5189363f91944eaf130daea41ee9a2c89f588149036e64a868ec438f69c",
    ),
    "NIST_TN1297_Uncertainty.pdf": (
        25,
        "f2c8e6026d5589a63d492f192b72cd905f554b477a6049532256170aec477e92",
    ),
    "NTHU_2022_Moments_of_Inertia.pdf": (
        10,
        "f4bf470bbb6cdb70fc51143636356ce8753d2a5c298614c3e4c6d056b7ec105b",
    ),
    "University_of_Toronto_Torsion_Pendulum_Summary.pdf": (
        6,
        "eab988ec88b6700713875a9fe767fac05bb20f142d4de7b92935e862bd600eaf",
    ),
    "WWU_Torsion_Pendulum.pdf": (
        4,
        "036b22c3c3686172cbfd03def7e5ec933aabe110b530baf5a533ef55d3d8a8bb",
    ),
    "Yu_Ying_2016_Trifilar_Period_Count.pdf": (
        3,
        "993f02e20abd7a79814e4620e4f7e934dca40b710a8ae5dd3a268546140b0897",
    ),
}

IMPORTED_PDFS = {
    name
    for name in EXPECTED_PDFS
    if name not in {"JCGM_100_2008_GUM.pdf", "NIST_TN1297_Uncertainty.pdf"}
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
                raise AssertionError(
                    f"{path.name}:{line_number} must contain a JSON object"
                )
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


class RotationalInertiaKnowledgeIntegrationTests(unittest.TestCase):
    """Regression contract for the rotational-inertia literature and KB."""

    @classmethod
    def setUpClass(cls) -> None:
        required = (
            MATERIAL_DIR / "转动惯量可视化实验方案.md",
            MATERIAL_DIR / "转动惯量文献导读.md",
            REFERENCE_DIR / "README.md",
            IMPORT_PATH,
            IMPORT_MANIFEST_PATH,
            IMPORT_REPORT_PATH,
            MAIN_CHUNKS_PATH,
            MAIN_MANIFEST_PATH,
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise AssertionError("转动惯量知识库产物尚未构建：" + ", ".join(missing))

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
            if str(row.get("id", "")).startswith("imported-rotational_inertia-")
        ]

    def test_documents_define_four_independent_experiments_and_ten_core_sources(self):
        plan = (MATERIAL_DIR / "转动惯量可视化实验方案.md").read_text(
            encoding="utf-8"
        )
        guide = (MATERIAL_DIR / "转动惯量文献导读.md").read_text(
            encoding="utf-8"
        )
        references = (REFERENCE_DIR / "README.md").read_text(encoding="utf-8")

        for route in ("/torsion", "/trifilar", "/parallel-axis", "/pendulum-fit"):
            self.assertIn(route, plan)
        for term in (
            "扭摆",
            "三线摆",
            "平行轴定理",
            "复摆",
            "960 × 760",
            "指针",
            "不确定度",
        ):
            self.assertIn(term, plan)
        for term in (
            "周期法",
            "空台",
            "自由截距",
            "回转半径",
            "A 类",
            "B 类",
        ):
            self.assertIn(term, guide)

        core_numbers = re.findall(r"^### 2\.(\d+)\s", references, flags=re.MULTILINE)
        self.assertEqual(core_numbers, [str(index) for index in range(1, 11)])
        self.assertGreaterEqual(len(set(re.findall(r"https://doi\.org/[^\s）]+", references))), 7)
        for pdf_name, (pages, digest) in EXPECTED_PDFS.items():
            self.assertIn(pdf_name, references)
            self.assertIn(f"| {pages} |", references)
            self.assertIn(digest, references)

    def test_all_eight_local_pdfs_have_expected_signature_hash_and_page_count(self):
        actual_pdfs = {path.name for path in REFERENCE_DIR.glob("*.pdf")}
        self.assertEqual(actual_pdfs, set(EXPECTED_PDFS))
        for name, (expected_pages, expected_digest) in EXPECTED_PDFS.items():
            path = REFERENCE_DIR / name
            with self.subTest(pdf=name):
                self.assertEqual(path.read_bytes()[:5], b"%PDF-")
                self.assertEqual(_sha256(path), expected_digest)
                self.assertEqual(len(PdfReader(str(path)).pages), expected_pages)

    def test_import_has_exactly_285_portable_physics_chunks(self):
        self.assertEqual(len(self.import_rows), 285)
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
                f"rotational_inertia.jsonl 第 {index} 条缺少字段："
                f"{sorted(required_fields - set(row))}",
            )
            identifiers.append(str(row["id"]))
            self.assertTrue(str(row["id"]).strip())
            self.assertIn(row["source_type"], {"markdown", "pdf"})
            self.assertIsInstance(row["page"], int)
            self.assertIsInstance(row["chunk"], int)
            for field in ("source", "text", "title", "topic", "locator"):
                self.assertTrue(str(row[field]).strip())
        self.assertEqual(len(identifiers), len(set(identifiers)))

        corpus = "\n".join(str(row["text"]) for row in self.import_rows)
        for term in (
            "转动惯量",
            "扭转常量",
            "三线摆",
            "平行轴定理",
            "复摆",
            "回转半径",
            "不确定度",
        ):
            self.assertIn(term, corpus)
        compact = re.sub(r"[\s$]", "", corpus)
        self.assertIn(r"I=\frac{\kappaT^2}{4\pi^2}-I_0", compact)
        self.assertIn(r"I_O=I_C+md^2", compact)

    def test_manifest_and_report_describe_the_exact_import(self):
        manifest = self.import_manifest
        self.assertEqual(manifest.get("topic"), "转动惯量测定")
        self.assertEqual(manifest.get("chunks"), 285)
        self.assertEqual(manifest.get("documents"), 9)
        self.assertEqual(manifest.get("markdown_documents"), 3)
        self.assertEqual(manifest.get("pdf_documents"), 6)
        self.assertEqual(manifest.get("chunk_size"), 760)
        self.assertEqual(manifest.get("chunk_overlap"), 120)
        self.assertEqual(
            manifest.get("routes"),
            ["torsion", "trifilar", "parallel-axis", "pendulum-fit"],
        )
        self.assertEqual(manifest.get("measured_quantity"), "刚体相对给定转轴的转动惯量 I")

        sources = manifest.get("sources", [])
        self.assertEqual(len(sources), 9)
        self.assertEqual(sum(int(source.get("chunks", 0)) for source in sources), 285)
        pdf_sources = {
            str(source.get("source"))
            for source in sources
            if source.get("source_type") == "pdf"
        }
        self.assertEqual(pdf_sources, IMPORTED_PDFS)
        for source in sources:
            source_path = str(source.get("source_path", ""))
            self.assertTrue(source_path)
            self.assertFalse(re.match(r"^[A-Za-z]:[\\/]", source_path))
            self.assertFalse(source_path.startswith(("/", "\\", "file:")))
            self.assertNotIn("..", PurePosixPath(source_path.replace("\\", "/")).parts)
            if source.get("source_type") == "pdf":
                pages, digest = EXPECTED_PDFS[str(source["source"])]
                self.assertEqual(source.get("pdf_signature"), "%PDF-")
                self.assertEqual(source.get("pages"), pages)
                self.assertEqual(source.get("sha256"), digest)

        self.assertIsInstance(self.extraction_report, list)
        self.assertEqual(len(self.extraction_report), 9)
        self.assertEqual(
            {str(item.get("source")) for item in self.extraction_report},
            {str(source.get("source")) for source in sources},
        )
        for item in self.extraction_report:
            self.assertIsInstance(item.get("chunks"), int)
            if item.get("source_type") == "pdf":
                self.assertEqual(item.get("pages"), EXPECTED_PDFS[str(item["source"])][0])
                self.assertIsInstance(item.get("empty_pages"), list)
                self.assertIsInstance(item.get("ocr_recommended"), bool)

    def test_main_kb_contains_all_285_chunks_in_rigid_body_chapter(self):
        self.assertEqual(
            build_kb.IMPORTED_COLLECTIONS.get("rotational_inertia"),
            ("转动惯量测定实验", "第3章 刚体的定轴转动"),
        )
        imported = {
            entry.get("file"): entry
            for entry in self.main_manifest.get("imported_knowledge_bases", [])
        }
        self.assertIn("rotational_inertia.jsonl", imported)
        entry = imported["rotational_inertia.jsonl"]
        self.assertEqual(entry.get("chunks"), 285)
        self.assertEqual(entry.get("duplicates_skipped"), 0)
        self.assertEqual(entry.get("invalid_skipped"), 0)
        self.assertEqual(len(self.merged_rows), 285)
        self.assertEqual(
            self.main_manifest.get("by_type", {}).get("imported_rotational_inertia_chunks"),
            285,
        )
        self.assertEqual(self.main_manifest.get("chunks"), len(self.main_rows))
        self.assertFalse(
            [
                failure
                for failure in self.main_manifest.get("import_failures", [])
                if "rotational_inertia" in str(failure.get("file", "")).lower()
            ]
        )
        for row in self.merged_rows:
            self.assertEqual(row.get("chapter"), "第3章 刚体的定轴转动")
            self.assertAlmostEqual(float(row.get("priority")), 0.9)
            self.assertTrue(
                str(row.get("source_type", "")).startswith(
                    "竞赛知识库·转动惯量测定实验"
                )
            )
            self.assertTrue(
                str(row.get("relative_path", "")).startswith(
                    "已整合知识库/转动惯量测定实验/"
                )
            )

    def test_bm25_retrieval_finds_period_based_inertia_measurement(self):
        knowledge_base = KnowledgeBase(MAIN_CHUNKS_PATH)
        results = knowledge_base.search(
            "转动惯量 扭摆 三线摆 周期 平行轴定理 复摆 回转半径 不确定度",
            chapter="第3章 刚体的定轴转动",
            top_k=10,
        )
        self.assertTrue(results)
        self.assertTrue(
            any(
                chunk.id.startswith("imported-rotational_inertia-")
                for chunk, _ in results
            ),
            "BM25 前 10 条没有命中转动惯量专题知识",
        )

    def test_windows_and_rocky_materials_and_kb_outputs_are_equivalent(self):
        counterpart_material = (
            COUNTERPART_ROOT / "教学素材" / "物理实验" / "转动惯量测定"
        )
        counterpart_import_dir = COUNTERPART_ROOT / "agnet" / "knowledge_base" / "imports"
        counterpart_main_chunks = (
            COUNTERPART_ROOT / "agnet" / "knowledge_base" / "chunks.jsonl"
        )
        if not counterpart_material.is_dir():
            self.skipTest("当前部署只包含一个平台树，无法执行双镜像哈希比较")
        self.assertEqual(_tree_hashes(MATERIAL_DIR), _tree_hashes(counterpart_material))
        self.assertEqual(
            _sha256(IMPORT_PATH),
            _sha256(counterpart_import_dir / "rotational_inertia.jsonl"),
        )
        self.assertEqual(
            _sha256(IMPORT_REPORT_PATH),
            _sha256(counterpart_import_dir / "rotational_inertia.extraction_report.json"),
        )
        self.assertEqual(
            _manifest_without_timestamp(IMPORT_MANIFEST_PATH),
            _manifest_without_timestamp(
                counterpart_import_dir / "rotational_inertia.manifest.json"
            ),
        )
        counterpart_rows = [
            row
            for row in _read_jsonl(counterpart_main_chunks)
            if str(row.get("id", "")).startswith("imported-rotational_inertia-")
        ]
        self.assertEqual(self.merged_rows, counterpart_rows)


if __name__ == "__main__":
    unittest.main()
