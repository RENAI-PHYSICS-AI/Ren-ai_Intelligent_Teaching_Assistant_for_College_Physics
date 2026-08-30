from __future__ import annotations

import os
import re
from collections.abc import Iterable

from exam_artifacts import (
    DEFAULT_TIMEOUT_SECONDS,
    ExamArtifactBundle,
    ExamArtifactError,
    build_exam_artifacts,
    extract_named_tex_documents,
    stabilize_exam_tex_layout,
    validate_tex_document,
)


_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$")
_UNORDERED_RE = re.compile(r"^\s*[-+*]\s+(.+?)\s*$")
_ORDERED_RE = re.compile(r"^\s*\d+[.)、]\s+(.+?)\s*$")
_RULE_RE = re.compile(r"^\s*(?:-{3,}|_{3,}|\*{3,})\s*$")
_SAFE_STEM_RE = re.compile(r"[^0-9A-Za-z\u3400-\u9fff_-]+")
_ANSWER_SUFFIX_RE = re.compile(r"(?:[_-]?参考答案|[_-]?答案)$")
_LEGACY_LINEBREAK_RE = re.compile(
    r"\\\r?\n\$\$\r?\n\s*([0-9]+(?:\.[0-9]+)?\s*(?:pt|em|ex|mm|cm))\]",
    re.I,
)
_ANSWER_FRAME_RE = re.compile(
    r"\\begin\s*\{\s*mdframed\s*\}(?:\s*\[[^]]*\])?"
    r"(?P<body>.*?)"
    r"\\end\s*\{\s*mdframed\s*\}",
    re.I | re.S,
)
_MULTICOLS_BEGIN_RE = re.compile(r"\\begin\s*\{\s*multicols\*?\s*\}", re.I)
_MATH_SPAN_RE = re.compile(
    r"\$\$(?P<display>.+?)\$\$|(?<!\$)\$(?!\$)(?P<inline>[^\n$]+?)\$(?!\$)",
    re.S,
)
_MATH_COMMAND_RE = re.compile(r"\\([A-Za-z]+|.)", re.S)
_MATH_ENVIRONMENT_RE = re.compile(r"\\(begin|end)\s*\{([A-Za-z*]+)\}")
_SAFE_MATH_ENVIRONMENTS = frozenset({
    "aligned", "alignedat", "gathered", "cases", "matrix", "pmatrix",
    "bmatrix", "vmatrix", "Vmatrix", "smallmatrix",
})
_SAFE_MATH_COMMANDS = frozenset({
    "begin", "end", "frac", "dfrac", "tfrac", "sqrt", "sum", "prod",
    "int", "iint", "iiint", "oint", "lim", "max", "min", "sup", "inf",
    "sin", "cos", "tan", "cot", "sec", "csc", "sinh", "cosh", "tanh",
    "ln", "log", "exp", "det", "gcd", "left", "right", "middle", "big",
    "Big", "bigg", "Bigg", "cdot", "times", "div", "pm", "mp", "ast",
    "star", "circ", "bullet", "oplus", "otimes", "approx", "sim", "simeq",
    "equiv", "neq", "ne", "le", "leq", "ge", "geq", "ll", "gg",
    "propto", "in", "notin", "ni", "subset", "subseteq", "supset",
    "supseteq", "parallel", "perp", "to", "mapsto", "rightarrow",
    "leftarrow", "leftrightarrow", "Rightarrow", "Leftarrow", "Leftrightarrow",
    "uparrow", "downarrow", "partial", "nabla", "infty", "forall", "exists",
    "therefore", "because", "alpha", "beta", "gamma", "delta", "epsilon",
    "varepsilon", "zeta", "eta", "theta", "vartheta", "iota", "kappa",
    "lambda", "mu", "nu", "xi", "pi", "varpi", "rho", "varrho", "sigma",
    "varsigma", "tau", "upsilon", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon",
    "Phi", "Psi", "Omega", "mathrm", "mathbf", "mathit", "mathsf", "mathtt",
    "mathcal", "mathbb", "text", "operatorname", "overline", "underline",
    "hat", "widehat", "bar", "vec", "dot", "ddot", "tilde", "widetilde",
    "overbrace", "underbrace", "overrightarrow", "overleftarrow", "boxed",
    "displaystyle", "textstyle", "scriptstyle", "scriptscriptstyle", "quad",
    "qquad", "enspace", "hbar", "ell", "Re", "Im", "angle", "degree",
})
_SAFE_MATH_CONTROL_SYMBOLS = frozenset({
    "\\", ",", ";", ":", "!", " ", "{", "}", "|", "%", "#", "&", "_",
})
_TEX_ESCAPE = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "^": r"\textasciicircum{}",
    "~": r"\textasciitilde{}",
}


def _plain_text(value: object) -> str:
    text = str(value or "").replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_RE.sub(" ", text)


