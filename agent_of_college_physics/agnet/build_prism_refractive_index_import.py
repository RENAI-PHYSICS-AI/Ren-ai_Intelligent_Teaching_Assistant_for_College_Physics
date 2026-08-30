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


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "三棱镜折射率测定"
REF_DIR = SOURCE_DIR / "ref"
SOURCE_CATALOG_PATH = SOURCE_DIR / "sources.json"
SOURCE_MANIFEST_PATH = SOURCE_DIR / "manifest.json"
OUTPUT_STEM = "prism_refractive_index"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120
ROUTES = ["collimation", "apex", "minimum-deviation", "dispersion"]

PDF_FILENAMES = (
    "SCHOTT_TIE29_Refractive_Index_Dispersion.pdf",
    "SCHOTT_Optical_Glass_Pocket_Catalog.pdf",
    "UCI_Faraday_Prism_Refractometry.pdf",
    "CSM_Prism_Spectrometer_Lab06.pdf",
    "Rochester_Student_Spectrometer_Experiment14.pdf",
    "JCGM_100_2008_GUM.pdf",
)

_PDF_METADATA = {
    "SCHOTT_TIE29_Refractive_Index_Dispersion.pdf": {
        "title": "TIE-29: Refractive Index and Dispersion",
        "year": 2023,
        "topic": "三棱镜折射率·折射率、标准谱线、Sellmeier 色散、Abbe 数与最小偏向法",
        "pages": list(range(1, 13)),
        "url": "https://media.schott.com/api/public/content/aaa572afd854434fb7b3faa4bc46103f?download=true&v=06988a0a",
    },
    "SCHOTT_Optical_Glass_Pocket_Catalog.pdf": {
        "title": "Optical Glass Pocket Catalog",
        "year": 2025,
        "topic": "三棱镜折射率·光学玻璃谱线数据、Cauchy/Sellmeier 系数与材料对照",
        "pages": list(range(5, 13)) + list(range(64, 73)),
        "url": "https://media.schott.com/api/public/content/b37dbd8fa7e64662b2d0ae523ae56238?download=true&v=97f67105",
    },
    "UCI_Faraday_Prism_Refractometry.pdf": {
        "title": "Faraday Rotation: Prism Angle and Refractive Index Measurements",
        "year": 2026,
        "topic": "三棱镜折射率·Gaussian 目镜、自准直顶角与双向最小偏向测量",
        "pages": list(range(8, 13)),
        "url": "https://www.physics.uci.edu/~advanlab/faraday.pdf",
    },
    "CSM_Prism_Spectrometer_Lab06.pdf": {
        "title": "Physics 270 Lab 6: Prism Spectrometer",
        "year": 2008,
        "topic": "三棱镜折射率·游标、跨零、谱线转向点和 Cauchy 最小二乘拟合",
        "pages": list(range(1, 7)),
        "url": "https://collegeofsanmateo.edu/physics/docs/physics270/lab06.pdf",
    },
    "Rochester_Student_Spectrometer_Experiment14.pdf": {
        "title": "Experiment 14: Student Spectrometer",
        "year": 2021,
        "topic": "三棱镜折射率·分光计调焦、消视差和最小偏向角操作",
        "pages": list(range(1, 6)) + list(range(15, 18)),
        "url": "https://www.pas.rochester.edu/~physlabs/manuals/Experiment14.pdf",
    },
    "JCGM_100_2008_GUM.pdf": {
        "title": "Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement",
        "year": 2008,
        "topic": "三棱镜折射率·角度输入量、灵敏系数、合成与扩展不确定度",
        "pages": list(range(17, 41)),
        "url": "https://doi.org/10.59161/JCGM100-2008E",
    },
}

PDF_SPECS = {REF_DIR / name: _PDF_METADATA[name] for name in PDF_FILENAMES}

MARKDOWN_TOPICS = {
    "三棱镜折射率可视化实验方案.md": "三棱镜折射率·四路可视化实验设计",
    "三棱镜折射率文献导读.md": "三棱镜折射率·经典文献、标准与计量导读",
    "README.md": "三棱镜折射率·十篇经典与权威参考索引",
}


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "三棱镜折射率综合实验")
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
        local_file = item["local_file"]
        if local_file is not None and not (SOURCE_DIR / str(local_file)).is_file():
            raise FileNotFoundError(f"{item['id']} 的本地文件不存在：{local_file}")
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
                f"三棱镜折射率·核心文献题录·{item['topic']}",
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
        SOURCE_DIR / "三棱镜折射率可视化实验方案.md",
        SOURCE_DIR / "三棱镜折射率文献导读.md",
        REF_DIR / "README.md",
    ]
    required_files = markdown_files + [SOURCE_CATALOG_PATH, SOURCE_MANIFEST_PATH, *PDF_SPECS]
    missing = [relative_path(path) for path in required_files if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少已索引资料：" + "；".join(missing))

    source_manifest = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    if source_manifest.get("routes") != ROUTES:
        raise RuntimeError("manifest.json 路由与可视化实验不一致")
    if source_manifest.get("core_reference_count") != 10:
        raise RuntimeError("manifest.json 核心文献数必须为 10")
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
        "topic": "三棱镜折射率测定",
        "method": "分光计调节、反射法测顶角、最小偏向角法测折射率、多谱线色散拟合与不确定度传播",
        "measured_quantity": "顶角 A、最小偏向角 δmin、折射率 n(λ)、Abbe 数 νd 与 U(n)",
        "routes": ROUTES,
        "core_references": len(catalog),
        "documents": len(reports),
        "markdown_documents": len(markdown_files),
        "catalog_documents": 1,
        "pdf_documents": len(PDF_SPECS),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/prism_refractive_index.jsonl",
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
