from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from config import IMPORTED_KB_DIR, PROJECT_ROOT


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "牛顿环"
REF_DIR = SOURCE_DIR / "ref"
OUTPUT_STEM = "newton_rings"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120

# 本校主任务是把空气中钠黄光波长作为已知量，用暗环直径求曲率半径 R。
# IGNOU 的“已知 R 测波长”只作为公式互逆性拓展，不能覆盖本校任务主线。
CURRICULUM = {
    "known_wavelength_nm": 589.3,
    "measured_quantity": "平凸透镜曲率半径 R",
    "dark_ring_orders": [5, 10, 15, 20, 25, 30],
    "successive_difference": 15,
    "primary_methods": ["m-n=15 逐差", "D_m^2-m 线性拟合"],
}

IGNOU_PDF = (
    PROJECT_ROOT
    / "教学素材"
    / "物理实验"
    / "双棱镜干涉测波长"
    / "ref"
    / "IGNOU_BPHCL-138_Waves_and_Optics_Laboratory_2022.pdf"
)

# 页码均为 PDF 的实际页码（从 1 开始）。None 表示导入全部页。
PDF_SPECS = {
    REF_DIR / "College_of_San_Mateo_Physics270_Lab09_Newtons_Rings.pdf": {
        "title": "Physics 270, Experiment 9 — Newton's Rings",
        "year": 0,
        "topic": "牛顿环·非理想接触、回程差与曲率半径",
        "pages": None,
        "note": "公开高校实验讲义；年份未在正文中明确署出。",
    },
    REF_DIR / "MSU_PHY431_2019_Interference_Fringes_Newton_Rings.pdf": {
        "title": "PHY 431 Experiment 6 — Interference Fringes, Newton Rings",
        "year": 2019,
        "topic": "牛顿环·数字图像、线性拟合残差与像散",
        "pages": None,
        "note": "密歇根州立大学 2019 Spring 课程归档。",
    },
    REF_DIR / "PHYWE_P2220203_Newtons_Rings_Digital_Camera.pdf": {
        "title": "Newton's Rings with Laser and Digital Array Camera",
        "year": 0,
        "topic": "牛顿环·数字相机、多波长与线性拟合",
        "pages": None,
        "note": "PHYWE P2220203 原厂实验说明；正文未明确署出版年。",
    },
    IGNOU_PDF: {
        "title": "BPHCL-138 Waves and Optics Laboratory — Experiment 5",
        "year": 2022,
        "topic": "牛顿环·理论与操作（已知 R 测波长，仅作拓展）",
        "pages": list(range(57, 67)),
        "note": "只导入 Newton's Rings 章节（PDF 实际第 57–66 页）；复用仓库既有 PDF，不重复保存。",
    },
}

TOPIC_BY_MARKDOWN = {
    "牛顿环可视化实验方案.md": "牛顿环·四路可视化实验设计",
    "README.md": "牛顿环·参考资料索引与课程边界",
    "牛顿环文献导读.md": "牛顿环·文献导读、公式与误差",
}

SOURCE_URLS = {
    "College_of_San_Mateo_Physics270_Lab09_Newtons_Rings.pdf": (
        "https://collegeofsanmateo.edu/physics/docs/physics270/lab09.pdf"
    ),
    "MSU_PHY431_2019_Interference_Fringes_Newton_Rings.pdf": (
        "https://web.pa.msu.edu/courses/2019spring/PHY431/"
        "Lab6-Interference%20Fringes%2C%20Newton%20Rings.pdf"
    ),
    "PHYWE_P2220203_Newtons_Rings_Digital_Camera.pdf": (
        "https://phywe-itemservice.s3.eu-central-1.amazonaws.com/sites/"
        "DMS-Phywe/PROD/de-DE/item/phy_itemtestinstruction/P2/P2220203/"
        "P2220203_en.pdf"
    ),
    IGNOU_PDF.name: (
        "https://www.egyankosh.ac.in/bitstream/123456789/82374/3/"
        "BPHCL-138%28English%29%20%281%29.pdf"
    ),
}


