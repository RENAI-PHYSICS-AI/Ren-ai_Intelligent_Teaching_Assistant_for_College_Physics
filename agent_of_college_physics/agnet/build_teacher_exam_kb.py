from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

from build_kb import (
    SUPPORTED,
    classify,
    clean,
    close_wps,
    legacy_office,
    office_openxml,
    pdf_pages,
    split_chunks,
    useful,
)
from config import (
    EXAM_MATERIALS_DIR,
    MATERIALS_DIR,
    PROJECT_ROOT,
    TEACHER_EXAM_GUIDE_FILE,
    TEACHER_EXAM_KB_FILE,
    TEACHER_EXAM_KB_MANIFEST_FILE,
    TEACHER_EXAM_MATERIALS_DIR,
    TEACHER_EXAM_TEMPLATE_FILE,
)

PRIVATE_SOURCE_TYPE = "教师专用·教研考试"
PRIVATE_SUPPORTED = SUPPORTED | {".tex"}
MAX_ARCHIVE_MEMBERS = 2000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_RATIO = 500
_ARTIFACT_SUFFIXES = {
    ".aux", ".log", ".out", ".toc", ".bbl", ".blg", ".fls", ".fdb_latexmk",
    ".synctex", ".gz", ".sum", ".bak", ".tmp",
}
_FIGURE_DIRS = {"fig", "figure", "figures", "pic", "pics", "image", "images"}
_FORMAT_PRIORITY = {
    ".md": 5,
    ".tex": 4,
    ".docx": 3,
    ".doc": 3,
    ".txt": 2,
    ".pdf": 1,
    ".zip": 0,
}
_KNOWN_PENDING_REVIEW = (
    "试卷/2025-2026-2/大物A/answer.tex",
    "试卷/LaTeX题库/Chap2_Dynamics.tex",
)
_DEFAULT_SOURCE_PASSWORDS = ("410410", "505505")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def source_roots() -> tuple[Path, ...]:
    """Return existing restricted roots belonging to this repository only."""
    repository_root = PROJECT_ROOT.parent.resolve()
    roots: list[Path] = []
    for candidate in (EXAM_MATERIALS_DIR, TEACHER_EXAM_MATERIALS_DIR):
        if not candidate.is_dir() or not _inside(candidate, repository_root):
            continue
        resolved = candidate.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _relative(path: Path, root: Path, *, archive_prefix: str = "") -> str:
    if root.resolve() == EXAM_MATERIALS_DIR.resolve():
        base = f"考试素材/{path.relative_to(root).as_posix()}"
    elif _inside(root, MATERIALS_DIR):
        base = path.relative_to(MATERIALS_DIR).as_posix()
    else:
        base = f"教师专用/{root.name}/{path.relative_to(root).as_posix()}"
    return f"{archive_prefix}!/{base}" if archive_prefix else base


def _passwords() -> tuple[str, ...]:
    """Return automatic corpus passwords plus optional local overrides."""
    raw = os.getenv("PHYSICS_EXAM_SOURCE_PASSWORDS", "")
    result: list[str] = list(_DEFAULT_SOURCE_PASSWORDS)
    for value in re.split(r"[,，;；\r\n]+", raw):
        value = value.strip()
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _stable_id(relative: str, locator: str, part_number: int, text: str) -> str:
    payload = "\0".join((relative, locator, str(part_number), text))
    return "teacher-exam-" + hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:24]


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized_fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", "", text).lower()
    return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()


def _metadata(relative: str, path: Path) -> dict[str, object]:
    normalized = relative.replace("\\", "/")
    name = path.name
    course = ""
    for pattern, label in (
        (r"(?:大学物理|大物|物理)\s*1", "大学物理1"),
        (r"(?:大学物理|大物|物理)\s*2", "大学物理2"),
        (r"(?:大学物理|大物|物理)\s*[AaＡａ]", "大学物理A"),
        (r"(?:大学物理|大物|物理)\s*[BbＢｂ]", "大学物理B"),
        (r"工程物理", "工程物理"),
    ):
        if re.search(pattern, normalized, re.I):
            course = label
            break
    term_match = re.search(r"20\d{2}-20\d{2}-[12]", normalized)
    exam_type = next((value for value in ("补考", "重修", "期末", "模拟", "线上", "题库", "模板") if value in normalized), "")
    variant_match = re.search(r"(?:^|[/_\-（(\s])([ABC])卷", normalized, re.I)
    if path.resolve() == TEACHER_EXAM_GUIDE_FILE.resolve():
        role = "mandatory_policy"
    elif path.resolve() == TEACHER_EXAM_TEMPLATE_FILE.resolve():
        role = "standard_template"
    elif "答案" in name.lower() or "answer" in name.lower():
        role = "answer"
    elif "题库" in normalized:
        role = "question_bank"
    elif "模板" in normalized:
        role = "template"
    elif any(word in name.lower() for word in ("main", "试卷", "卷")):
        role = "paper"
    else:
        role = "reference"
    pending = any(marker.lower() in normalized.lower() for marker in _KNOWN_PENDING_REVIEW)
    return {
        "access_scope": "teacher_exam",
        "visibility": "verified_teacher",
        "corpus": "exam_materials",
        "course": course,
        "folder_term": term_match.group(0) if term_match else "",
        "exam_type": exam_type,
        "paper_variant": variant_match.group(1).upper() if variant_match else "",
        "document_role": role,
        "review_status": "pending" if pending else "reference",
        "template_standard": role == "standard_template",
    }


