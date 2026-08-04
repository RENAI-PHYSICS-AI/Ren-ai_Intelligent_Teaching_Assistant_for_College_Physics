from __future__ import annotations

import json
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from config import KB_DIR, KB_FILE, MATERIALS_DIR, SOLUTION_NAME, TEXTBOOK_DIR, TEXTBOOK_NAME

CHAPTERS = [
    "第1章 质点运动、时间和空间", "第2章 牛顿运动定律", "第3章 动量与角动量",
    "第4章 功和能", "第5章 刚体力学", "第6章 机械振动", "第7章 机械波",
    "第8章 相对论基础", "第9章 气体动理论", "第10章 热力学基础",
    "第11章 静电场", "第12章 静电场中的导体和电介质", "第13章 恒定磁场",
    "第14章 电磁感应", "第15章 电磁场与电磁波", "第16章 波动光学",
    "第17章 量子物理基础", "第18章 原子核与粒子物理",
]

TOPIC_RULES = [
    (0, "质点|运动学|位移|速度|加速度|相对论|时空"), (1, "牛顿|摩擦|惯性|受力"),
    (2, "动量|冲量|角动量|碰撞"), (3, "功和能|机械能|势能|保守力"),
    (4, "刚体|转动惯量|力矩|定轴转动"), (5, "振动|简谐|阻尼|受迫|共振"),
    (6, "机械波|波动|声波|驻波|多普勒"), (7, "狭义相对论|洛伦兹"),
    (8, "气体动理论|分子运动|麦克斯韦|平均自由程"), (9, "热力学|熵|卡诺|循环"),
    (10, "静电场|库仑|高斯|电势"), (11, "导体|电介质|电容"),
    (12, "磁场|毕奥|安培|洛伦兹力|霍尔"), (13, "电磁感应|法拉第|楞次|自感|互感"),
    (14, "电磁波|麦克斯韦方程"), (15, "光学|干涉|衍射|偏振|光栅"),
    (16, "量子|黑体|光电效应|德布罗意|薛定谔"), (17, "原子核|放射性|粒子物理"),
]

SUPPORTED = {".pdf", ".pptx", ".pptm", ".ppt", ".pot", ".docx", ".doc", ".md", ".txt", ".zip", ".mp4", ".mpg"}
_WPS = None
_WPP = None


def find_primary_pdfs() -> tuple[Path, Path]:
    files = list(TEXTBOOK_DIR.glob("*.pdf"))
    textbook = next((p for p in files if "习题" not in p.name), None)
    solution = next((p for p in files if "习题" in p.name or "解答" in p.name), None)
    if not textbook or not solution:
        raise FileNotFoundError(f"未在 {TEXTBOOK_DIR} 找到祝之光教材和习题解答")
    return textbook.resolve(), solution.resolve()


def clean(text: str) -> str:
    text = text.replace("\x00", " ").replace("\ufeff", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def useful(text: str, minimum: int = 35) -> bool:
    compact = re.sub(r"\s+", "", text)
    return len(compact) >= minimum and sum(ch.isprintable() for ch in compact) / max(1, len(compact)) > .92


def split_chunks(text: str, size: int = 1500, overlap: int = 180):
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            pivot = max(text.rfind("\n", start, end), text.rfind("。", start, end))
            if pivot > start + size // 2:
                end = pivot + 1
        yield clean(text[start:end])
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


def classify(text: str, fallback: str = "补充教学资料") -> str:
    sample = re.sub(r"\s+", "", text[:6000])
    scores = [(len(re.findall(pattern, sample, re.I)), idx) for idx, pattern in TOPIC_RULES]
    score, idx = max(scores)
    return CHAPTERS[idx] if score else fallback


def pdf_pages(pdf: Path) -> list[str]:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("缺少 pdftotext")
    proc = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(pdf), "-"], capture_output=True)
    if proc.returncode:
        return []
    return proc.stdout.decode("utf-8", errors="replace").split("\f")


def xml_text(blob: bytes) -> str:
    try:
        root = ET.fromstring(blob)
        return clean("\n".join(node.text for node in root.iter() if node.text and node.tag.endswith("}t")))
    except ET.ParseError:
        return ""


