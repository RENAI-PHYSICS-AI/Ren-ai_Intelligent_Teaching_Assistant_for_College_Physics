from __future__ import annotations

import io
import locale
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final


MAX_TEX_BYTES: Final = 512 * 1024
MAX_PDF_BYTES: Final = 8 * 1024 * 1024
MAX_WORKSPACE_BYTES: Final = 64 * 1024 * 1024
# Keep the optional archive within the persistence/download limit used by the
# chat history store. Larger image sets should be reduced before delivery.
MAX_ARCHIVE_BYTES: Final = 8 * 1024 * 1024
MAX_COMPILER_LOG_BYTES: Final = 512 * 1024
DEFAULT_TIMEOUT_SECONDS: Final = 45

_COMPILER_NAMES: Final = ("xelatex", "lualatex", "pdflatex", "tectonic")
_DOCUMENT_CLASSES: Final = frozenset({"article", "ctexart"})
_PACKAGES: Final = frozenset({
    "algorithm",
    "algorithmicx",
    "algpseudocode",
    "amsfonts",
    "amsmath",
    "amssymb",
    "amsthm",
    "array",
    "booktabs",
    "calc",
    "ctex",
    "diagbox",
    "enumitem",
    "enumerate",
    "fancyhdr",
    "fontspec",
    "geometry",
    "graphicx",
    "indentfirst",
    "longtable",
    "mathrsfs",
    "mdframed",
    "multicol",
    "multirow",
    "relsize",
    "setspace",
    "tabularx",
    "tikz",
    "times",
    "ulem",
    "xcolor",
    "xeCJK",
})
_TIKZ_LIBRARIES: Final = frozenset({
    "angles",
    "arrows",
    "arrows.meta",
    "backgrounds",
    "babel",
    "calc",
    "decorations.markings",
    "decorations.pathmorphing",
    "decorations.pathreplacing",
    "fit",
    "intersections",
    "matrix",
    "patterns",
    "positioning",
    "quotes",
    "shapes.geometric",
})
_GRAPHICS_EXTENSIONS: Final = (".pdf", ".png", ".jpg", ".jpeg")
_SAFE_TEX_RESOURCE_EXTENSIONS: Final = frozenset({
    ".afm", ".cfg", ".clo", ".cls", ".cnf", ".def", ".enc", ".fd",
    ".fmt", ".ist", ".ldf", ".lua", ".map", ".mf", ".otf", ".pfb",
    ".pk", ".sty", ".tex", ".tfm", ".ttc", ".ttf", ".vf",
})