def _prefix(meta: dict[str, object], relative: str) -> str:
    fields = [
        "教师专用考试资料",
        f"课程：{meta['course'] or '未标注'}",
        f"材料角色：{meta['document_role']}",
        f"考试类型：{meta['exam_type'] or '未标注'}",
        f"卷型：{meta['paper_variant'] or '通用'}",
        f"归档学期：{meta['folder_term'] or '未标注'}",
        f"审核状态：{meta['review_status']}",
        f"源位置：{relative}",
    ]
    return "｜".join(fields)


def _append_parts(
    records: list[dict],
    path: Path,
    parts: list[tuple[int, str, str]],
    relative: str,
    source_type: str,
    source_hash: str,
    seen_text: set[str],
) -> tuple[int, int]:
    meta = _metadata(relative, path)
    forced_chapter = (
        "教研考试命题规范" if meta["document_role"] == "mandatory_policy"
        else "教研考试标准模板" if meta["document_role"] == "standard_template"
        else None
    )
    priority = (
        2.0 if meta["document_role"] == "mandatory_policy"
        else 1.8 if meta["document_role"] == "standard_template"
        else 0.55 if meta["review_status"] == "pending"
        else 1.0
    )
    added = duplicates = 0
    header = _prefix(meta, relative)
    for number, locator, raw_text in parts:
        cleaned = clean(raw_text)
        if not useful(cleaned):
            continue
        chapter = forced_chapter or classify(path.stem + "\n" + cleaned, fallback="教研考试")
        for part_number, body in enumerate(split_chunks(cleaned), 1):
            text = f"{header}\n{body}"
            fingerprint = _normalized_fingerprint(body)
            if fingerprint in seen_text:
                duplicates += 1
                continue
            seen_text.add(fingerprint)
            records.append({
                "id": _stable_id(relative, locator, part_number, body),
                "source": path.name,
                "source_type": source_type,
                "page": number,
                "chapter": chapter,
                "text": text,
                "relative_path": relative,
                "locator": locator,
                "priority": priority,
                "source_hash": source_hash,
                **meta,
            })
            added += 1
    return added, duplicates


def _append_catalog_record(
    records: list[dict], path: Path, relative: str, source_hash: str
) -> None:
    """Keep image-only sources discoverable without pretending OCR succeeded."""
    meta = _metadata(relative, path)
    meta["review_status"] = "pending_ocr"
    text = (
        f"{_prefix(meta, relative)}\n"
        "该文件已纳入教师考试资料目录，但没有可用文本层，当前仅可按文件名、课程、"
        "学期和材料角色定位。正文与公式须经OCR及教师复核后才能作为命题或标准答案依据。"
    )
    records.append({
        "id": _stable_id(relative, "待OCR文件索引", 1, text),
        "source": path.name,
        "source_type": f"{PRIVATE_SOURCE_TYPE}（待OCR目录索引）",
        "page": 0,
        "chapter": "教研考试待OCR",
        "text": text,
        "relative_path": relative,
        "locator": "待OCR文件索引",
        "priority": 0.2,
        "source_hash": source_hash,
        **meta,
    })


