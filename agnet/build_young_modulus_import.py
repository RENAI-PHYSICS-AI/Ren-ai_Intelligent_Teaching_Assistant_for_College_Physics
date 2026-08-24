from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from config import IMPORTED_KB_DIR, PROJECT_ROOT


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "杨氏模量测定"
REF_DIR = SOURCE_DIR / "ref"
OUTPUT_STEM = "young_modulus"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120

PDF_SPECS = {
    REF_DIR / "Harbin_Engineering_University_Wire_Youngs_Modulus_Optical_Lever.pdf": {
        "title": "拉伸法测量金属丝的杨氏模量",
        "year": 2023,
        "topic": "杨氏模量·静态拉伸、光杠杆与逐差法",
        "pages": None,
        "url": "https://pec.hrbeu.edu.cn/_upload/article/files/3b/db/205fd41048199668119d23837cde/2519c877-3e53-44df-80e4-df0c25eb21f7.pdf",
    },
    REF_DIR / "Shandong_University_Metal_Wire_Youngs_Modulus.pdf": {
        "title": "金属丝杨氏弹性模量的测定",
        "year": 0,
        "topic": "杨氏模量·三脚光杠杆、望远镜标尺与误差分析",
        "pages": None,
        "url": "https://www.phylab.sdu.edu.cn/shiyansanjinshusiyangshidanxingmoliangdeceding-.pdf",
    },
    REF_DIR / "York_College_CUNY_Lab10_Youngs_Modulus.pdf": {
        "title": "Experiment 10 — Young's Modulus",
        "year": 2019,
        "topic": "杨氏模量·加载卸载、平均读数与跨级差分",
        "pages": None,
        "url": "https://www.york.cuny.edu/earth-physical-sciences/physics-lab-manuals/physics-i/lab-10/@@download/file",
    },
    REF_DIR / "McMurry_University_Lab5_1_Youngs_Modulus.pdf": {
        "title": "5.1 Young's Modulus",
        "year": 0,
        "topic": "杨氏模量·悬丝加载、激光反射与应力应变",
        "pages": None,
        "url": "https://mail.mcm.edu/~bykov.tikhon/phys2510/lab/Lab5-1.pdf",
    },
    REF_DIR / "Experimental_Science_Technology_2016_Length_Instruments_Youngs_Modulus.pdf": {
        "title": "杨氏模量实验中长度测量仪器的选配",
        "year": 2016,
        "topic": "杨氏模量·量具选配与不确定度贡献",
        "pages": None,
        "url": "https://www.sy.uestc.edu.cn/cn/article/pdf/preview/10.3969/j.issn.1672-4550.2016.01.008.pdf",
    },
    REF_DIR / "JCGM_100_2008_GUM.pdf": {
        "title": "JCGM 100:2008 — Guide to the Expression of Uncertainty in Measurement",
        "year": 2008,
        "topic": "测量不确定度·模型、标准不确定度与传播",
        "pages": list(range(17, 41)),
        "url": "https://www.bipm.org/documents/20126/2071204/JCGM1002008E.pdf/cb0ef43f-baa5-11cf-3f85-4dcd86f77bd6",
    },
    REF_DIR / "NIST_TN1297_Uncertainty.pdf": {
        "title": "NIST Technical Note 1297 — Measurement Uncertainty",
        "year": 1994,
        "topic": "测量不确定度·A类、B类、合成与扩展不确定度",
        "pages": list(range(4, 17)),
        "url": "https://nvlpubs.nist.gov/nistpubs/Legacy/TN/nbstechnicalnote1297.pdf",
    },
}

MARKDOWN_TOPICS = {
    "杨氏模量可视化实验方案.md": "杨氏模量·四路可视化实验设计",
    "杨氏模量文献导读.md": "杨氏模量·文献导读、公式与误差",
    "README.md": "杨氏模量·参考资料索引与使用边界",
}


def clean(text: str) -> str:
    text = text.replace("\x00", " ").replace("\ufeff", " ").replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def useful(text: str, minimum: int = 35) -> bool:
    compact = re.sub(r"\s+", "", text)
    if len(compact) < minimum:
        return False
    printable = sum(character.isprintable() for character in compact)
    return printable / max(1, len(compact)) > 0.92


def split_chunks(text: str):
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            pivot = max(
                text.rfind("\n", start, end),
                text.rfind("。", start, end),
                text.rfind("；", start, end),
                text.rfind(". ", start, end),
            )
            if pivot > start + CHUNK_SIZE // 2:
                end = pivot + 1
        chunk = clean(text[start:end])
        if useful(chunk):
            yield chunk
        if end >= len(text):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)