_FENCE_RE = re.compile(
    r"```(?P<info>[^\r\n`]*)\r?\n(?P<body>.*?)```", re.I | re.S
)
_TEX_FENCE_INFO_RE = re.compile(r"^\s*(?:latex|tex)(?:\b|:)(?P<rest>.*)$", re.I)
_ANY_TEX_NAME_RE = re.compile(r"(?<![\w.-])([A-Za-z0-9_.-]+\.tex)(?![\w.-])", re.I)
_NAMED_TEX_FILES: Final = frozenset({"main.tex", "answer.tex"})
_BINARY_STREAM_RE = re.compile(
    r"(?:%PDF-\d(?:\.\d)?|<~(?:[!-u]|z|\s){8,}?~>)", re.I | re.S
)
_DOCUMENT_RE = re.compile(
    r"\\documentclass\b.*?\\begin\s*\{document\}.*?\\end\s*\{document\}",
    re.I | re.S,
)
_CLASS_RE = re.compile(
    r"\\documentclass(?:\s*\[[^\]]*\])?\s*\{\s*([^{}]+)\s*\}", re.I
)
_PACKAGE_RE = re.compile(
    r"\\usepackage(?:\s*\[[^\]]*\])?\s*\{\s*([^{}]+)\s*\}", re.I
)
_GRAPHICS_RE = re.compile(
    r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{\s*([^{}]+)\s*\}", re.I
)
_TIKZ_LIBRARY_RE = re.compile(r"\\usetikzlibrary\s*\{\s*([^{}]+)\s*\}", re.I)
_TIKZ_COMMAND_RE = re.compile(
    r"\\(?:begin\s*\{\s*tikzpicture\s*\}|tikz(?:set)?\b|usetikzlibrary\b)", re.I
)
_BANNED_TIKZ_RE = re.compile(
    r"(?:"
    r"\\(?:tikzexternalize|tikzsetexternalprefix|pgfdeclareimage|pgfimage|"
    r"pgfdataimage|usepgfmodule|usepgflibrary)\b|"
    r"\bexternal\s*/\s*(?:system\s+call|shell\s+escape)\b|"
    r"\bplot\s+file\b"
    r")",
    re.I,
)
_MDFRAMED_BLOCK_RE = re.compile(
    r"(?P<open>\\begin\s*\{\s*mdframed\s*\}(?:\s*\[[^\]]*\])?)"
    r"(?P<body>.*?)"
    r"(?P<close>\\end\s*\{\s*mdframed\s*\})",
    re.I | re.S,
)
_BANNED_TEX_RE = re.compile(
    r"(?:"
    r"\^\^|"
    r"\\(?:input|include|openin|openout|read|write|newread|newwrite|closein|closeout)(?![A-Za-z@])|"
    r"\\(?:immediate|special|directlua|luaexec|scantokens|csname|catcode|endlinechar|escapechar)\b|"
    r"\\(?:def|edef|gdef|xdef|let|futurelet|expandafter|everyjob|RequirePackage)\b|"
    r"\\(?:lstinputlisting|verbatiminput|VerbatimInput|bibliography|addbibresource|graphicspath)\b|"
    r"\\pdf[a-zA-Z@]*\b|"
    r"\\begin\s*\{\s*(?:filecontents\*?|luacode\*?)\s*\}|"
    r"\\ExplSyntax(?:On|Off)\b"
    r")",
    re.I,
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SAFE_GRAPHIC_PATH_RE = re.compile(r"^[0-9A-Za-z\u3400-\u9fff _./()\-]+$")


class ExamArtifactError(RuntimeError):
    """Base error safe for presentation in the teacher-only UI."""


class TexExtractionError(ExamArtifactError):
    pass


class UnsafeTexError(ExamArtifactError):
    pass


class TexCompilerUnavailable(ExamArtifactError):
    pass


class TexCompilationError(ExamArtifactError):
    def __init__(self, message: str, *, log: str = "") -> None:
        super().__init__(message)
        self.log = log


@dataclass(frozen=True, slots=True)
class ExamArtifactBundle:
    tex_name: str
    tex_bytes: bytes
    pdf_name: str
    pdf_bytes: bytes
    compiler: str
    elapsed_seconds: float

    @property
    def tex_mime(self) -> str:
        return "application/x-tex; charset=utf-8"

    @property
    def pdf_mime(self) -> str:
        return "application/pdf"


@dataclass(frozen=True, slots=True)
class NamedTexDocument:
    name: str
    source: str


@dataclass(frozen=True, slots=True)
class ExamArtifactBundles:
    """Immutable, iterable artifacts for main.tex and answer.tex."""

    items: tuple[ExamArtifactBundle, ...]

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> ExamArtifactBundle:
        return self.items[index]

    def get(self, tex_name: str) -> ExamArtifactBundle:
        wanted = str(tex_name or "").strip().lower()
        for item in self.items:
            if item.tex_name.lower() == wanted:
                return item
        raise KeyError(tex_name)


@dataclass(frozen=True, slots=True)
class ExamDownloadArchive:
    """In-memory ZIP containing both TeX/PDF pairs and trusted image assets."""

    zip_name: str
    zip_bytes: bytes
    member_names: tuple[str, ...]

    @property
    def zip_mime(self) -> str:
        return "application/zip"


def _without_comments(source: str) -> str:
    cleaned: list[str] = []
    for line in source.splitlines():
        index = 0
        while True:
            index = line.find("%", index)
            if index < 0:
                break
            backslashes = 0
            cursor = index - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                line = line[:index]
                break
            index += 1
        cleaned.append(line)
    return "\n".join(cleaned)


def extract_tex_document(model_output: str, *, max_bytes: int = MAX_TEX_BYTES) -> str:
    """Extract one complete UTF-8 LaTeX document from a model response.

    Binary-looking prose and incomplete snippets are rejected instead of being
    rendered in the chat or offered as corrupt downloads.
    """
    if not isinstance(model_output, str):
        raise TexExtractionError("模型输出不是可处理的文本。")
    normalized = model_output.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    if _CONTROL_RE.search(normalized):
        raise TexExtractionError("模型输出含有二进制控制字符，未生成试卷文件。")
    marker = _BINARY_STREAM_RE.search(normalized)
    if marker:
        kind = "PDF 数据流" if marker.group(0).upper().startswith("%PDF-") else "ASCII85 压缩流"
        raise TexExtractionError(f"模型输出包含{kind}，不能作为 LaTeX 文本处理。")

    candidates = [
        match.group("body").strip()
        for match in _FENCE_RE.finditer(normalized)
        if _TEX_FENCE_INFO_RE.match(match.group("info"))
    ]
    candidates.append(normalized)
    document = ""
    for candidate in candidates:
        match = _DOCUMENT_RE.search(candidate)
        if match:
            document = match.group(0).strip() + "\n"
            break
    if not document:
        raise TexExtractionError("未找到完整的 LaTeX 文档（缺少 documentclass 或 document 环境）。")
    encoded = document.encode("utf-8")
    if len(encoded) > max_bytes:
        raise TexExtractionError(f"LaTeX 源文件超过 {max_bytes // 1024} KiB 限制。")
    return document


def _fence_tex_name(model_output: str, match: re.Match[str], previous_end: int) -> str:
    info_match = _TEX_FENCE_INFO_RE.match(match.group("info"))
    if not info_match:
        return ""
    locations = (info_match.group("rest"), match.group("body")[:240])
    for location in locations:
        found = _ANY_TEX_NAME_RE.search(location)
        if found:
            name = found.group(1).lower()
            if name not in _NAMED_TEX_FILES:
                raise TexExtractionError(f"不支持模型生成文件名：{name}")
            return name
    prefix = model_output[max(previous_end, match.start() - 240):match.start()]
    found_names = _ANY_TEX_NAME_RE.findall(prefix)
    if found_names:
        name = found_names[-1].lower()
        return name if name in _NAMED_TEX_FILES else ""
    return ""


def extract_named_tex_documents(
    model_output: str,
    *,
    required_names: tuple[str, ...] = ("main.tex", "answer.tex"),
) -> tuple[NamedTexDocument, ...]:
    """Extract independently fenced, explicitly named TeX documents.

    Accepted labels include `````latex main.tex``, ``filename=main.tex``, a
    ``main.tex`` heading immediately before the fence, or a filename comment at
    the beginning of the fence. Only main.tex and answer.tex are accepted.
    """
    if not isinstance(model_output, str):
        raise TexExtractionError("模型输出不是可处理的文本。")
    normalized = model_output.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    if _CONTROL_RE.search(normalized) or _BINARY_STREAM_RE.search(normalized):
        # Reuse the single-document path to preserve its specific safe message.
        extract_tex_document(normalized)

    required = tuple(str(name).strip().lower() for name in required_names)
    if (
        not required
        or len(set(required)) != len(required)
        or any(name not in _NAMED_TEX_FILES for name in required)
    ):
        raise ValueError("required_names 只能由 main.tex 与 answer.tex 组成且不能重复。")

    documents: dict[str, NamedTexDocument] = {}
    previous_end = 0
    for match in _FENCE_RE.finditer(normalized):
        if not _TEX_FENCE_INFO_RE.match(match.group("info")):
            previous_end = match.end()
            continue
        name = _fence_tex_name(normalized, match, previous_end)
        previous_end = match.end()
        if not name:
            continue
        if name in documents:
            raise TexExtractionError(f"模型输出重复声明了 {name}。")
        source = extract_tex_document(match.group("body"))
        documents[name] = NamedTexDocument(name=name, source=source)

    missing = [name for name in required if name not in documents]
    if missing:
        raise TexExtractionError("模型输出缺少独立文件：" + "、".join(missing))
    return tuple(documents[name] for name in required)


def _safe_relative_graphic(value: str) -> PurePosixPath:
    raw = value.strip()
    path = PurePosixPath(raw)
    if (
        not raw
        or not _SAFE_GRAPHIC_PATH_RE.fullmatch(raw)
        or path.is_absolute()
        or ":" in raw
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(part.startswith(".") for part in path.parts)
        or path.as_posix() != raw
    ):
        raise UnsafeTexError(f"图片路径不安全：{value!r}")
    if path.suffix and path.suffix.lower() not in _GRAPHICS_EXTENSIONS:
        raise UnsafeTexError(f"不支持的图片格式：{path.suffix}")
    return path


def validate_tex_document(source: str, *, allow_graphics: bool = False) -> tuple[PurePosixPath, ...]:
    """Validate the deliberately small TeX dialect used by the exam template."""
    if len(source.encode("utf-8")) > MAX_TEX_BYTES:
        raise UnsafeTexError("LaTeX 源文件过大。")
    active = _without_comments(source)
    banned = _BANNED_TEX_RE.search(active)
    if banned:
        token = banned.group(0).replace("\n", " ")[:60]
        raise UnsafeTexError(f"LaTeX 包含禁止的文件访问、宏构造或执行命令：{token}")

    class_matches = _CLASS_RE.findall(active)
    if len(class_matches) != 1:
        raise UnsafeTexError("LaTeX 必须且只能声明一个文档类。")
    document_class = class_matches[0].strip()
    if document_class not in _DOCUMENT_CLASSES:
        raise UnsafeTexError(f"不允许使用文档类：{document_class}")

    packages: set[str] = set()
    for package_group in _PACKAGE_RE.findall(active):
        for package in (part.strip() for part in package_group.split(",")):
            if not package or package not in _PACKAGES:
                raise UnsafeTexError(f"不允许使用 LaTeX 宏包：{package or '(空)'}")
            packages.add(package)

    tikz_commands = _TIKZ_COMMAND_RE.findall(active)
    if tikz_commands and "tikz" not in packages:
        raise UnsafeTexError("TikZ 绘图命令必须显式加载 tikz 宏包。")
    library_commands = len(re.findall(r"\\usetikzlibrary\b", active, re.I))
    library_groups = _TIKZ_LIBRARY_RE.findall(active)
    if library_commands != len(library_groups):
        raise UnsafeTexError("TikZ 库声明格式不受支持。")
    for library_group in library_groups:
        for library in (part.strip() for part in library_group.split(",")):
            if not library or library not in _TIKZ_LIBRARIES:
                raise UnsafeTexError(f"不允许使用 TikZ 库：{library or '(空)'}")
    banned_tikz = _BANNED_TIKZ_RE.search(active)
    if banned_tikz:
        token = banned_tikz.group(0).replace("\n", " ")[:60]
        raise UnsafeTexError(f"TikZ 包含禁止的外部文件或执行功能：{token}")

    graphic_commands = len(re.findall(r"\\includegraphics\b", active, re.I))
    graphic_values = _GRAPHICS_RE.findall(active)
    if graphic_commands != len(graphic_values):
        raise UnsafeTexError("图片命令格式不受支持。")
    if graphic_values and not allow_graphics:
        raise UnsafeTexError("当前请求未配置可信图片目录，不能引用外部图片。")
    if len(graphic_values) > 32:
        raise UnsafeTexError("单份试卷最多引用 32 张图片。")
    return tuple(_safe_relative_graphic(value) for value in graphic_values)


def stabilize_exam_tex_layout(source: str) -> str:
    """Remove one oversized, unbreakable frame that can trap TeX in an output loop.

    The standard renderer creates one independent frame per page and is left
    untouched.  Some local models instead wrap an entire nominal three-page,
    two-column paper in a single ``mdframed`` block.  TeX then repeatedly grows
    an overfull vbox and never completes.  Keeping the columns while dropping
    only that outer frame preserves all exam content and makes the document
    page-breakable.
    """
    text = str(source or "")
    blocks = tuple(_MDFRAMED_BLOCK_RE.finditer(text))
    if len(blocks) != 1:
        return text
    block = blocks[0]
    body = block.group("body")
    if not re.search(r"\\begin\s*\{\s*multicols\*?\s*\}", body, re.I):
        return text
    looks_multipage = bool(re.search(r"共\s*\$?\s*[2-9]\d*\s*\$?\s*页", text))
    if not looks_multipage and len(text.encode("utf-8")) < 4500 and text.count("\n") < 160:
        return text
    replacement = (
        "\n% Oversized outer mdframed removed server-side to allow page breaks.\n"
        + body
    )
    return text[:block.start()] + replacement + text[block.end():]


def find_tex_compiler(preferred: str | os.PathLike[str] | None = None) -> Path | None:
    """Return an allow-listed TeX executable without accepting shell fragments."""
    requested = str(preferred or os.getenv("PHYSICS_TEX_COMPILER", "")).strip()
    if requested:
        candidates: tuple[str | Path, ...] = (requested,)
    else:
        app_dir = Path(__file__).resolve().parent
        runtime_roots = (app_dir.parent, app_dir.parent.parent)
        local_tectonic = tuple(
            root / ".runtime" / "tectonic" / executable
            for root in runtime_roots
            for executable in ("tectonic", "tectonic.exe")
        )
        candidates = local_tectonic + _COMPILER_NAMES
    for candidate in candidates:
        if not candidate:
            continue
        base = Path(candidate).name.lower()
        if base.endswith(".exe"):
            base = base[:-4]
        if base not in _COMPILER_NAMES:
            continue
        candidate_path = Path(candidate).expanduser()
        located = (
            str(candidate_path.resolve())
            if candidate_path.is_file() and os.access(candidate_path, os.X_OK)
            else shutil.which(str(candidate))
        )
        if located:
            return Path(located).resolve()
    return None


def _compiler_output(raw: bytes | str | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw[-MAX_COMPILER_LOG_BYTES:]
    tail = raw[-MAX_COMPILER_LOG_BYTES:]
    encodings = ("utf-8", locale.getpreferredencoding(False), "gb18030")
    for encoding in dict.fromkeys(encodings):
        try:
            return tail.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return tail.decode("utf-8", errors="replace")


def _resolve_graphics(
    graphics: tuple[PurePosixPath, ...], asset_root: Path
) -> tuple[tuple[PurePosixPath, Path, PurePosixPath], ...]:
    try:
        trusted_root = asset_root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise UnsafeTexError("可信图片目录不存在或无法读取。") from exc
    if not trusted_root.is_dir():
        raise UnsafeTexError("可信图片目录不是有效文件夹。")
    total = 0
    resolved: list[tuple[PurePosixPath, Path, PurePosixPath]] = []
    seen_members: dict[PurePosixPath, Path] = {}
    for graphic in graphics:
        requested = trusted_root.joinpath(*graphic.parts)
        candidates = (requested,) if graphic.suffix else tuple(
            requested.with_suffix(extension) for extension in _GRAPHICS_EXTENSIONS
        )
        source = next((path.resolve() for path in candidates if path.is_file()), None)
        if source is None or not source.is_relative_to(trusted_root):
            raise UnsafeTexError(f"可信模板目录中不存在图片：{graphic.as_posix()}")
        size = source.stat().st_size
        archive_path = graphic if graphic.suffix else graphic.with_suffix(source.suffix.lower())
        previous = seen_members.get(archive_path)
        if previous is not None:
            if previous != source:
                raise UnsafeTexError(f"图片归档路径冲突：{archive_path.as_posix()}")
            continue
        total += size
        if size > 8 * 1024 * 1024 or total > 20 * 1024 * 1024:
            raise UnsafeTexError("试卷图片文件超过安全大小限制。")
        seen_members[archive_path] = source
        resolved.append((graphic, source, archive_path))
    return tuple(resolved)


def _copy_graphics(
    graphics: tuple[PurePosixPath, ...], asset_root: Path, workdir: Path
) -> None:
    for graphic, source, _archive_path in _resolve_graphics(graphics, asset_root):
        destination = workdir.joinpath(*graphic.parts)
        if not graphic.suffix:
            destination = destination.with_suffix(source.suffix.lower())
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _compiler_command(compiler: Path, workdir: Path, source_name: str) -> list[str]:
    name = compiler.stem.lower()
    if name == "tectonic":
        return [
            str(compiler), "-X", "compile", "--untrusted", "--only-cached",
            "--keep-logs", "--outdir", str(workdir), source_name,
        ]
    return [
        str(compiler),
        "-no-shell-escape",
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-file-line-error",
        "-recorder",
        f"-output-directory={workdir}",
        source_name,
    ]


def _tex_environment(workdir: Path) -> dict[str, str]:
    environment = os.environ.copy()
    texmf_home = workdir / "texmf-home"
    texmf_home.mkdir()
    default_cache = Path(__file__).resolve().parent.parent / ".runtime" / "tectonic-cache"
    cache_root = Path(
        os.getenv("PHYSICS_TEX_CACHE_DIR", str(default_cache))
    ).expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    environment.update({
        "TEXMFHOME": str(texmf_home),
        "TEXMFOUTPUT": str(workdir),
        "TEXINPUTS": f"{workdir}{os.pathsep}",
        "openin_any": "p",
        "openout_any": "p",
        "shell_escape": "0",
        "TECTONIC_UNTRUSTED_MODE": "1",
        "XDG_CACHE_HOME": str(cache_root),
        "SOURCE_DATE_EPOCH": "0",
    })
    return environment


def _workspace_size(workdir: Path) -> int:
    return sum(path.stat().st_size for path in workdir.rglob("*") if path.is_file())


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^0-9A-Za-z\u3400-\u9fff_-]+", "_", str(value or "")).strip("_-")
    return stem[:64] or "大学物理试卷"


def _compile_exam_document(
    source: str,
    *,
    tex_name: str,
    executable: Path,
    asset_root: str | os.PathLike[str] | None = None,
    work_root: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ExamArtifactBundle:
    source = stabilize_exam_tex_layout(source)
    graphics = validate_tex_document(source, allow_graphics=asset_root is not None)
    timeout = max(5, min(int(timeout_seconds), 120))
    stem = _safe_stem(Path(tex_name).stem)

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"physics-exam-{stem}-", dir=work_root) as temporary:
        workdir = Path(temporary).resolve()
        source_path = workdir / "exam.tex"
        source_bytes = source.encode("utf-8")
        source_path.write_bytes(source_bytes)
        if graphics:
            _copy_graphics(graphics, Path(asset_root), workdir)  # type: ignore[arg-type]

        command = _compiler_command(executable, workdir, source_path.name)
        try:
            completed = subprocess.run(
                command,
                cwd=workdir,
                env=_tex_environment(workdir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise TexCompilationError(f"LaTeX 编译超过 {timeout} 秒，已终止。") from exc
        except OSError as exc:
            raise TexCompilationError("无法启动服务器端 LaTeX 编译器。") from exc

        log = _compiler_output(completed.stdout)
        if _workspace_size(workdir) > MAX_WORKSPACE_BYTES:
            raise TexCompilationError("LaTeX 编译产生的临时文件超过安全限制。", log=log)
        pdf_path = workdir / "exam.pdf"
        if completed.returncode != 0 or not pdf_path.is_file():
            raise TexCompilationError("LaTeX 编译失败，请检查试卷公式或版式。", log=log)
        pdf_bytes = pdf_path.read_bytes()
        if not pdf_bytes.startswith(b"%PDF-"):
            raise TexCompilationError("编译器未生成有效的 PDF 文件。", log=log)
        if len(pdf_bytes) > MAX_PDF_BYTES:
            raise TexCompilationError("生成的 PDF 超过 8 MiB 限制。", log=log)

    return ExamArtifactBundle(
        tex_name=f"{stem}.tex",
        tex_bytes=source_bytes,
        pdf_name=f"{stem}.pdf",
        pdf_bytes=pdf_bytes,
        compiler=executable.stem,
        elapsed_seconds=time.monotonic() - started,
    )


def _artifact_work_root(work_root: str | os.PathLike[str] | None) -> Path | None:
    root = Path(work_root).expanduser().resolve() if work_root else None
    if root:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _available_compiler(compiler: str | os.PathLike[str] | None) -> Path:
    executable = find_tex_compiler(compiler)
    if executable is None:
        raise TexCompilerUnavailable(
            "服务器未安装可用的 Tectonic/XeLaTeX/LuaLaTeX/PDFLaTeX 编译器。"
        )
    return executable


def build_exam_artifacts(
    model_output: str,
    *,
    filename_stem: str = "大学物理试卷",
    compiler: str | os.PathLike[str] | None = None,
    asset_root: str | os.PathLike[str] | None = None,
    work_root: str | os.PathLike[str] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ExamArtifactBundle:
    """Backward-compatible single-document TeX/PDF builder."""
    return _compile_exam_document(
        extract_tex_document(model_output),
        tex_name=f"{_safe_stem(filename_stem)}.tex",
        executable=_available_compiler(compiler),
        asset_root=asset_root,
        work_root=_artifact_work_root(work_root),
        timeout_seconds=timeout_seconds,
    )


def build_exam_artifact_bundles(
    model_output: str,
    *,
    compiler: str | os.PathLike[str] | None = None,
    asset_root: str | os.PathLike[str] | None = None,
    work_root: str | os.PathLike[str] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ExamArtifactBundles:
    """Build independent main.tex/main.pdf and answer.tex/answer.pdf artifacts."""
    documents = extract_named_tex_documents(model_output)
    executable = _available_compiler(compiler)
    root = _artifact_work_root(work_root)
    items = tuple(
        _compile_exam_document(
            document.source,
            tex_name=document.name,
            executable=executable,
            asset_root=asset_root,
            work_root=root,
            timeout_seconds=timeout_seconds,
        )
        for document in documents
    )
    return ExamArtifactBundles(items)


def _safe_archive_member(value: str) -> str:
    raw = str(value or "").strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or ":" in raw
        or _CONTROL_RE.search(raw)
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(part.startswith(".") for part in path.parts)
        or path.as_posix() != raw
    ):
        raise UnsafeTexError(f"ZIP 成员路径不安全：{value!r}")
    return path.as_posix()


def _zip_member(name: str, data: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(_safe_archive_member(name), date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info, data


def build_exam_download_archive(
    bundles: ExamArtifactBundles | tuple[ExamArtifactBundle, ...],
    *,
    asset_root: str | os.PathLike[str] | None = None,
    filename_stem: str = "大学物理试卷完整包",
    minimum_graphics: int = 1,
) -> ExamDownloadArchive | None:
    """Package compiled documents and their trusted local images into one ZIP.

    The default returns ``None`` for image-free exams because the four normal
    TeX/PDF download buttons remain manageable.  Once an external image is
    referenced, the archive preserves its relative path so the downloaded TeX
    compiles after extraction.  Callers may pass ``minimum_graphics=0`` when an
    explicit all-in-one archive is desired even without images.
    """
    threshold = int(minimum_graphics)
    if threshold < 0:
        raise ValueError("minimum_graphics 不能为负数。")
    items = tuple(bundles)
    if not items:
        return None

    trusted_root = Path(asset_root).expanduser() if asset_root is not None else None
    graphics: list[PurePosixPath] = []
    entries: dict[str, bytes] = {}

    def add_entry(name: str, data: bytes) -> None:
        member = _safe_archive_member(name)
        existing = entries.get(member)
        if existing is not None and existing != data:
            raise UnsafeTexError(f"ZIP 成员文件名冲突：{member}")
        entries.setdefault(member, data)

    for bundle in items:
        try:
            source = bundle.tex_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise UnsafeTexError(f"{bundle.tex_name} 不是有效 UTF-8 文本。") from exc
        if len(bundle.tex_bytes) > MAX_TEX_BYTES:
            raise UnsafeTexError(f"{bundle.tex_name} 超过 TeX 大小限制。")
        if (
            len(bundle.pdf_bytes) > MAX_PDF_BYTES
            or not bundle.pdf_bytes.startswith(b"%PDF-")
        ):
            raise UnsafeTexError(f"{bundle.pdf_name} 不是可归档的有效 PDF。")
        graphics.extend(
            validate_tex_document(source, allow_graphics=trusted_root is not None)
        )
        add_entry(bundle.tex_name, bundle.tex_bytes)
        add_entry(bundle.pdf_name, bundle.pdf_bytes)

    resolved_graphics = (
        _resolve_graphics(tuple(graphics), trusted_root)
        if graphics and trusted_root is not None
        else ()
    )
    if len(resolved_graphics) < threshold:
        return None
    for _reference, source, archive_path in resolved_graphics:
        add_entry(archive_path.as_posix(), source.read_bytes())

    if sum(len(data) for data in entries.values()) > MAX_WORKSPACE_BYTES:
        raise UnsafeTexError("试卷 ZIP 的未压缩文件总量超过安全限制。")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", allowZip64=False) as archive:
        for name, data in entries.items():
            info, payload = _zip_member(name, data)
            archive.writestr(info, payload)
    payload = buffer.getvalue()
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise UnsafeTexError("试卷 ZIP 超过 8 MiB 限制。")
    return ExamDownloadArchive(
        zip_name=f"{_safe_stem(filename_stem)}.zip",
        zip_bytes=payload,
        member_names=tuple(entries),
    )
