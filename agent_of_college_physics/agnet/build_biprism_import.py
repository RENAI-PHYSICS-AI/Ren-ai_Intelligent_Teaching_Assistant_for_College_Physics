from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from config import IMPORTED_KB_DIR, PROJECT_ROOT


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "双棱镜干涉测波长"
REF_DIR = SOURCE_DIR / "ref"
OUTPUT_STEM = "biprism"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120

TOPIC_BY_SOURCE = {
    "双棱镜干涉测波长各实验详细说明.md": "双棱镜·实验原理、测量流程与误差",
    "双棱镜干涉测波长可视化演示题目报告.md": "双棱镜·四页可视化实验设计",
    "README.md": "双棱镜·参考资料索引",
    "NIST_钠D线标准数据说明.md": "双棱镜·钠黄光与Na D双线",
}


def clean(text: str) -> str:
    text = (
        text.replace("\x00", " ")
        .replace("\ufeff", " ")
        .replace("\u00ad", "")
    )
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def useful(text: str, minimum: int = 35) -> bool:
    compact = re.sub(r"\s+", "", text)
    return (
        len(compact) >= minimum
        and sum(character.isprintable() for character in compact)
        / max(1, len(compact))
        > 0.92
    )


def split_chunks(text: str):
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_SIZE)
        if end < len(text):
            pivots = (
                text.rfind("\n", start, end),
                text.rfind("。", start, end),
                text.rfind("；", start, end),
            )
            pivot = max(pivots)
            if pivot > start + CHUNK_SIZE // 2:
                end = pivot + 1
        chunk = clean(text[start:end])
        if useful(chunk):
            yield chunk
        if end == len(text):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)


def stable_id(source: str, page: int, chunk: int, text: str) -> str:
    payload = f"{source}\0{page}\0{chunk}\0{text}".encode(
        "utf-8", errors="ignore"
    )
    return hashlib.sha256(payload).hexdigest()[:16]


def source_title(path: Path) -> str:
    return re.sub(r"[_-]+", " ", path.stem).strip()


def source_year(path: Path) -> int:
    match = re.search(r"(?:18|19|20)\d{2}", path.stem)
    return int(match.group()) if match else 0


