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


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "霍尔效应测磁场分布"
REF_DIR = SOURCE_DIR / "ref"
OUTPUT_STEM = "hall_effect"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120
ROUTES = ["calibration", "scan", "fit", "uncertainty"]

PDF_FILENAMES = (
    "Hall_1879_New_Action.pdf",
    "Hall_1880_Permanent_Current.pdf",
    "NBS_SP400_4_Semiconductor_Measurement.pdf",
    "Boero_2011_Hall_Probes_Magnetometry.pdf",
    "NMT_Hall_Effect_Lab.pdf",
    "Gerken_2020_Traceable_Scanning_Hall.pdf",
    "JCGM_100_2008_GUM.pdf",
    "NIST_TN1297_Uncertainty.pdf",
)

_PDF_METADATA = {
    "Hall_1879_New_Action.pdf": {
        "title": "On a New Action of the Magnet on Electric Currents",
        "year": 1879,
        "topic": "霍尔效应测磁场分布·原始发现、横向电势与磁场反转",
        "pages": None,
        "url": "https://doi.org/10.2307/2369245",
    },
    "Hall_1880_Permanent_Current.pdf": {
        "title": "On the New Action of Magnetism on a Permanent Electric Current",
        "year": 1880,
        "topic": "霍尔效应测磁场分布·多材料、换向测量与博士论文",
        "pages": None,
        "url": "https://doi.org/10.2475/ajs.s3-20.117.161",
    },
    "NBS_SP400_4_Semiconductor_Measurement.pdf": {
        "title": "Semiconductor Measurement Technology, NBS Special Publication 400-4",
        "year": 1974,
        "topic": "霍尔效应测磁场分布·正反磁场、剩磁与自动 Hall 测量",
        "pages": list(range(25, 28)),
        "url": "https://doi.org/10.6028/NBS.SP.400-4",
    },
    "Boero_2011_Hall_Probes_Magnetometry.pdf": {
        "title": "Hall Probes: Physics and Application to Magnetometry",
        "year": 2011,
        "topic": "霍尔效应测磁场分布·探头校准、偏置、温度与磁强计",
        "pages": None,
        "url": "https://arxiv.org/abs/1103.1271",
    },
    "NMT_Hall_Effect_Lab.pdf": {
        "title": "Hall Effect Experiment",
        "year": 2011,
        "topic": "霍尔效应测磁场分布·大学物理实验装置与磁场研究",
        "pages": None,
        "url": "https://kestrel.nmt.edu/~krm/TEACHING/srlab/manuals/hall_new.pdf",
    },
    "Gerken_2020_Traceable_Scanning_Hall.pdf": {
        "title": "Traceably Calibrated Scanning Hall Probe Microscopy at Room Temperature",
        "year": 2020,
        "topic": "霍尔效应测磁场分布·可追溯扫描、定位与不确定度预算",
        "pages": None,
        "url": "https://doi.org/10.5194/jsss-9-391-2020",
    },
    "JCGM_100_2008_GUM.pdf": {
        "title": "Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement",
        "year": 2008,
        "topic": "霍尔效应测磁场分布·A 类与 B 类不确定度、传播律和结果表达",
        "pages": list(range(17, 41)),
        "url": "https://doi.org/10.59161/JCGM100-2008E",
    },
    "NIST_TN1297_Uncertainty.pdf": {
        "title": "Guidelines for Evaluating and Expressing the Uncertainty of NIST Measurement Results",
        "year": 1994,
        "topic": "霍尔效应测磁场分布·合成不确定度、扩展不确定度与报告",
        "pages": list(range(4, 17)),
        "url": "https://doi.org/10.6028/NIST.TN.1297",
    },
}

PDF_SPECS = {REF_DIR / filename: _PDF_METADATA[filename] for filename in PDF_FILENAMES}

MARKDOWN_TOPICS = {
    "霍尔效应测磁场分布可视化实验方案.md": "霍尔效应测磁场分布·四路可视化实验设计",
    "霍尔效应测磁场分布文献导读.md": "霍尔效应测磁场分布·文献导读、探头校准与不确定度",
    "README.md": "霍尔效应测磁场分布·参考资料索引与版权边界",
}


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "霍尔效应测磁场分布综合实验")
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
        SOURCE_DIR / "霍尔效应测磁场分布可视化实验方案.md",
        SOURCE_DIR / "霍尔效应测磁场分布文献导读.md",
        REF_DIR / "README.md",
    ]
    source_manifest = REF_DIR / "source_manifest.json"
    missing_markdown = [relative_path(path) for path in markdown_files if not path.is_file()]
    missing_pdfs = [relative_path(path) for path in PDF_SPECS if not path.is_file()]
    if not source_manifest.is_file():
        missing_markdown.append(relative_path(source_manifest))
    if missing_markdown or missing_pdfs:
        raise FileNotFoundError("缺少已索引资料：" + "；".join(missing_markdown + missing_pdfs))

    source_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
    if int(source_payload.get("core_reference_count", 0)) < 10:
        raise RuntimeError("霍尔效应文献清单少于 10 项核心资料")

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
        "topic": "霍尔效应测磁场分布",
        "method": "霍尔电压标定、有限长螺线管轴向扫描、自由截距拟合与 GUM 不确定度",
        "measured_quantity": "指定方向的磁感应强度分量 B_n",
        "routes": ROUTES,
        "core_references": int(source_payload["core_reference_count"]),
        "documents": len(reports),
        "markdown_documents": len(markdown_files),
        "pdf_documents": len(PDF_SPECS),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/hall_effect.jsonl",
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
