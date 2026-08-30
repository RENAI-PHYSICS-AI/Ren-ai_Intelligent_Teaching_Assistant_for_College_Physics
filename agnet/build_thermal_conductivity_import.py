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


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "固体热传导系数测定"
REF_DIR = SOURCE_DIR / "ref"
SOURCE_CATALOG_PATH = SOURCE_DIR / "sources.json"
SOURCE_MANIFEST_PATH = SOURCE_DIR / "manifest.json"
OUTPUT_STEM = "thermal_conductivity"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120
ROUTES = ["steady-state", "cooling", "fit", "uncertainty"]

PDF_FILENAMES = (
    "Fourier_1878_Analytical_Theory_of_Heat.pdf",
    "NBS_IR_88_3089_Guarded_Hot_Plate.pdf",
    "NIST_JRES_123_001_Transient_GHP.pdf",
    "NIST_TN_1606_GHP_Uncertainty.pdf",
    "JCGM_100_2008_GUM.pdf",
)

_PDF_METADATA = {
    "Fourier_1878_Analytical_Theory_of_Heat.pdf": {
        "title": "The Analytical Theory of Heat",
        "year": 1878,
        "topic": "固体热传导·傅里叶定律、温度梯度与导热方程",
        "pages": list(range(1, 45)) + list(range(67, 93)),
        "url": "https://archive.org/details/analyticaltheory00fourrich",
    },
    "NBS_IR_88_3089_Guarded_Hot_Plate.pdf": {
        "title": "An Automated High-Temperature Guarded-Hot-Plate Apparatus for Measuring Apparent Thermal Conductivity",
        "year": 1988,
        "topic": "固体热传导·防护热板、稳态控制与功率测量",
        "pages": None,
        "url": "https://doi.org/10.6028/NBS.IR.88-3089",
    },
    "NIST_JRES_123_001_Transient_GHP.pdf": {
        "title": "Transient Thermal Response of a Guarded-Hot-Plate Apparatus for Operation Over an Extended Temperature Range",
        "year": 2018,
        "topic": "固体热传导·瞬态响应、时间常数与稳态判据",
        "pages": None,
        "url": "https://doi.org/10.6028/jres.123.001",
    },
    "NIST_TN_1606_GHP_Uncertainty.pdf": {
        "title": "Assessment of Uncertainties for the NIST 1016 mm Guarded-Hot-Plate Apparatus: Extended Analysis for Low-Density Fibrous-Glass Thermal Insulation",
        "year": 2009,
        "topic": "固体热传导·测量模型、修正与不确定度预算",
        "pages": None,
        "url": "https://doi.org/10.6028/NIST.TN.1606",
    },
    "JCGM_100_2008_GUM.pdf": {
        "title": "Evaluation of Measurement Data - Guide to the Expression of Uncertainty in Measurement",
        "year": 2008,
        "topic": "固体热传导·灵敏系数、合成与扩展不确定度",
        "pages": list(range(17, 41)),
        "url": "https://doi.org/10.59161/JCGM100-2008E",
    },
}

PDF_SPECS = {REF_DIR / name: _PDF_METADATA[name] for name in PDF_FILENAMES}

MARKDOWN_TOPICS = {
    "固体热传导系数可视化实验方案.md": "固体热传导·四路可视化实验设计",
    "固体热传导系数文献导读.md": "固体热传导·傅里叶定律、稳态法、修正与计量",
    "README.md": "固体热传导·十篇经典与权威参考索引",
}


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "固体热传导综合实验")
    topic = base_topic
    lines: list[str] = []
    sections: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        heading = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if heading:
            prior = "\n".join(lines)
            if useful(prior):
                sections.append((topic, clean(prior)))
            heading_text = clean(re.sub(r"^\d+(?:\.\d+)*[、.：:]?\s*", "", heading.group(1)))
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