def office_openxml(path: Path) -> list[tuple[int, str, str]]:
    rows = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if path.suffix.lower() in {".pptx", ".pptm"}:
                slides = [n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
                slides.sort(key=lambda n: int(re.search(r"(\d+)", Path(n).stem).group(1)))
                for i, name in enumerate(slides, 1):
                    text = xml_text(archive.read(name))
                    notes_name = f"ppt/notesSlides/notesSlide{i}.xml"
                    if notes_name in names:
                        notes = xml_text(archive.read(notes_name))
                        if notes:
                            text += "\n讲者备注：" + notes
                    rows.append((i, f"幻灯片{i}", clean(text)))
            else:
                parts = [n for n in names if n == "word/document.xml" or n.startswith("word/header") or n.startswith("word/footer")]
                text = clean("\n".join(xml_text(archive.read(n)) for n in parts))
                rows.append((1, "文档正文", text))
    except (zipfile.BadZipFile, OSError):
        pass
    return rows


def binary_text(path: Path) -> str:
    """Conservative recovery for legacy OLE doc/ppt when Office COM is unavailable."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    found = []
    # UTF-16LE runs, common for Chinese text in binary Office documents.
    for match in re.finditer(rb"(?:[\x09\x20-\x7e\x00-\xff]\x00){8,}", data):
        value = match.group().decode("utf-16le", errors="ignore")
        if useful(value, 8):
            found.append(value)
    # ASCII runs preserve formulas, units and English titles.
    for match in re.finditer(rb"[\x20-\x7e]{16,}", data):
        value = match.group().decode("latin1", errors="ignore")
        if not any(x in value.lower() for x in ("microsoft", "office", "xml", "http://", "font")):
            found.append(value)
    return clean("\n".join(dict.fromkeys(found)))


def _shape_text(shape) -> list[str]:
    found = []
    try:
        if int(getattr(shape, "Type", 0)) == 6:  # msoGroup
            for i in range(1, shape.GroupItems.Count + 1):
                found.extend(_shape_text(shape.GroupItems.Item(i)))
        elif getattr(shape, "HasTextFrame", 0) and shape.TextFrame.HasText:
            value = clean(str(shape.TextFrame.TextRange.Text))
            if value:
                found.append(value)
    except Exception:
        pass
    return found


def _wps_legacy_once(path: Path) -> list[tuple[int, str, str]]:
    """Read legacy DOC/PPT through installed WPS Office COM automation."""
    global _WPS, _WPP
    import win32com.client
    ext = path.suffix.lower()
    if ext == ".doc":
        if _WPS is None:
            _WPS = win32com.client.Dispatch("KWPS.Application")
            try:
                _WPS.Visible = False
            except Exception:
                pass
        doc = _WPS.Documents.Open(str(path), False, True)
        try:
            return [(1, "WPS文档正文", clean(str(doc.Content.Text)))]
        finally:
            try:
                doc.Close(False)
            except Exception:
                pass
    if _WPP is None:
        _WPP = win32com.client.Dispatch("KWPP.Application")
        try:
            _WPP.Visible = False
        except Exception:
            pass
    deck = _WPP.Presentations.Open(str(path), True, False, False)
    try:
        rows = []
        for i in range(1, deck.Slides.Count + 1):
            slide = deck.Slides.Item(i); texts = []
            for j in range(1, slide.Shapes.Count + 1):
                texts.extend(_shape_text(slide.Shapes.Item(j)))
            try:
                notes = slide.NotesPage
                for j in range(1, notes.Shapes.Count + 1):
                    texts.extend(_shape_text(notes.Shapes.Item(j)))
            except Exception:
                pass
            rows.append((i, f"幻灯片{i}", clean("\n".join(dict.fromkeys(texts)))))
        return rows
    finally:
        try:
            deck.Close()
        except Exception:
            pass


def _reset_wps(ext: str) -> None:
    global _WPS, _WPP
    name = "_WPS" if ext == ".doc" else "_WPP"
    app = globals()[name]
    if app is not None:
        try:
            app.Quit()
        except Exception:
            pass
    globals()[name] = None


def wps_legacy(path: Path) -> list[tuple[int, str, str]]:
    last_error = None
    for _ in range(2):
        try:
            return _wps_legacy_once(path)
        except Exception as exc:
            last_error = exc
            _reset_wps(path.suffix.lower())
    raise last_error


def close_wps() -> None:
    global _WPS, _WPP
    for app in (_WPS, _WPP):
        if app is not None:
            try:
                app.Quit()
            except Exception:
                pass
    _WPS = _WPP = None


def archive_listing(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if not n.endswith("/")]
        return "压缩包文件清单：\n" + "\n".join(names[:1000])
    except (zipfile.BadZipFile, OSError):
        return ""


def record_parts(records: list[dict], path: Path, parts: list[tuple[int, str, str]], source_type: str,
                 priority: float, forced_chapter: str | None = None) -> int:
    relative = str(path.relative_to(MATERIALS_DIR))
    added = 0
    for number, locator, text in parts:
        text = clean(text)
        if not useful(text):
            continue
        chapter = forced_chapter or classify(path.stem + "\n" + text)
        for part_no, chunk in enumerate(split_chunks(text), 1):
            records.append({"id": f"{abs(hash(relative))}-{number}-{part_no}", "source": path.name,
                            "source_type": source_type, "page": number, "chapter": chapter, "text": chunk,
                            "relative_path": relative, "locator": locator, "priority": priority})
            added += 1
    return added


def build() -> dict:
    textbook, solution = find_primary_pdfs()
    records: list[dict] = []
    stats = Counter(); failures = []
    all_files = sorted(p for p in MATERIALS_DIR.rglob("*") if p.is_file())
    try:
      for path in all_files:
        ext = path.suffix.lower()
        if ext not in SUPPORTED:
          continue
        resolved = path.resolve()
        priority = 1.0; source_type = "补充资料"
        forced_chapter = None
        if resolved == textbook:
          priority = 1.5; source_type = "基准教材正文"; forced_chapter = "教材正文"
        elif resolved == solution:
          priority = 1.3; source_type = "基准教材习题解答"
        try:
            if ext == ".pdf":
                parts = [(i, f"PDF第{i}页", text) for i, text in enumerate(pdf_pages(path), 1)]
            elif ext in {".pptx", ".pptm", ".docx"}:
                parts = office_openxml(path)
            elif ext in {".ppt", ".pot", ".doc"}:
                try:
                    parts = wps_legacy(path)
                    source_type += "（WPS提取）"
                except Exception as wps_exc:
                    parts = [(1, "二进制文档文本恢复", binary_text(path))]
                    failures.append({"file": str(path.relative_to(MATERIALS_DIR)), "warning": f"WPS读取失败，已回退：{wps_exc}"})
            elif ext in {".md", ".txt"}:
                parts = [(1, "全文", path.read_text(encoding="utf-8", errors="replace"))]
            elif ext == ".zip":
                parts = [(1, "压缩包目录", archive_listing(path))]
            else:
                parts = []
            added = record_parts(records, path, parts, source_type, priority, forced_chapter)
            stats[f"{ext}_files"] += 1; stats[f"{ext}_chunks"] += added
            if not added:
                # Every file still becomes discoverable, including videos and image-only documents.
                relative = str(path.relative_to(MATERIALS_DIR))
                records.append({"id": f"catalog-{abs(hash(relative))}", "source": path.name,
                                "source_type": "资源目录索引", "page": 0,
                                "chapter": classify(path.stem),
                                "text": f"教学资源文件：{path.name}\n相对路径：{relative}\n文件类型：{ext or '无扩展名'}。该文件未提取到可检索正文，可按文件名定位原始资源。",
                                "relative_path": relative, "locator": "文件索引", "priority": .45})
                stats["catalog_only"] += 1
        except Exception as exc:
          failures.append({"file": str(path.relative_to(MATERIALS_DIR)), "error": str(exc)})
    finally:
      close_wps()
    for i, chapter in enumerate(CHAPTERS, 1):
        records.append({"id": f"chapter-{i}", "source": TEXTBOOK_NAME, "source_type": "章节索引",
                        "page": 0, "chapter": chapter, "text": f"{chapter}。以祝之光《物理学》第5版为基准，其他教学材料仅作补充。",
                        "relative_path": str(textbook.relative_to(MATERIALS_DIR)), "locator": "章节索引", "priority": 1.5})
    KB_DIR.mkdir(parents=True, exist_ok=True)
    with KB_FILE.open("w", encoding="utf-8", newline="\n") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {"chunks": len(records), "files_scanned": len(all_files), "failures": failures,
                "by_type": dict(sorted(stats.items())), "primary_textbook": str(textbook),
                "primary_solution": str(solution), "policy": "祝之光教材优先，教学素材全目录补充"}
    (KB_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