def clean(text: str) -> str:
    text = text.replace("\x00", " ").replace("\ufeff", " ").replace("\u00ad", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


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
    base_topic = TOPIC_BY_MARKDOWN.get(path.name, "牛顿环综合实验")
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
    title = path.stem
    chunk_no = 0
    for topic, section in markdown_sections(path):
        for chunk in split_chunks(section):
            rows.append(
                make_row(path, 1, chunk_no, chunk, topic, "markdown", title, 0)
            )
            chunk_no += 1
    return rows, {
        "source": path.name,
        "source_path": relative_path(path),
        "source_type": "markdown",
        "chunks": len(rows),
    }


def run_tool(arguments: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        arguments,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


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


def validate_pdf(path: Path, pdfinfo: str) -> tuple[int, str]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise RuntimeError(f"{path.name}: 文件签名不是 %PDF-")
    return pdf_page_count(pdfinfo, path), sha256(path)


def extract_pdf(
    path: Path,
    spec: dict,
    pdftotext: str,
    pdfinfo: str,
) -> tuple[list[dict], dict]:
    total_pages, digest = validate_pdf(path, pdfinfo)
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
        raise RuntimeError(
            f"{path.name}: 选定页未提取到可检索文字；请 OCR 后再构建，避免写入空壳条目。"
        )

    return rows, {
        "source": path.name,
        "source_path": relative_path(path),
        "source_type": "pdf",
        "url": SOURCE_URLS[path.name],
        "bytes": path.stat().st_size,
        "sha256": digest,
        "pdf_signature": "%PDF-",
        "pages": total_pages,
        "selected_pages": selected_pages,
        "empty_pages": empty_pages,
        "text_layer_pages": len(selected_pages) - len(empty_pages),
        "chunks": len(rows),
        "ocr_recommended": bool(empty_pages),
        "note": spec["note"],
    }


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_json(path: Path, value) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def build() -> dict:
    if not SOURCE_DIR.is_dir():
        raise FileNotFoundError(SOURCE_DIR)

    markdown_files = sorted(SOURCE_DIR.glob("*.md")) + sorted(REF_DIR.glob("*.md"))
    pdf_specs = [(path, spec) for path, spec in PDF_SPECS.items() if path.is_file()]
    missing_pdfs = [relative_path(path) for path in PDF_SPECS if not path.is_file()]
    if missing_pdfs:
        raise FileNotFoundError("缺少已索引 PDF：" + "；".join(missing_pdfs))

    pdftotext = shutil.which("pdftotext")
    pdfinfo = shutil.which("pdfinfo")
    if pdf_specs and (not pdftotext or not pdfinfo):
        raise RuntimeError("存在 PDF 文献，但缺少 pdftotext 或 pdfinfo。")

    rows: list[dict] = []
    reports: list[dict] = []
    for path in markdown_files:
        markdown_rows, report = import_markdown(path)
        rows.extend(markdown_rows)
        reports.append(report)
    for path, spec in pdf_specs:
        pdf_rows, report = extract_pdf(path, spec, str(pdftotext), str(pdfinfo))
        rows.extend(pdf_rows)
        reports.append(report)

    required_fields = {
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
    seen: set[str] = set()
    for row in rows:
        missing = required_fields - row.keys()
        if missing:
            raise RuntimeError(f"{row.get('source', '?')} 缺少字段：{sorted(missing)}")
        if row["id"] in seen:
            raise RuntimeError(f"文本块 ID 冲突：{row['id']}")
        seen.add(row["id"])

    created_at = datetime.now().astimezone().isoformat()
    manifest = {
        "created_at": created_at,
        "topic": "牛顿环",
        "primary_task": "已知空气中钠黄光 λ=589.3 nm，测平凸透镜曲率半径 R",
        **CURRICULUM,
        "documents": len(markdown_files) + len(pdf_specs),
        "markdown_documents": len(markdown_files),
        "pdf_documents": len(pdf_specs),
        "local_pdf_documents": sum(path.parent == REF_DIR for path, _ in pdf_specs),
        "cross_referenced_pdf_documents": sum(path.parent != REF_DIR for path, _ in pdf_specs),
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/newton_rings.jsonl",
        "main_knowledge_base_modified": False,
        "sources": reports,
    }

    IMPORTED_KB_DIR.mkdir(parents=True, exist_ok=True)
    jsonl = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write_text(IMPORTED_KB_DIR / f"{OUTPUT_STEM}.jsonl", jsonl)
    write_json(IMPORTED_KB_DIR / f"{OUTPUT_STEM}.manifest.json", manifest)
    write_json(
        IMPORTED_KB_DIR / f"{OUTPUT_STEM}.extraction_report.json",
        reports,
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