def load_source_catalog() -> list[dict]:
    payload = json.loads(SOURCE_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or len(payload) != 10:
        raise RuntimeError("sources.json 必须包含恰好 10 条核心文献")
    required = {"id", "authors", "year", "title", "publisher", "type", "topic", "url", "local_file"}
    identifiers: set[str] = set()
    for index, item in enumerate(payload, 1):
        if not isinstance(item, dict) or set(item) != required:
            raise RuntimeError(f"sources.json 第 {index} 条字段不符合契约")
        if item["id"] in identifiers:
            raise RuntimeError(f"文献 ID 重复：{item['id']}")
        identifiers.add(item["id"])
        if not str(item["url"]).startswith("https://"):
            raise RuntimeError(f"{item['id']} 缺少 HTTPS 权威链接")
    return payload


def import_source_catalog(items: list[dict]) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    for index, item in enumerate(items):
        authors = "；".join(str(author) for author in item["authors"])
        local = item["local_file"] or "仅题录/官方链接，未复制受限全文"
        text = clean(
            f"文献 ID：{item['id']}\n题名：{item['title']}\n作者/机构：{authors}\n"
            f"出版者：{item['publisher']}\n年份：{item['year']}\n类型：{item['type']}\n"
            f"主题：{item['topic']}\n权威链接：{item['url']}\n本地文件：{local}"
        )
        rows.append(
            make_row(
                SOURCE_CATALOG_PATH,
                1,
                index,
                text,
                f"固体热传导·核心文献题录·{item['topic']}",
                "reference_metadata",
                str(item["title"]),
                int(item["year"]),
            )
        )
    return rows, {
        "source": SOURCE_CATALOG_PATH.name,
        "source_path": relative_path(SOURCE_CATALOG_PATH),
        "source_type": "reference_metadata",
        "references": len(items),
        "chunks": len(rows),
    }


def build() -> dict:
    markdown_files = [
        SOURCE_DIR / "固体热传导系数可视化实验方案.md",
        SOURCE_DIR / "固体热传导系数文献导读.md",
        REF_DIR / "README.md",
    ]
    required_files = markdown_files + [SOURCE_CATALOG_PATH, SOURCE_MANIFEST_PATH, *PDF_SPECS]
    missing = [relative_path(path) for path in required_files if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少已索引资料：" + "；".join(missing))

    source_manifest = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    if source_manifest.get("routes") != ROUTES:
        raise RuntimeError("manifest.json 路由与可视化实验不一致")
    catalog = load_source_catalog()
    pdftotext, pdfinfo = shutil.which("pdftotext"), shutil.which("pdfinfo")
    if not pdftotext or not pdfinfo:
        raise RuntimeError("构建 PDF 文献索引需要 pdftotext 与 pdfinfo")

    rows: list[dict] = []
    reports: list[dict] = []
    for path in markdown_files:
        imported, report = import_markdown(path)
        rows.extend(imported)
        reports.append(report)
    catalog_rows, catalog_report = import_source_catalog(catalog)
    rows.extend(catalog_rows)
    reports.append(catalog_report)
    for path, spec in PDF_SPECS.items():
        pdf_rows, report = extract_pdf(path, spec, pdftotext, pdfinfo)
        rows.extend(pdf_rows)
        reports.append(report)

    required = {"id", "source", "source_type", "page", "chunk", "text", "title", "year", "language", "topic", "locator"}
    identifiers: set[str] = set()
    for row in rows:
        missing_fields = required - row.keys()
        if missing_fields:
            raise RuntimeError(f"{row.get('source', '?')} 缺少字段：{sorted(missing_fields)}")
        if row["id"] in identifiers:
            raise RuntimeError(f"文本块 ID 冲突：{row['id']}")
        identifiers.add(row["id"])

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "topic": "固体热传导系数测定",
        "method": "稳态圆盘法、良导体棒法、冷却曲线修正、线性拟合与不确定度评定",
        "measured_quantity": "热传导系数 k、温度梯度、热损失修正和扩展不确定度",
        "routes": ROUTES,
        "core_references": len(catalog),
        "documents": len(reports),
        "markdown_documents": len(markdown_files),
        "catalog_documents": 1,
        "pdf_documents": len(PDF_SPECS),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/thermal_conductivity.jsonl",
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
