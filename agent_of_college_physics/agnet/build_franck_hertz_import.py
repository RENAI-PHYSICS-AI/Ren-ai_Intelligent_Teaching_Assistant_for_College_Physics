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


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "弗兰克-赫兹实验"
REF_DIR = SOURCE_DIR / "ref"
OUTPUT_STEM = "franck_hertz"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120
ROUTES = ["apparatus", "curve", "analysis", "uncertainty"]

# Only institutionally hosted, publicly downloadable PDFs are copied into the
# repository.  The accompanying literature guide may cite additional classic
# papers by DOI without bundling restricted copies.
PDF_FILENAMES = (
    "Franck_Hertz_1914_Mercury_Collisions.pdf",
    "James_Franck_1926_Nobel_Lecture.pdf",
    "Gustav_Hertz_1926_Nobel_Lecture.pdf",
    "MIT_OCW_Franck_Hertz_Lab_Guide.pdf",
    "NIST_Saloman_2006_Neutral_Mercury.pdf",
    "CODATA_2022_Fundamental_Constants.pdf",
)

_PDF_METADATA = {
    "Franck_Hertz_1914_Mercury_Collisions.pdf": {
        "title": "Über Zusammenstöße zwischen Elektronen und den Molekülen des Quecksilberdampfes und die Ionisierungsspannung desselben",
        "year": 1914,
        "topic": "弗兰克-赫兹·核心原始论文、汞蒸气电子碰撞与 4.9 V 临界电势",
        "pages": None,
        "url": "https://www.dpg-physik.de/presse/presseinformationen/alt/tagungsinfos2014/pdf/franck-hertz-experiment-vh1914.pdf",
    },
    "James_Franck_1926_Nobel_Lecture.pdf": {
        "title": "Transformations of Kinetic Energy of Free Electrons into Excitation Energy of Atoms by Impacts",
        "year": 1926,
        "topic": "弗兰克-赫兹·电子碰撞、激发电势与原始装置",
        "pages": None,
        "url": "https://www.nobelprize.org/uploads/2018/06/franck-lecture.pdf",
    },
    "Gustav_Hertz_1926_Nobel_Lecture.pdf": {
        "title": "Results of the Electron-Impact Tests in the Light of Bohr's Theory of Atoms",
        "year": 1926,
        "topic": "弗兰克-赫兹·电子碰撞、Bohr 能级与实验方法",
        "pages": None,
        "url": "https://www.nobelprize.org/uploads/2018/06/hertz-lecture.pdf",
    },
    "MIT_OCW_Franck_Hertz_Lab_Guide.pdf": {
        "title": "The Franck-Hertz Experiment and the Ramsauer-Townsend Effect: Elastic and Inelastic Scattering of Electrons by Atoms",
        "year": 2016,
        "topic": "弗兰克-赫兹·教学装置、热电子发射、空间电荷、峰谷、接触电势与数据处理",
        "pages": None,
        "url": "https://ocw.mit.edu/courses/8-13-14-experimental-physics-i-ii-junior-lab-fall-2016-spring-2017/afdfff9f8bbe067239af19c8b178a764_MIT8_13-14F16-S17exp7.pdf",
    },
    "NIST_Saloman_2006_Neutral_Mercury.pdf": {
        "title": "Wavelengths, Energy Level Classifications, and Energy Levels for the Spectrum of Neutral Mercury",
        "year": 2006,
        "topic": "弗兰克-赫兹·Hg I 临界能级、253.6 nm 共振线与能级分类",
        "pages": None,
        "url": "https://www.nist.gov/system/files/documents/srd/jpcrd3520061519.pdf",
    },
    "CODATA_2022_Fundamental_Constants.pdf": {
        "title": "CODATA Recommended Values of the Fundamental Physical Constants: 2022",
        "year": 2025,
        "topic": "弗兰克-赫兹·h、c、e 与激发电势—波长换算",
        # One-based PDF pages 44–51 contain the abbreviated constants table,
        # detailed h/c/e values and the energy-equivalence tables used here.
        "pages": list(range(44, 52)),
        "url": "https://physics.nist.gov/cuu/pdf/RevModPhys.97.025002.pdf",
    },
}

PDF_SPECS = {REF_DIR / name: _PDF_METADATA[name] for name in PDF_FILENAMES}

MARKDOWN_TOPICS = {
    "弗兰克-赫兹可视化实验方案.md": "弗兰克-赫兹·四路可视化实验设计",
    "弗兰克-赫兹文献导读.md": "弗兰克-赫兹·文献导读、能级、碰撞与不确定度",
    "README.md": "弗兰克-赫兹·参考资料索引与使用边界",
}


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "弗兰克-赫兹综合实验")
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
        SOURCE_DIR / "弗兰克-赫兹可视化实验方案.md",
        SOURCE_DIR / "弗兰克-赫兹文献导读.md",
        REF_DIR / "README.md",
    ]
    missing_markdown = [relative_path(path) for path in markdown_files if not path.is_file()]
    missing_pdfs = [relative_path(path) for path in PDF_SPECS if not path.is_file()]
    if missing_markdown or missing_pdfs:
        raise FileNotFoundError(
            "缺少弗兰克-赫兹已索引资料："
            + "；".join(missing_markdown + missing_pdfs)
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
        "topic": "弗兰克-赫兹实验",
        "method": "电子碰撞、周期性峰谷、逐差与线性拟合",
        "measured_quantity": "第一激发电势 U_1 与能级差 E_1=eU_1",
        "routes": ROUTES,
        "documents": len(reports),
        "markdown_documents": len(markdown_files),
        "pdf_documents": len(PDF_SPECS),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/franck_hertz.jsonl",
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
