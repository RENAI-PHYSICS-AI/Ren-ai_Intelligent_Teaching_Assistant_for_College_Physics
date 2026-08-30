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


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "温度传感器特性的测定"
REF_DIR = SOURCE_DIR / "ref"
SOURCE_CATALOG_PATH = SOURCE_DIR / "sources.json"
SOURCE_MANIFEST_PATH = SOURCE_DIR / "manifest.json"
OUTPUT_STEM = "temperature_sensor"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120
ROUTES = ["calibration", "response", "bridge", "uncertainty"]

PDF_FILENAMES = (
    "NIST_MONO_175_Thermocouples.pdf",
    "NIST_SP250_81_SPRT_Calibration.pdf",
    "NIST_IR6225_IPRT_Automated_Calibration.pdf",
    "BIPM_CCT_Guide_IPRT.pdf",
    "BIPM_CCT_Thermocouple_Part1.pdf",
    "JCGM_100_2008_GUM.pdf",
)

_PDF_METADATA = {
    "NIST_MONO_175_Thermocouples.pdf": {
        "title": "Temperature-Electromotive Force Reference Functions and Tables for the Letter-Designated Thermocouple Types Based on the ITS-90",
        "year": 1993,
        "topic": "温度传感器·热电偶参考函数、参考端与 Type K 表格",
        "pages": list(range(13, 22)) + list(range(165, 176)),
        "url": "https://doi.org/10.6028/NIST.MONO.175",
    },
    "NIST_SP250_81_SPRT_Calibration.pdf": {
        "title": "Standard Platinum Resistance Thermometer Calibrations from the Ar TP to the Ag FP",
        "year": 2008,
        "topic": "温度传感器·标准铂电阻固定点校准、读出与不确定度",
        "pages": list(range(8, 34)),
        "url": "https://doi.org/10.6028/NIST.SP.250-81",
    },
    "NIST_IR6225_IPRT_Automated_Calibration.pdf": {
        "title": "A New NIST Automated Calibration System for Industrial-Grade Platinum Resistance Thermometers",
        "year": 1998,
        "topic": "温度传感器·工业 Pt100 比较温槽、电桥和自动校准",
        "pages": None,
        "url": "https://doi.org/10.6028/NIST.IR.6225",
    },
    "BIPM_CCT_Guide_IPRT.pdf": {
        "title": "Guide to Secondary Thermometry: Industrial Platinum Resistance Thermometers",
        "year": 2021,
        "topic": "温度传感器·IPRT 结构、读出、滞后、自热、校准和不确定度",
        "pages": list(range(7, 33)),
        "url": "https://www.bipm.org/documents/20126/41773843/BIPM_CCT_Guide_to_IPRTs.pdf",
    },
    "BIPM_CCT_Thermocouple_Part1.pdf": {
        "title": "Guide to Secondary Thermometry: Thermocouple Thermometry, Part 1 - General Usage",
        "year": 2021,
        "topic": "温度传感器·热电偶参考端、非均匀性、补偿导线和安装",
        "pages": list(range(6, 31)),
        "url": "https://www.bipm.org/documents/20126/41773843/Thermocouple_Thermometry_Part1.pdf",
    },
    "JCGM_100_2008_GUM.pdf": {
        "title": "Evaluation of Measurement Data - Guide to the Expression of Uncertainty in Measurement",
        "year": 2008,
        "topic": "温度传感器·A/B 类不确定度、灵敏系数、合成与扩展不确定度",
        "pages": list(range(17, 41)),
        "url": "https://doi.org/10.59161/JCGM100-2008E",
    },
}

PDF_SPECS = {REF_DIR / name: _PDF_METADATA[name] for name in PDF_FILENAMES}

MARKDOWN_TOPICS = {
    "温度传感器可视化实验方案.md": "温度传感器·四路可视化实验设计",
    "温度传感器文献导读.md": "温度传感器·文献导读、温标、标定与计量",
    "README.md": "温度传感器·十篇经典与权威参考索引",
}


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "温度传感器综合实验")
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
                f"温度传感器·核心文献题录·{item['topic']}",
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
        SOURCE_DIR / "温度传感器可视化实验方案.md",
        SOURCE_DIR / "温度传感器文献导读.md",
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
        "topic": "温度传感器特性的测定",
        "method": "Pt100 静态标定、阶跃响应、电桥读出、升降温滞后与不确定度评定",
        "measured_quantity": "灵敏度 S、时间常数 τ、滞后和温度测量不确定度",
        "routes": ROUTES,
        "core_references": len(catalog),
        "documents": len(reports),
        "markdown_documents": len(markdown_files),
        "catalog_documents": 1,
        "pdf_documents": len(PDF_SPECS),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/temperature_sensor.jsonl",
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
