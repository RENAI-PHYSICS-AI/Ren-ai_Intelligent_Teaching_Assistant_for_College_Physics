from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from build_viscosity_import import (
    atomic_write_text,
    clean,
    make_row,
    relative_path,
    split_chunks,
    useful,
    write_json,
)
from config import IMPORTED_KB_DIR, PROJECT_ROOT


SOURCE_DIR = PROJECT_ROOT / "教学素材" / "物理实验" / "惠斯通电桥测电阻"
REF_DIR = SOURCE_DIR / "ref"
OUTPUT_STEM = "wheatstone_bridge"
CHUNK_SIZE = 760
CHUNK_OVERLAP = 120
ROUTES = ["principle", "balance", "sensitivity", "fit"]
CORE_REFERENCE_COUNT = 11

MARKDOWN_TOPICS = {
    "惠斯通电桥可视化实验方案.md": "惠斯通电桥·四路可视化实验设计",
    "惠斯通电桥文献导读.md": "惠斯通电桥·平衡原理、灵敏度、误差与不确定度",
    "README.md": "惠斯通电桥·经典文献与权威资料索引",
}


def markdown_sections(path: Path) -> list[tuple[str, str]]:
    base_topic = MARKDOWN_TOPICS.get(path.name, "惠斯通电桥测电阻综合实验")
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
        "bytes": path.stat().st_size,
    }
    return rows, report


def _reference_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    numbers = re.findall(r"^###\s+2\.(\d+)\s", text, flags=re.MULTILINE)
    expected = [str(index) for index in range(1, CORE_REFERENCE_COUNT + 1)]
    if numbers != expected:
        raise RuntimeError(
            f"参考资料编号应连续为 {expected}，实际为 {numbers}"
        )
    return len(numbers)


def build() -> dict:
    markdown_files = [
        SOURCE_DIR / "惠斯通电桥可视化实验方案.md",
        SOURCE_DIR / "惠斯通电桥文献导读.md",
        REF_DIR / "README.md",
    ]
    missing = [relative_path(path) for path in markdown_files if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少已索引资料：" + "；".join(missing))

    reference_count = _reference_count(REF_DIR / "README.md")
    rows: list[dict] = []
    reports: list[dict] = []
    for path in markdown_files:
        markdown_rows, report = import_markdown(path)
        rows.extend(markdown_rows)
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
        missing_fields = required - row.keys()
        if missing_fields:
            raise RuntimeError(
                f"{row.get('source', '?')} 缺少字段：{sorted(missing_fields)}"
            )
        if row["id"] in identifiers:
            raise RuntimeError(f"文本块 ID 冲突：{row['id']}")
        identifiers.add(row["id"])

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "topic": "惠斯通电桥测电阻",
        "method": "零示平衡、粗调细调、戴维南灵敏度、多比率线性拟合与不确定度评定",
        "measured_quantity": "未知电阻 R_x",
        "routes": ROUTES,
        "documents": len(reports),
        "markdown_documents": len(markdown_files),
        "pdf_documents": 0,
        "core_references": reference_count,
        "chunks": len(rows),
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "output": "agnet/knowledge_base/imports/wheatstone_bridge.jsonl",
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