def _tex_escape(value: object) -> str:
    """Escape every model-controlled character before adding trusted markup."""
    return "".join(_TEX_ESCAPE.get(char, char) for char in _plain_text(value))


def _safe_math_expression(value: str) -> bool:
    """Accept a small mathematical TeX subset, never document-level commands."""
    if not value or len(value) > 8000 or _CONTROL_RE.search(value):
        return False
    if any(char in value for char in ("$", "`", "\x00")):
        return False
    # Raw TeX comment/parameter markers can change the surrounding document.
    if re.search(r"(?<!\\)[%#]", value):
        return False

    depth = 0
    escaped = False
    for char in value:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    if escaped or depth:
        return False

    environments: list[str] = []
    environment_commands: set[int] = set()
    for match in _MATH_ENVIRONMENT_RE.finditer(value):
        action, environment = match.groups()
        if environment not in _SAFE_MATH_ENVIRONMENTS:
            return False
        environment_commands.add(match.start())
        if action == "begin":
            environments.append(environment)
        elif not environments or environments.pop() != environment:
            return False
    if environments:
        return False
    if "&" in value and not environment_commands:
        return False

    for match in _MATH_COMMAND_RE.finditer(value):
        command = match.group(1)
        if command.isalpha():
            if command not in _SAFE_MATH_COMMANDS:
                return False
            if command in {"begin", "end"} and match.start() not in environment_commands:
                return False
        elif command not in _SAFE_MATH_CONTROL_SYMBOLS:
            return False
    return True


def _protect_safe_math(value: str) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}
    # The token deliberately contains no TeX-special characters because it
    # passes through the normal escaping path before trusted math is restored.
    prefix = "\ue000PHYSICSMATH"
    while prefix in value:
        prefix += "X"

    def replace(match: re.Match[str]) -> str:
        body = match.group("display") if match.group("display") is not None else match.group("inline")
        if body is None or not _safe_math_expression(body.strip()):
            return match.group(0)
        token = f"{prefix}{len(replacements)}\ue001"
        if match.group("display") is not None:
            replacements[token] = f"\\[\n{body.strip()}\n\\]"
        else:
            replacements[token] = f"${body.strip()}$"
        return token

    return _MATH_SPAN_RE.sub(replace, value), replacements


def _restore_safe_math(value: str, replacements: dict[str, str]) -> str:
    for token, expression in replacements.items():
        value = value.replace(token, expression)
    return value


def _close_list(lines: list[str], current: str | None) -> None:
    if current:
        lines.append(f"\\end{{{current}}}")


def _render_answer_body(answer_text: str) -> str:
    protected_text, math_replacements = _protect_safe_math(_plain_text(answer_text))
    output: list[str] = []
    current_list: str | None = None
    in_code_fence = False

    for raw_line in protected_text.split("\n"):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            _close_list(output, current_list)
            current_list = None
            in_code_fence = not in_code_fence
            continue
        if not stripped:
            _close_list(output, current_list)
            current_list = None
            output.append(r"\par\smallskip")
            continue

        heading = None if in_code_fence else _HEADING_RE.match(raw_line)
        if heading:
            _close_list(output, current_list)
            current_list = None
            level = len(heading.group(1))
            command = "section" if level == 1 else "subsection" if level == 2 else "subsubsection"
            output.append(f"\\{command}*{{{_tex_escape(heading.group(2))}}}")
            continue

        if not in_code_fence and _RULE_RE.match(raw_line):
            _close_list(output, current_list)
            current_list = None
            output.append(r"\par\smallskip\hrule\smallskip")
            continue

        unordered = None if in_code_fence else _UNORDERED_RE.match(raw_line)
        ordered = None if in_code_fence else _ORDERED_RE.match(raw_line)
        wanted_list = "itemize" if unordered else "enumerate" if ordered else None
        if wanted_list:
            if current_list != wanted_list:
                _close_list(output, current_list)
                current_list = wanted_list
                output.append(f"\\begin{{{wanted_list}}}")
            item = unordered.group(1) if unordered else ordered.group(1)  # type: ignore[union-attr]
            output.append(f"\\item {_tex_escape(item)}")
            continue

        _close_list(output, current_list)
        current_list = None
        escaped = _tex_escape(raw_line)
        if in_code_fence:
            # The offline Tectonic bundle does not contain every 8pt Latin
            # Modern Mono metric.  A safe fallback must remain compilable even
            # when displaying rejected model TeX, so use the cached roman face.
            output.append(f"{{\\rmfamily {escaped}}}\\par")
        elif stripped.startswith(">"):
            quote = stripped[1:].lstrip()
            output.append(f"\\begin{{quote}}{_tex_escape(quote)}\\end{{quote}}")
        else:
            output.append(f"{escaped}\\par")

    _close_list(output, current_list)
    if not any(line and line != r"\par\smallskip" for line in output):
        return r"（未提供答案内容）\par"
    return _restore_safe_math("\n".join(output), math_replacements)