def source_language(path: Path, text: str = "") -> str:
    if path.suffix.lower() == ".md":
        return "zh"
    compact = re.sub(r"\s+", "", text[:3000])
    chinese = len(re.findall(r"[\u3400-\u9fff]", compact))
    return "zh" if chinese > max(20, len(compact) // 5) else "en"


def default_topic(path: Path) -> str:
    return TOPIC_BY_SOURCE.get(path.name, "双棱镜干涉测波长综合实验")


def make_row(
    path: Path,
    page: int,
    chunk_no: int,
    text: str,
    topic: str,
    source_type: str,
) -> dict:
    locator = (
        f"PDF第{page}页"
        if source_type == "pdf" and page
        else (topic or "全文")
    )
    return {
        "id": stable_id(path.name, page, chunk_no, text),
        "source": path.name,
        "source_type": source_type,
        "page": page,
        "chunk": chunk_no,
        "text": text,
        "title": source_title(path),
        "year": source_year(path),
        "language": source_language(path, text),
        "topic": topic,
        "locator": locator,
    }


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    base_topic = default_topic(path)
    topic = base_topic
    lines: list[str] = []
    for line in path.read_text(
        encoding="utf-8", errors="replace"
    ).splitlines():
        heading = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if heading:
            prior = "\n".join(lines)
            if useful(prior):
                sections.append((topic, clean(prior)))
            heading_topic = clean(
                re.sub(r"^\d+(?:\.\d+)*[、.：:]?\s*", "", heading.group(1))
            )
            topic = (
                f"{base_topic}·{heading_topic}"
                if heading_topic
                else base_topic
            )
            lines = [line]
        else:
            lines.append(line)
    trailing = "\n".join(lines)
    if useful(trailing):
        sections.append((topic, clean(trailing)))
    return sections


def import_markdown(path: Path) -> list[dict]:
    rows: list[dict] = []
    chunk_no = 0
    for topic, section in markdown_sections(path):
        for chunk in split_chunks(section):
            rows.append(
                make_row(
                    path,
                    page=1,
                    chunk_no=chunk_no,
                    text=chunk,
                    topic=topic,
                    source_type="markdown",
                )
            )
            chunk_no += 1
    return rows


def pdf_page_count(pdfinfo: str | None, path: Path) -> int:
    if not pdfinfo:
        return 0
    result = subprocess.run(
        [pdfinfo, str(path)],
        capture_output=True,
        check=False,
        timeout=60,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r"^Pages:\s+(\d+)", output, re.MULTILINE)
    return int(match.group(1)) if match else 0


def extract_pdf(
    pdftotext: str,
    pdfinfo: str | None,
    path: Path,
) -> tuple[list[dict], dict]:
    result = subprocess.run(
        [pdftotext, "-layout", "-enc", "UTF-8", str(path), "-"],
        capture_output=True,
        check=False,
        timeout=300,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{path.name}: pdftotext failed: {detail}")

    pages = result.stdout.decode("utf-8", errors="replace").split("\f")
    total_pages = pdf_page_count(pdfinfo, path)
    if total_pages:
        pages = (pages + [""] * total_pages)[:total_pages]
    else:
        while pages and not pages[-1].strip():
            pages.pop()
        total_pages = len(pages)

    rows: list[dict] = []
    empty_pages: list[int] = []
    topic = default_topic(path)
    for page_number, raw_text in enumerate(pages, 1):
        page_text = clean(raw_text)
        if not useful(page_text):
            empty_pages.append(page_number)
            continue
        for chunk_no, chunk in enumerate(split_chunks(page_text)):
            rows.append(
                make_row(
                    path,
                    page=page_number,
                    chunk_no=chunk_no,
                    text=chunk,
                    topic=topic,
                    source_type="pdf",
                )
            )

    if not rows:
        catalog = (
            f"双棱镜干涉测波长参考资料：{source_title(path)}。"
            f"主题：{topic}。该 PDF 未提取到可检索文字层，"
            "建议完成 OCR 后重新构建专题索引。"
        )
        rows.append(
            make_row(
                path,
                page=0,
                chunk_no=0,
                text=catalog,
                topic=topic,
                source_type="pdf",
            )
        )

    report = {
        "source": path.name,
        "pages": total_pages,
        "chunks": len(rows),
        "empty_pages": empty_pages,
        "ocr_recommended": len(empty_pages) >= max(1, total_pages // 2),
    }
    return rows, report


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def build() -> dict:
    if not SOURCE_DIR.is_dir():
        raise FileNotFoundError(SOURCE_DIR)

    markdown_files = sorted(SOURCE_DIR.glob("*.md"))
    if REF_DIR.is_dir():
        markdown_files += sorted(REF_DIR.glob("*.md"))
        pdf_files = sorted(REF_DIR.glob("*.pdf"))
    else:
        pdf_files = []

    # Markdown-only builds are intentionally self-contained.  Poppler is
    # required only after an optional reference PDF is actually added.
    pdftotext = shutil.which("pdftotext") if pdf_files else None
    if pdf_files and not pdftotext:
        raise RuntimeError(
            "ref 目录中存在 PDF，但系统缺少 pdftotext，无法提取可选文献。"
        )
    pdfinfo = shutil.which("pdfinfo") if pdf_files else None

    rows: list[dict] = []
    reports: list[dict] = []
    for path in markdown_files:
        rows.extend(import_markdown(path))
    for path in pdf_files:
        pdf_rows, report = extract_pdf(
            str(pdftotext),
            pdfinfo,
            path,
        )
        rows.extend(pdf_rows)
        reports.append(report)

    seen_ids: set[str] = set()
    for row in rows:
        if row["id"] in seen_ids:
            raise RuntimeError(f"文本块 ID 冲突：{row['id']}")
        seen_ids.add(row["id"])

    IMPORTED_KB_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = IMPORTED_KB_DIR / f"{OUTPUT_STEM}.jsonl"
    temporary = jsonl_path.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(jsonl_path)

    ocr_documents = [
        report["source"]
        for report in reports
        if report["ocr_recommended"]
    ]
    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "documents": len(markdown_files) + len(pdf_files),
        "markdown_documents": len(markdown_files),
        "pdf_documents": len(pdf_files),
        "chunks": len(rows),
        "features": 60000,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "retrieval": "character TF-IDF + BM25",
        "ocr_recommended_documents": ocr_documents,
    }
    write_json(
        IMPORTED_KB_DIR / f"{OUTPUT_STEM}.manifest.json",
        manifest,
    )
    write_json(
        IMPORTED_KB_DIR / f"{OUTPUT_STEM}.extraction_report.json",
        reports,
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
