from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VARIANTS = (ROOT, ROOT / "agent_of_college_physics")
CASES = {
    "gas_gamma": ("气体gamma常数测定", 2, 62),
    "grating_interference": ("光栅干涉", 1, 22),
    "light_polarization": ("光的偏振研究", 3, 236),
    "michelson_wavelength": ("迈克尔逊干涉仪测波长", 3, 100),
}


class AddedExperimentKnowledgeTests(unittest.TestCase):
    def test_sources_imports_and_main_merge_are_complete(self) -> None:
        for variant in VARIANTS:
            kb = variant / "agnet" / "knowledge_base"
            main_manifest = json.loads((kb / "manifest.json").read_text(encoding="utf-8"))
            merged = {item["file"]: item for item in main_manifest["imported_knowledge_bases"]}
            for stem, (folder, minimum_pdfs, minimum_chunks) in CASES.items():
                with self.subTest(variant=variant.name, stem=stem):
                    material = variant / "教学素材" / "物理实验" / folder
                    sources = json.loads((material / "sources.json").read_text(encoding="utf-8"))
                    manifest = json.loads((kb / "imports" / f"{stem}.manifest.json").read_text(encoding="utf-8"))
                    self.assertEqual(len(sources), 10)
                    self.assertGreaterEqual(len(list((material / "ref").glob("*.pdf"))), minimum_pdfs)
                    self.assertGreaterEqual(manifest["chunks"], minimum_chunks)
                    self.assertEqual(manifest["routes"], json.loads((material / "manifest.json").read_text(encoding="utf-8"))["routes"])
                    self.assertIn(f"{stem}.jsonl", merged)
                    self.assertEqual(merged[f"{stem}.jsonl"]["invalid_skipped"], 0)


if __name__ == "__main__":
    unittest.main()