def stable_id(source: str, page: int, chunk: int, text: str) -> str:
    payload = f"{source}\0{page}\0{chunk}\0{text}".encode("utf-8", errors="ignore")
    return hashlib.sha256(payload).hexdigest()[:16]


def relative_path(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_language(path: Path, text: str = "") -> str:
    if path.suffix.lower() == ".md":
        return "zh"
    compact = re.sub(r"\s+", "", text[:3000])
    chinese = len(re.findall(r"[\u3400-\u9fff]", compact))
    return "zh" if chinese > max(20, len(compact) // 5) else "en"


def make_row(
    path: Path,
    page: int,
    chunk_no: int,
    text: str,
    topic: str,
    source_type: str,
    title: str,
    year: int,
) -> dict:
    locator = f"PDF第{page}页" if source_type == "pdf" else topic
    return {
        "id": stable_id(path.name, page, chunk_no, text),
        "source": path.name,
        "source_type": source_type,
        "page": page,
        "chunk": chunk_no,
        "text": text,
        "title": title,
        "year": year,
        "language": source_language(path, text),
        "topic": topic,
        "locator": locator,
    }


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "杨氏模量综合实验")
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


def run_tool(arguments: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(arguments, capture_output=True, check=False, timeout=timeout)


def pdf_page_count(pdfinfo: str, path: Path) -> int:
    result = run_tool([pdfinfo, str(path)], timeout=60)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{path.name}: pdfinfo failed: {detail}")
    output = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r"^Pages:\s+(\d+)", output, re.MULTILINE)
    if not match:
        raise RuntimeError(f"{path.name}: pdfinfo 未返回页数")
    return int(match.group(1))


def extract_pdf(
    path: Path,
    spec: dict,
    pdftotext: str,
    pdfinfo: str,
) -> tuple[list[dict], dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise RuntimeError(f"{path.name}: 文件签名不是 %PDF-")
    total_pages = pdf_page_count(pdfinfo, path)
    requested = spec["pages"]
    selected_pages = (
        list(range(1, total_pages + 1))
        if requested is None
        else [page for page in requested if 1 <= page <= total_pages]
    )
    if not selected_pages:
        raise RuntimeError(f"{path.name}: 没有有效的选定页")

    rows: list[dict] = []
    empty_pages: list[int] = []
    for page in selected_pages:
        result = run_tool(
            [
                pdftotext,
                "-f",
                str(page),
                "-l",
                str(page),
                "-layout",
                "-enc",
                "UTF-8",
                str(path),
                "-",
            ]
        )
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"{path.name} 第 {page} 页提取失败: {detail}")
        page_text = clean(result.stdout.decode("utf-8", errors="replace"))
        if not useful(page_text):
            empty_pages.append(page)
            continue
        for chunk_no, chunk in enumerate(split_chunks(page_text)):
            rows.append(
                make_row(
                    path,
                    page,
                    chunk_no,
                    chunk,
                    spec["topic"],
                    "pdf",
                    spec["title"],
                    int(spec["year"]),
                )
            )
    if not rows:
        raise RuntimeError(f"{path.name}: 选定页未提取到可检索文字，请先 OCR")

    report = {
        "source": path.name,
        "source_path": relative_path(path),
        "source_type": "pdf",
        "url": spec["url"],
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "pdf_signature": "%PDF-",
        "pages": total_pages,
        "selected_pages": selected_pages,
        "empty_pages": empty_pages,
        "text_layer_pages": len(selected_pages) - len(empty_pages),
        "chunks": len(rows),
        "ocr_recommended": bool(empty_pages),
    }
    return rows, report


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_json(path: Path, value) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def build() -> dict:
    markdown_files = sorted(SOURCE_DIR.glob("*.md")) + [REF_DIR / "README.md"]
    missing_markdown = [relative_path(path) for path in markdown_files if not path.is_file()]
    missing_pdfs = [relative_path(path) for path in PDF_SPECS if not path.is_file()]
    if missing_markdown or missing_pdfs:
        missing = missing_markdown + missing_pdfs
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
        "topic": "杨氏模量测定",
        "method": "静态拉伸法（光杠杆）",
        "measured_quantity": "金属丝杨氏模量 E",
        "routes": ["principle", "loading", "fit", "uncertainty"],
        "documents": len(reports),
        "markdown_documents": len(markdown_files),
        "pdf_documents": len(PDF_SPECS),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/young_modulus.jsonl",
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
