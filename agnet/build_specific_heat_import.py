from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from build_viscosity_import import (
    atomic_write_text,
    clean,
    extract_pdf,
    make_row,
    relative_path,
    split_chunks,
    useful,
    write_json,
)
from config import IMPORTED_KB_DIR, PROJECT_ROOT


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "固体比热容的测定"
REF_DIR = SOURCE_DIR / "ref"
OUTPUT_STEM = "specific_heat"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120
ROUTES = ["mixing", "cooling", "electrical", "fit"]

# Keep the six distributable filenames in one place so a source replacement
# does not require hunting through importer logic or tests.
PDF_FILENAMES = (
    "Dulong_Petit_1819_Atomic_Heat.pdf",
    "Einstein_1907_Specific_Heat.pdf",
    "Debye_1912_Specific_Heat.pdf",
    "Furukawa_et_al_1956_Sapphire_Calorimetry.pdf",
    "JCGM_100_2008_GUM.pdf",
    "NIST_TN1297_Uncertainty.pdf",
)

_PDF_METADATA = {
    "Dulong_Petit_1819_Atomic_Heat.pdf": {
        "title": "Dulong–Petit 1819 原始数据表教学摘页（Recherches sur quelques points importants de la théorie de la chaleur）",
        "year": 1819,
        "topic": "固体比热容·Dulong–Petit 定律与原子热",
        "pages": None,
        "url": "https://perso.ens-lyon.fr/benjamin.monnet/LP/LP44%20Capacit%C3%A9s%20thermique.%20Description%2C%20interp%C3%A9tations%20miscroscopiques/Petit.pdf",
    },
    "Einstein_1907_Specific_Heat.pdf": {
        "title": "Die Plancksche Theorie der Strahlung und die Theorie der spezifischen Wärme",
        "year": 1907,
        "topic": "固体比热容·Einstein 模型、量子振子与低温偏离",
        "pages": None,
        "url": "https://commons.wikimedia.org/wiki/File:Einstein1906.pdf",
    },
    "Debye_1912_Specific_Heat.pdf": {
        "title": "Zur Theorie der spezifischen Wärmen",
        "year": 1912,
        "topic": "固体比热容·Debye 模型、声子谱与低温三次方律",
        "pages": None,
        "url": "https://zenodo.org/records/1424256",
    },
    "Furukawa_et_al_1956_Sapphire_Calorimetry.pdf": {
        "title": "Thermal Properties of Aluminum Oxide From 0° to 1,200° K",
        "year": 1956,
        "topic": "固体比热容·蓝宝石基准、绝热量热与 Bunsen 冰量热",
        "pages": None,
        "url": "https://doi.org/10.6028/jres.057.008",
    },
    "JCGM_100_2008_GUM.pdf": {
        "title": "Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement",
        "year": 2008,
        "topic": "固体比热容·A 类与 B 类不确定度、协方差和结果表达",
        "pages": list(range(17, 41)),
        "url": "https://doi.org/10.59161/JCGM100-2008E",
    },
    "NIST_TN1297_Uncertainty.pdf": {
        "title": "Guidelines for Evaluating and Expressing the Uncertainty of NIST Measurement Results",
        "year": 1994,
        "topic": "固体比热容·合成不确定度、扩展不确定度与报告规范",
        "pages": list(range(4, 17)),
        "url": "https://doi.org/10.6028/NIST.TN.1297",
    },
}

PDF_SPECS = {
    REF_DIR / filename: _PDF_METADATA[filename]
    for filename in PDF_FILENAMES
}

MARKDOWN_TOPICS = {
    "固体比热容可视化实验方案.md": "固体比热容·四路可视化实验设计",
    "固体比热容文献导读.md": "固体比热容·文献导读、模型、修正与不确定度",
    "README.md": "固体比热容·参考资料索引与使用边界",
}


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "固体比热容综合实验")
    topic = base_topic
    lines: list[str] = []
    sections: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        heading = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if heading:
            prior = "\n".join(lines)
            if useful(prior):
                sections.append((topic, clean(prior)))
            heading_text = clean(
                re.sub(r"^\d+(?:\.\d+)*[、.：:]?\s*", "", heading.group(1))
            )
            topic = f"{base_topic}·{heading_text}" if heading_text else base_topic
            lines = [line]
        else:
            lines.append(line)
    trailing = "\n".join(lines)
    if useful(trailing):
        sections.append((topic, clean(trailing)))
    return sections


def import_markdown(path: Path) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    chunk_no = 0
    for topic, section in markdown_sections(path):
        for chunk in split_chunks(section):
            rows.append(
                make_row(path, 1, chunk_no, chunk, topic, "markdown", path.stem, 0)
            )
            chunk_no += 1
    report = {
        "source": path.name,
        "source_path": relative_path(path),
        "source_type": "markdown",
        "chunks": len(rows),
    }
    return rows, report


def build() -> dict:
    markdown_files = [
        SOURCE_DIR / "固体比热容可视化实验方案.md",
        SOURCE_DIR / "固体比热容文献导读.md",
        REF_DIR / "README.md",
    ]
    missing_markdown = [relative_path(path) for path in markdown_files if not path.is_file()]
    missing_pdfs = [relative_path(path) for path in PDF_SPECS if not path.is_file()]
    if missing_markdown or missing_pdfs:
        raise FileNotFoundError(
            "缺少已索引资料：" + "；".join(missing_markdown + missing_pdfs)
        )

    pdftotext = shutil.which("pdftotext")
    pdfinfo = shutil.which("pdfinfo")
    if not pdftotext or not pdfinfo:
        raise RuntimeError("构建 PDF 文献索引需要 pdftotext 与 pdfinfo")

    rows: list[dict] = []
    reports: list[dict] = []
    for path in markdown_files:
        markdown_rows, report = import_markdown(path)
        rows.extend(markdown_rows)
        reports.append(report)
    for path, spec in PDF_SPECS.items():
        pdf_rows, report = extract_pdf(path, spec, pdftotext, pdfinfo)
        rows.extend(pdf_rows)
        reports.append(report)

    required = {
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
    identifiers: set[str] = set()
    for row in rows:
        missing = required - row.keys()
        if missing:
            raise RuntimeError(f"{row.get('source', '?')} 缺少字段：{sorted(missing)}")
        if row["id"] in identifiers:
            raise RuntimeError(f"文本块 ID 冲突：{row['id']}")
        identifiers.add(row["id"])

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "topic": "固体比热容的测定",
        "method": "混合法、冷却修正、电热法与多组数据线性拟合",
        "measured_quantity": "固体比热容 c",
        "routes": ROUTES,
        "documents": len(reports),
        "markdown_documents": len(markdown_files),
        "pdf_documents": len(PDF_SPECS),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/specific_heat.jsonl",
        "main_knowledge_base_modified": False,
        "sources": reports,
    }

    IMPORTED_KB_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        IMPORTED_KB_DIR / f"{OUTPUT_STEM}.jsonl",
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )
    write_json(IMPORTED_KB_DIR / f"{OUTPUT_STEM}.manifest.json", manifest)
    write_json(IMPORTED_KB_DIR / f"{OUTPUT_STEM}.extraction_report.json", reports)
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