def render_answer_tex(answer_text: str, *, title: str = "大学物理参考答案") -> str:
    """Render untrusted Markdown/plain text as a standalone safe ``ctexart``.

    Only a small, server-owned subset of Markdown structure is recognized.
    Ordinary model text is fully escaped; formulas are preserved only when all
    TeX controls belong to the server-owned mathematical allow-list.  Unsafe
    commands remain visible text and cannot execute during compilation.
    """
    safe_title = _tex_escape(title).strip() or "大学物理参考答案"
    body = _render_answer_body(answer_text)
    return (
        "\\documentclass[UTF8,a4paper,12pt]{ctexart}\n"
        "\\usepackage[top=1.8cm,bottom=1.8cm,left=2.0cm,right=2.0cm]{geometry}\n"
        "\\usepackage{amsmath,amssymb}\n"
        "\\usepackage{enumitem}\n"
        "\\setlist{leftmargin=2.2em,itemsep=0.35em,topsep=0.35em}\n"
        "\\setlength{\\parindent}{2em}\n"
        "\\setlength{\\parskip}{0.35em}\n"
        "\\pagestyle{plain}\n"
        "\\raggedbottom\n"
        "\\begin{document}\n"
        f"\\begin{{center}}{{\\heiti\\LARGE {safe_title}}}\\end{{center}}\n"
        "\\vspace{0.8em}\n"
        f"{body}\n"
        "\\end{document}\n"
    )


def answer_filename_stem(pdf_names: Iterable[str] | str | None) -> str:
    """Return a deterministic safe answer filename derived from uploaded PDFs."""
    if isinstance(pdf_names, str):
        candidates = [pdf_names]
    else:
        candidates = list(pdf_names or [])

    stems: list[str] = []
    for value in candidates:
        name = str(value or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
        if not name:
            continue
        stem = name[:-4] if name.lower().endswith(".pdf") else name
        stem = _ANSWER_SUFFIX_RE.sub("", stem).strip(" _-")
        stem = _SAFE_STEM_RE.sub("_", stem).strip("_-")[:48]
        if stem and stem not in stems:
            stems.append(stem)

    if not stems:
        return "大学物理参考答案"
    if len(stems) == 1:
        return f"{stems[0]}_参考答案"
    return f"{stems[0]}_等{len(stems)}份_参考答案"


def _safe_named_answer_tex(answer_text: str) -> str | None:
    """Return one explicitly named, complete and validated ``answer.tex``.

    A model-authored document is used only through the existing exam TeX
    extraction and allow-list validation pipeline.  Missing, incomplete or
    unsafe documents deliberately fall back to the server-owned Markdown
    renderer instead of weakening that policy or exposing raw TeX commands.
    """
    try:
        documents = extract_named_tex_documents(
            answer_text,
            required_names=("answer.tex",),
        )
        # Older chat history passed complete TeX fences through the Markdown
        # delimiter normalizer.  A row break such as ``\\[2pt]`` then became
        # ``\\`` + newline + ``$$`` + newline + ``2pt]``.  Repair only this
        # tightly scoped, unit-bearing legacy pattern before validation.
        source = _LEGACY_LINEBREAK_RE.sub(r"\\\\[\1]", documents[0].source)
        source = stabilize_exam_tex_layout(source)
        # A generated answer is often much taller than the three-page question
        # template it copied.  ``mdframed`` around ``multicols`` cannot split
        # reliably in Tectonic and can enter an endless overfull-vbox loop.
        # Remove only those outer answer frames; the columns, page headers,
        # questions, solutions and explicit page breaks remain intact.
        source = _ANSWER_FRAME_RE.sub(
            lambda match: (
                "\n% Answer frame removed server-side to allow page breaks.\n"
                + match.group("body")
                if _MULTICOLS_BEGIN_RE.search(match.group("body"))
                else match.group(0)
            ),
            source,
        )
        validate_tex_document(source)
    except ExamArtifactError:
        return None
    return source


def build_answer_artifact_bundle(
    answer_text: str,
    *,
    pdf_names: Iterable[str] | str | None = None,
    title: str = "大学物理参考答案",
    compiler: str | os.PathLike[str] | None = None,
    work_root: str | os.PathLike[str] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ExamArtifactBundle:
    """Safely typeset one answer and compile its editable TeX and PDF files."""
    source = _safe_named_answer_tex(answer_text)
    if source is None:
        source = render_answer_tex(answer_text, title=title)
    return build_exam_artifacts(
        source,
        filename_stem=answer_filename_stem(pdf_names),
        compiler=compiler,
        work_root=work_root,
        timeout_seconds=timeout_seconds,
    )
