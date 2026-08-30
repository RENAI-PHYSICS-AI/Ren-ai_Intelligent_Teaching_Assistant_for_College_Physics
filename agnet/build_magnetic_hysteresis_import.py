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


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "铁磁滞回线测定与观察"
REF_DIR = SOURCE_DIR / "ref"
OUTPUT_STEM = "magnetic_hysteresis"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120
ROUTES = ["loop", "apparatus", "demagnetization", "fit"]

PDF_SPECS = {
    REF_DIR / "NBS_Monograph_47_Magnetic_Measurement.pdf": {
        "title": "Basic Magnetic Quantities and the Measurement of the Magnetic Properties of Materials",
        "year": 1962,
        "topic": "铁磁滞回线·磁学量、环形样品、磁导计与矫顽力测量",
        "pages": list(range(1, 36)),
        "url": "https://nvlpubs.nist.gov/nistpubs/Legacy/MONO/nbsmonograph47.pdf",
    },
    REF_DIR / "Sanford_Bennett_1935_Fahy_Permeameter.pdf": {
        "title": "Determination of magnetic hysteresis with the Fahy Simplex permeameter",
        "year": 1935,
        "topic": "铁磁滞回线·逐点回线、H线圈、磁导计与系统误差",
        "pages": None,
        "url": "https://nvlpubs.nist.gov/nistpubs/jres/15/jresv15n5p517_A1b.pdf",
    },
    REF_DIR / "JCGM_100_2008_GUM.pdf": {
        "title": "Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement",
        "year": 2008,
        "topic": "铁磁滞回线·输入量模型、相关性与不确定度传播",
        "pages": list(range(17, 41)),
        "url": "https://doi.org/10.59161/JCGM100-2008E",
    },
    REF_DIR / "NIST_TN1297_Uncertainty.pdf": {
        "title": "Guidelines for Evaluating and Expressing the Uncertainty of NIST Measurement Results",
        "year": 1994,
        "topic": "铁磁滞回线·合成与扩展不确定度及结果报告",
        "pages": list(range(4, 17)),
        "url": "https://doi.org/10.6028/NIST.TN.1297",
    },
}

MARKDOWN_TOPICS = {
    "铁磁滞回线文献导读.md": "铁磁滞回线·文献导读、测量原理与模型边界",
    "铁磁滞回线可视化实验方案.md": "铁磁滞回线·四路可视化实验设计",
    "README.md": "铁磁滞回线·十二项经典文献与标准索引",
}


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "铁磁滞回线综合实验")
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
            rows.append(make_row(path, 1, chunk_no, chunk, topic, "markdown", path.stem, 0))
            chunk_no += 1
    return rows, {
        "source": path.name,
        "source_path": relative_path(path),
        "source_type": "markdown",
        "chunks": len(rows),
    }


def build() -> dict:
    markdown_files = [
        SOURCE_DIR / "铁磁滞回线文献导读.md",
        SOURCE_DIR / "铁磁滞回线可视化实验方案.md",
        REF_DIR / "README.md",
    ]
    missing = [relative_path(path) for path in [*markdown_files, *PDF_SPECS] if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少已索引资料：" + "；".join(missing))

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

    identifiers: set[str] = set()
    required = {"id", "source", "source_type", "page", "chunk", "text", "title", "year", "language", "topic", "locator"}
    for row in rows:
        absent = required - row.keys()
        if absent:
            raise RuntimeError(f"{row.get('source', '?')} 缺少字段：{sorted(absent)}")
        if row["id"] in identifiers:
            raise RuntimeError(f"文本块 ID 冲突：{row['id']}")
        identifiers.add(row["id"])

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "topic": "铁磁滞回线测定与观察",
        "method": "环形样品示波器法、RC积分、交流退磁与回线损耗分析",
        "measured_quantity": "B-H回线、矫顽力Hc、剩磁Br和磁滞损耗",
        "routes": ROUTES,
        "documents": len(reports),
        "annotated_references": 12,
        "markdown_documents": len(markdown_files),
        "pdf_documents": len(PDF_SPECS),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/magnetic_hysteresis.jsonl",
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