def _wps_document_text(path: Path, passwords: tuple[str, ...]) -> tuple[str, str]:
    """Extract a password-protected DOC/DOCX through WPS without exposing secrets."""
    if os.name != "nt" or not shutil.which("powershell"):
        return "", ""
    script = r"""
$ErrorActionPreference = 'Stop'
$app = $null
$doc = $null
try {
  $app = New-Object -ComObject KWPS.Application
  $app.Visible = $false
  try { $app.DisplayAlerts = 0 } catch {}
  $doc = $app.Documents.Open($env:PHYSICS_EXAM_INPUT, $false, $true, $false, $env:PHYSICS_EXAM_PASSWORD)
  $doc.Content.Text | Out-File -LiteralPath $env:PHYSICS_EXAM_OUTPUT -Encoding utf8 -NoNewline
} finally {
  if ($null -ne $doc) { $doc.Close($false) }
  if ($null -ne $app) { $app.Quit() }
}
"""
    # Every protected Word source in this corpus uses the first automatic
    # password.  Trying a wrong password can leave WPS on a modal prompt.
    for password in (passwords[:1] or ("",)):
        with tempfile.TemporaryDirectory(prefix="physics-exam-wps-") as temporary:
            output = Path(temporary) / "document.txt"
            environment = os.environ.copy()
            environment["PHYSICS_EXAM_INPUT"] = str(path)
            environment["PHYSICS_EXAM_OUTPUT"] = str(output)
            environment["PHYSICS_EXAM_PASSWORD"] = password
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True,
                    timeout=120,
                    env=environment,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            text = output.read_text(encoding="utf-8-sig", errors="replace") if output.is_file() else ""
            text = clean(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", text))
        # WPS may return a non-zero automation status while Content.Text was
        # already emitted (usually during Close/Quit).  The extracted body is
        # still valid and avoids reopening the document with a wrong password.
            if useful(text):
                return text, "WPS密码文档提取"
    return "", ""


def _document_parts(path: Path, passwords: tuple[str, ...]) -> tuple[list[tuple[int, str, str]], str, list[str]]:
    ext = path.suffix.lower()
    warnings: list[str] = []
    if ext == ".docx":
        parts = office_openxml(path)
        if any(useful(text) for _, _, text in parts):
            return parts, "OpenXML提取", warnings
        text, extractor = _wps_document_text(path, passwords)
        return ([(1, "文档正文", text)] if text else []), (extractor or "未提取"), warnings
    text, extractor = _wps_document_text(path, passwords)
    if text:
        return [(1, "文档正文", text)], extractor, warnings
    parts, extractor, failures = legacy_office(path)
    warnings.extend(failures)
    return parts, extractor, warnings


def _safe_extract_zip(path: Path, target: Path) -> list[Path]:
    extracted: list[Path] = []
    total = 0
    kwargs = {"metadata_encoding": "gbk"} if "metadata_encoding" in zipfile.ZipFile.__init__.__code__.co_varnames else {}
    with zipfile.ZipFile(path, **kwargs) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise RuntimeError("压缩包成员数超过安全上限")
        for info in members:
            if info.is_dir():
                continue
            member = PurePosixPath(info.filename.replace("\\", "/"))
            if member.is_absolute() or ".." in member.parts:
                raise RuntimeError("压缩包包含不安全路径")
            total += int(info.file_size)
            if total > MAX_ARCHIVE_BYTES:
                raise RuntimeError("压缩包展开大小超过安全上限")
            if info.compress_size and info.file_size / info.compress_size > MAX_ARCHIVE_RATIO:
                raise RuntimeError("压缩包压缩比异常")
            destination = target.joinpath(*member.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(destination)
    return extracted


def _skip(path: Path, root: Path) -> str:
    if path.stat().st_size == 0:
        return "空文件"
    if path.suffix.lower() in _ARTIFACT_SUFFIXES:
        return "编译产物"
    relative_parts = {part.lower() for part in path.relative_to(root).parts[:-1]}
    if path.suffix.lower() == ".pdf" and relative_parts & _FIGURE_DIRS:
        return "试题附图PDF"
    if path.suffix.lower() not in PRIVATE_SUPPORTED:
        return "不支持的文件类型"
    return ""


def _parts_for(path: Path, passwords: tuple[str, ...]) -> tuple[list[tuple[int, str, str]], str, list[str]]:
    ext = path.suffix.lower()
    if ext == ".pdf":
        pages = pdf_pages(path, passwords)
        return [(number, f"PDF第{number}页", text) for number, text in enumerate(pages, 1)], "PDF提取", []
    if ext in {".docx", ".doc"}:
        return _document_parts(path, passwords)
    if ext in {".pptx", ".pptm"}:
        return office_openxml(path), "OpenXML提取", []
    if ext in {".ppt", ".pot"}:
        parts, extractor, warnings = legacy_office(path)
        return parts, extractor, warnings
    if ext in {".md", ".txt", ".tex"}:
        return [(1, "全文", path.read_text(encoding="utf-8", errors="replace"))], "纯文本提取", []
    return [], "未提取", []


def _write_jsonl(records: list[dict]) -> None:
    TEACHER_EXAM_KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = TEACHER_EXAM_KB_FILE.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(TEACHER_EXAM_KB_FILE)


def _write_manifest(manifest: dict) -> None:
    TEACHER_EXAM_KB_MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = TEACHER_EXAM_KB_MANIFEST_FILE.with_name(TEACHER_EXAM_KB_MANIFEST_FILE.name + ".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(TEACHER_EXAM_KB_MANIFEST_FILE)


def build() -> dict:
    """Build one isolated teacher index from exam materials and future private notes."""
    records: list[dict] = []
    stats: Counter[str] = Counter()
    failures: list[dict] = []
    skipped: list[dict] = []
    duplicate_files: list[dict] = []
    roots = source_roots()
    passwords = _passwords()
    seen_sources: dict[str, str] = {}
    seen_text: set[str] = set()
    candidates: list[tuple[Path, Path]] = []
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            reason = _skip(path, root)
            if reason:
                if path.suffix.lower() in PRIVATE_SUPPORTED or path.stat().st_size == 0:
                    skipped.append({"file": _relative(path, root), "reason": reason})
                continue
            candidates.append((path, root))
    candidates.sort(key=lambda item: (
        0 if item[0].resolve() == TEACHER_EXAM_GUIDE_FILE.resolve() else 1,
        0 if item[0].resolve() == TEACHER_EXAM_TEMPLATE_FILE.resolve() else 1,
        -_FORMAT_PRIORITY.get(item[0].suffix.lower(), 0),
        _relative(item[0], item[1]).lower(),
    ))

    def process(path: Path, root: Path, *, relative_override: str = "") -> None:
        relative = relative_override or _relative(path, root)
        ext = path.suffix.lower()
        if ext == ".zip":
            try:
                with tempfile.TemporaryDirectory(prefix="physics-exam-zip-") as temporary:
                    extracted = _safe_extract_zip(path, Path(temporary))
                    for member in sorted(extracted):
                        reason = _skip(member, Path(temporary))
                        if reason:
                            continue
                        virtual = f"{relative}!/{member.relative_to(temporary).as_posix()}"
                        process(member, Path(temporary), relative_override=virtual)
                stats["zip_files"] += 1
            except Exception as exc:
                failures.append({"file": relative, "error": str(exc)})
            return
        try:
            digest = _source_hash(path)
            if digest in seen_sources:
                duplicate_files.append({"file": relative, "same_as": seen_sources[digest]})
                stats["duplicate_files"] += 1
                return
            seen_sources[digest] = relative
            parts, extractor, warnings = _parts_for(path, passwords)
            for warning in warnings:
                failures.append({"file": relative, "warning": warning})
            if not any(useful(text) for _, _, text in parts):
                failures.append({"file": relative, "error": "未提取到可检索正文"})
                stats["empty_text_files"] += 1
                _append_catalog_record(records, path, relative, digest)
                stats["catalog_only"] += 1
                return
            added, duplicates = _append_parts(
                records, path, parts, relative,
                f"{PRIVATE_SOURCE_TYPE}（{extractor}）", digest, seen_text,
            )
            stats[f"{ext}_files"] += 1
            stats[f"{ext}_chunks"] += added
            stats["duplicate_chunks"] += duplicates
        except Exception as exc:
            failures.append({"file": relative, "error": str(exc)})

    try:
        for path, root in candidates:
            process(path, root)
    finally:
        close_wps()

    _write_jsonl(records)
    template_available = TEACHER_EXAM_TEMPLATE_FILE.is_file() and any(
        _inside(TEACHER_EXAM_TEMPLATE_FILE, root) for root in roots
    )
    template_hash = _source_hash(TEACHER_EXAM_TEMPLATE_FILE) if template_available else ""
    manifest = {
        "private": True,
        "collection": "教师专用·教研考试",
        "chunks": len(records),
        "files_scanned": len(candidates),
        "failures": failures,
        "skipped": skipped,
        "duplicates": duplicate_files,
        "by_type": dict(sorted(stats.items())),
        "source_roots": [str(root) for root in roots],
        "index_file": TEACHER_EXAM_KB_FILE.name,
        "mandatory_guide": "考试素材/大学物理课程章节与组卷分值规范.md",
        "standard_template": "考试素材/试卷/2025-2026-2/25262大物1补考/main.tex",
        "standard_template_sha256": template_hash,
        "policy": "考试素材仅写入教师私有索引；学生端不得加载、查询或回退到该索引",
    }
    _write_manifest(manifest)
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
