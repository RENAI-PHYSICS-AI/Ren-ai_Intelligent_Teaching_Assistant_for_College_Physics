from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Final


MAX_BLUEPRINT_BYTES: Final = 512 * 1024
SCHEMA_VERSION: Final = 1
STANDARD_COUNTS: Final = {
    "single_choice": 10,
    "fill_blank": 5,
    "calculation": 5,
}
STANDARD_SCORES: Final = {
    "single_choice": 3,
    "fill_blank": 4,
    "calculation": 10,
}
QUESTION_TYPES: Final = tuple(STANDARD_COUNTS)
STEM_LENGTH_LIMITS: Final = {
    "single_choice": 160,
    "fill_blank": 180,
    "calculation": 320,
}
OPTION_LENGTH_LIMIT: Final = 90
CHOICE_LAYOUT_BUDGET: Final = 1400
FILL_LAYOUT_BUDGET: Final = 650
PAGE_TWO_LEFT_LAYOUT_BUDGET: Final = 800
PAGE_THREE_LEFT_LAYOUT_BUDGET: Final = 520

EXAM_BLUEPRINT_JSON_SCHEMA: Final = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "kind", "summary", "title", "course",
        "academic_year", "term", "exam_type", "exam_date",
        "duration_minutes", "total_score", "questions",
    ],
    "properties": {
        "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
        "kind": {"type": "string", "enum": ["message", "exam"]},
        "summary": {"type": "string", "minLength": 1, "maxLength": 800},
        "title": {"type": "string", "maxLength": 120},
        "course": {"type": "string", "maxLength": 60},
        "academic_year": {"type": "string", "maxLength": 40},
        "term": {"type": "string", "maxLength": 40},
        "exam_type": {"type": "string", "maxLength": 40},
        "exam_date": {"type": "string", "maxLength": 40},
        "duration_minutes": {"type": "integer", "minimum": 0, "maximum": 360},
        "total_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "questions": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "number", "type", "score", "title", "stem", "options", "answer",
                    "analysis", "rubric", "chapter", "difficulty",
                ],
                "properties": {
                    "number": {"type": "integer", "minimum": 1, "maximum": 20},
                    "type": {
                        "type": "string",
                        "enum": ["single_choice", "fill_blank", "calculation"],
                    },
                    "score": {"type": "integer", "minimum": 1, "maximum": 10},
                    "title": {"type": "string", "maxLength": 80},
                    "stem": {"type": "string", "minLength": 8, "maxLength": 320},
                    "options": {
                        "type": "array",
                        "maxItems": 4,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1, "maxLength": 90},
                    },
                    "answer": {"type": "string", "minLength": 1, "maxLength": 1200},
                    "analysis": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "rubric": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 10,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["points", "criterion"],
                            "properties": {
                                "points": {"type": "integer", "minimum": 1, "maximum": 10},
                                "criterion": {
                                    "type": "string", "minLength": 1, "maxLength": 500,
                                },
                            },
                        },
                    },
                    "chapter": {"type": "string", "maxLength": 100},
                    "difficulty": {"type": "string", "maxLength": 30},
                },
            },
        },
    },
}

EXAM_BLUEPRINT_FALLBACK_INSTRUCTIONS: Final = """你正在执行教研考试的结构化安全回退。只返回一个普通 UTF-8 JSON 对象，不要使用 Markdown 代码块，不要输出解释性前后缀。
顶层所有字段必须存在：schema_version=1；kind 为 exam 或 message；summary 为简短中文说明；以及 title、course、academic_year、term、exam_type、exam_date、duration_minutes、total_score、questions。
如果本轮只是教研说明而不生成整卷：kind=message，其他元数据用空字符串或0，questions=[]。
如果生成或修改整卷：kind=exam，严格采用“25262大物1补考”的三类题结构：questions 恰好20项且 number 全局连续1～20；第1～10题为 single_choice、每题3分、options恰好四项、answer只能是A/B/C/D；第11～15题为 fill_blank、每题4分且stem中恰有两个[[BLANK]]（每空2分）、options=[]；第16～20题为 calculation、每题10分、options=[]。总分严格100分。
每题都必须包含 title 字段：选择题和填空题的 title 必须为空字符串；五道计算题的 title 必须分别是完整、简明的大题栏目名，例如“电学计算题”或“质点动力学计算题”，不得包含“三、”等大题序号或“共10分”等分值文字。五道计算题的知识点顺序可根据组卷需要调整，服务器按 questions 中第16～20题的当前顺序依次排为大题三、四、五、六、七。
题干必须简洁以保证三页试卷版面和编译安全：single_choice 每题最多160字，每个选项最多90字；fill_blank 每题最多180字；calculation 每题最多320字。十道选择题的题干与选项合计不得超过1400字，五道填空题题干合计不得超过650字；不要用冗长背景叙述挤占学生答题空间。
元数据只能使用提问者明确提供的信息。未提供考试日期时 exam_date 必须为空字符串，严禁猜测或编造日期。exam_type 为补考时 title 必须含“补考”；exam_type 不是补考时 title 严禁含“补考”。大学物理1和大学物理A的试题、答案、解析与评分细则均不得涉及相对论主题。
每题都必须包含普通文本 title、stem、answer、analysis、rubric、chapter、difficulty；rubric 是 points 与 criterion 对象数组，points 必须为整数且逐题合计等于score。为套用“25262大物1补考/answer.tex”的固定答案版式，选择题 answer 只能填写选项字母，填空题 answer 应按两空顺序给出简短答案，计算题 analysis 必须包含完整但精炼的推导，rubric 的每个 criterion 必须按解题顺序写成可直接显示的独立给分步骤且不得自行附加分值文字。每道选择题的四个选项在忽略大小写、空格、标点和选项序号后仍须互不相同，不得用仅修改标点、空白或序号的方式制造伪差异。选择题答案分布应尽量让A/B/C/D各出现2～3次，并避免连续多题使用同一答案；答案分布属于命题质量偏好，不得为了调整字母分布而改变题目物理语义。不得出现重复或仅替换数值的近重复题。
所有字符串只能是普通可打印文本；公式请用Unicode和线性写法表达。禁止任何LaTeX命令、Markdown围栏、HTML、PDF、Base64、ASCII85、PostScript、文件路径、压缩流或二进制数据。不要自行声称已编译文件；服务器会校验JSON并生成TeX与PDF。"""

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BINARY_RE = re.compile(
    r"(?:%PDF-\d|(?:^|\n)(?:xref|startxref|endstream)\b|<~[!-u\s]{16,}~>)",
    re.I | re.S,
)
_JSON_FENCE_RE = re.compile(r"^```\s*json\s*\r?\n(?P<body>.*)\r?\n```\s*$", re.I | re.S)
_DUPLICATE_NORMALIZE_RE = re.compile(r"[^0-9a-z\u3400-\u9fff]+", re.I)
_OPTION_LABEL_PREFIX_RE = re.compile(
    r"^\s*(?:选项\s*)?[A-DＡ-Ｄ]\s*[.．、:：)）]\s*",
    re.I,
)
_MAKEUP_RE = re.compile(r"补\s*考")
_COURSE_WITHOUT_RELATIVITY_RE = re.compile(
    r"(?:大学物理|大物)(?:1(?!\d)|[aAＡ](?![a-zA-Z])|Ⅰ|I(?![a-zA-Z]))",
    re.I,
)
_RELATIVITY_TOPIC_RE = re.compile(
    r"(?:狭义相对论|广义相对论|相对论(?:力学|效应|性)?|"
    r"洛伦兹变换|时间膨胀|钟慢效应|长度收缩|尺缩效应|"
    r"相对论性(?:质量|动量|能量)|质能(?:关系|方程|等价)|闵可夫斯基|"
    r"同时性的相对性|双生子佯谬|光速不变原理|"
    r"E\s*=\s*mc(?:\^?2|²)|special\s+relativity|general\s+relativity|"
    r"Lorentz\s+transformation|time\s+dilation|length\s+contraction|"
    r"mass[-\s]*energy\s+equivalence)",
    re.I,
)
_TOP_LEVEL_KEYS: Final = frozenset(EXAM_BLUEPRINT_JSON_SCHEMA["properties"])
_QUESTION_KEYS: Final = frozenset(
    EXAM_BLUEPRINT_JSON_SCHEMA["properties"]["questions"]["items"]["properties"]
)
_RUBRIC_KEYS: Final = frozenset({"points", "criterion"})
_OPTION_REPAIR_KEYS: Final = frozenset({"repairs"})
_OPTION_REPAIR_ITEM_KEYS: Final = frozenset({"number", "options"})
_TARGETED_REPAIR_KEYS: Final = frozenset({"choice_repairs", "fill_stem_repairs"})
_TARGETED_CHOICE_REPAIR_ITEM_KEYS: Final = frozenset({"number", "options"})
_TARGETED_FILL_REPAIR_ITEM_KEYS: Final = frozenset({"number", "stem"})


class ExamBlueprintError(ValueError):
    """A safe, user-presentable structured-exam validation failure."""


def _require_exact_keys(value: dict, allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(allowed - set(value))
    if unknown:
        raise ExamBlueprintError(f"{label} 含有未允许字段：{'、'.join(unknown)}")
    if missing:
        raise ExamBlueprintError(f"{label} 缺少必填字段：{'、'.join(missing)}")


@dataclass(frozen=True, slots=True)
class RubricItem:
    points: int
    criterion: str


@dataclass(frozen=True, slots=True)
class ExamQuestion:
    number: int
    question_type: str
    score: int
    title: str
    stem: str
    options: tuple[str, ...]
    answer: str
    analysis: str
    rubric: tuple[RubricItem, ...]
    chapter: str = ""
    difficulty: str = ""


@dataclass(frozen=True, slots=True)
class ExamBlueprint:
    kind: str
    summary: str
    title: str = ""
    course: str = ""
    academic_year: str = ""
    term: str = ""
    exam_type: str = ""
    exam_date: str = ""
    duration_minutes: int = 0
    total_score: int = 0
    questions: tuple[ExamQuestion, ...] = ()


@dataclass(frozen=True, slots=True)
class ChoiceOptionRepairSpec:
    """Immutable bounds for repairing duplicate distractors in one question."""

    number: int
    stem: str
    options: tuple[str, str, str, str]
    answer: str
    analysis: str
    editable_labels: tuple[str, ...]
    keeper_labels: tuple[str, ...]
    locked_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FillBlankStemRepairSpec:
    """Immutable context for repairing one invalid double-blank stem."""

    number: int
    stem: str
    answer: str
    analysis: str
    chapter: str
    difficulty: str


@dataclass(frozen=True, slots=True)
class TargetedExamRepairPlan:
    """All and only the local repairs authorized for one otherwise-valid exam."""

    choice_repairs: tuple[ChoiceOptionRepairSpec, ...]
    fill_stem_repairs: tuple[FillBlankStemRepairSpec, ...]


def _reject_constant(value: str) -> None:
    raise ExamBlueprintError(f"JSON 不允许使用 {value}。")


def _object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ExamBlueprintError(f"JSON 字段重复：{key}")
        result[key] = value
    return result


def _plain_text(
    value: object,
    field: str,
    *,
    minimum: int = 1,
    maximum: int = 2000,
) -> str:
    if not isinstance(value, str):
        raise ExamBlueprintError(f"{field} 必须是普通 UTF-8 文本。")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ExamBlueprintError(f"{field} 不是有效 UTF-8 文本。") from exc
    if _CONTROL_RE.search(value):
        raise ExamBlueprintError(f"{field} 含有二进制控制字符。")
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) < minimum:
        raise ExamBlueprintError(f"{field} 不能为空。")
    if len(normalized) > maximum:
        raise ExamBlueprintError(f"{field} 超过 {maximum} 字符限制。")
    return normalized


def _optional_text(value: object, field: str, *, maximum: int) -> str:
    if value in (None, ""):
        return ""
    return _plain_text(value, field, maximum=maximum)


def _positive_integer(value: object, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExamBlueprintError(f"{field} 必须是整数。")
    if value <= 0 or value > maximum:
        raise ExamBlueprintError(f"{field} 必须在 1～{maximum} 之间。")
    return value


def _parse_json(text: str) -> dict:
    if not isinstance(text, str):
        raise ExamBlueprintError("模型输出不是普通文本。")
    normalized = text.lstrip("\ufeff").strip()
    if len(normalized.encode("utf-8", errors="ignore")) > MAX_BLUEPRINT_BYTES:
        raise ExamBlueprintError("结构化命题 JSON 超过 512 KiB 限制。")
    if _CONTROL_RE.search(normalized) or _BINARY_RE.search(normalized):
        raise ExamBlueprintError("模型输出包含 PDF、ASCII85 或二进制文件流。")
    fence = _JSON_FENCE_RE.fullmatch(normalized)
    if fence:
        normalized = fence.group("body").strip()
    if not normalized.startswith("{") or not normalized.endswith("}"):
        raise ExamBlueprintError("模型输出必须是单个 JSON 对象，不能包含说明文字或文件流。")
    try:
        data = json.loads(
            normalized,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ExamBlueprintError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ExamBlueprintError("模型输出不是完整、合法的 UTF-8 JSON。") from exc
    if not isinstance(data, dict):
        raise ExamBlueprintError("结构化命题的顶层必须是 JSON 对象。")
    return data


def _parse_rubric(value: object, score: int, number: int) -> tuple[RubricItem, ...]:
    if not isinstance(value, list) or not value:
        raise ExamBlueprintError(f"第 {number} 题必须给出非空 rubric 数组。")
    result = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise ExamBlueprintError(f"第 {number} 题 rubric[{index}] 必须是对象。")
        _require_exact_keys(item, _RUBRIC_KEYS, f"第 {number} 题 rubric[{index}]")
        points = _positive_integer(
            item.get("points"), f"第 {number} 题 rubric[{index}].points", maximum=score
        )
        criterion = _plain_text(
            item.get("criterion"),
            f"第 {number} 题 rubric[{index}].criterion",
            maximum=500,
        )
        result.append(RubricItem(points=points, criterion=criterion))
    if sum(item.points for item in result) != score:
        raise ExamBlueprintError(f"第 {number} 题评分点合计不等于该题 {score} 分。")
    return tuple(result)


def _option_key(value: str) -> str:
    without_label = _OPTION_LABEL_PREFIX_RE.sub("", value, count=1)
    return _DUPLICATE_NORMALIZE_RE.sub("", without_label.lower())


def _duplicate_option_groups(options: tuple[str, ...]) -> tuple[tuple[int, ...], ...]:
    groups: dict[str, list[int]] = {}
    for index, option in enumerate(options):
        groups.setdefault(_option_key(option), []).append(index)
    return tuple(tuple(indices) for indices in groups.values() if len(indices) > 1)


def _parse_options(
    value: object,
    number: int,
    *,
    allow_duplicates: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) != 4:
        raise ExamBlueprintError(f"第 {number} 题必须恰有 A、B、C、D 四个选项。")
    options = []
    for index, item in enumerate(value):
        label = chr(ord("A") + index)
        options.append(
            _plain_text(
                item,
                f"第 {number} 题选项 {label}",
                maximum=OPTION_LENGTH_LIMIT,
            )
        )
    parsed = tuple(options)
    if _duplicate_option_groups(parsed) and not allow_duplicates:
        raise ExamBlueprintError(f"第 {number} 题存在重复选项。")
    return parsed


def _parse_question(
    value: object,
    expected_number: int,
    expected_type: str,
    *,
    allow_duplicate_options: bool = False,
    allow_invalid_fill_blank_markers: bool = False,
) -> ExamQuestion:
    if not isinstance(value, dict):
        raise ExamBlueprintError(f"第 {expected_number} 题必须是 JSON 对象。")
    _require_exact_keys(value, _QUESTION_KEYS, f"第 {expected_number} 题")
    number = _positive_integer(
        value.get("number"), f"第 {expected_number} 题 number", maximum=20
    )
    if number != expected_number:
        raise ExamBlueprintError(f"题号必须连续；此处应为第 {expected_number} 题。")
    question_type = str(value.get("type") or "").strip().lower()
    if question_type != expected_type:
        raise ExamBlueprintError(
            f"第 {number} 题类型应为 {expected_type}，实际为 {value.get('type')!r}。"
        )
    score = _positive_integer(value.get("score"), f"第 {number} 题 score", maximum=100)
    if score != STANDARD_SCORES[question_type]:
        raise ExamBlueprintError(
            f"第 {number} 题必须为 {STANDARD_SCORES[question_type]} 分。"
        )
    title = _optional_text(value.get("title"), f"第 {number} 题 title", maximum=80)
    if question_type == "calculation":
        if not title:
            raise ExamBlueprintError(f"第 {number} 题必须给出独立的计算题 title。")
        if re.match(r"^[一二三四五六七八九十\d]+[\s、．.]+", title):
            raise ExamBlueprintError(f"第 {number} 题 title 不得自带大题序号。")
        if re.search(r"(?:共|本题)?\s*10\s*分", title):
            raise ExamBlueprintError(f"第 {number} 题 title 不得自带分值。")
    elif title:
        raise ExamBlueprintError(f"第 {number} 题不是计算题，title 必须为空字符串。")
    stem = _plain_text(
        value.get("stem"),
        f"第 {number} 题 stem",
        maximum=STEM_LENGTH_LIMITS[question_type],
    )
    if question_type == "fill_blank":
        blank_count = stem.count("[[BLANK]]")
        if blank_count != 2 and not allow_invalid_fill_blank_markers:
            raise ExamBlueprintError(f"第 {number} 题必须且只能包含两个 [[BLANK]]。")
    options = (
        _parse_options(
            value.get("options"),
            number,
            allow_duplicates=allow_duplicate_options,
        )
        if question_type == "single_choice"
        else ()
    )
    if question_type != "single_choice" and value.get("options") not in (None, []):
        raise ExamBlueprintError(f"第 {number} 题不是选择题，不应包含 options。")
    answer = _plain_text(value.get("answer"), f"第 {number} 题 answer", maximum=1200)
    if question_type == "single_choice":
        answer = answer.strip().upper().rstrip(".、")
        if answer not in {"A", "B", "C", "D"}:
            raise ExamBlueprintError(f"第 {number} 题 answer 必须是 A、B、C 或 D。")
    analysis = _plain_text(value.get("analysis"), f"第 {number} 题 analysis", maximum=4000)
    rubric = _parse_rubric(value.get("rubric"), score, number)
    return ExamQuestion(
        number=number,
        question_type=question_type,
        score=score,
        title=title,
        stem=stem,
        options=options,
        answer=answer,
        analysis=analysis,
        rubric=rubric,
        chapter=_optional_text(value.get("chapter"), f"第 {number} 题 chapter", maximum=100),
        difficulty=_optional_text(value.get("difficulty"), f"第 {number} 题 difficulty", maximum=30),
    )


def _check_duplicate_questions(questions: tuple[ExamQuestion, ...]) -> None:
    seen: dict[str, int] = {}
    for question in questions:
        normalized = _DUPLICATE_NORMALIZE_RE.sub("", question.stem.lower())
        if len(normalized) < 8:
            raise ExamBlueprintError(f"第 {question.number} 题题干过短，无法可靠查重。")
        previous = seen.get(normalized)
        if previous is not None:
            raise ExamBlueprintError(f"第 {previous} 题与第 {question.number} 题题干重复。")
        current_grams = {normalized[index:index + 3] for index in range(len(normalized) - 2)}
        for other_text, other_number in seen.items():
            other_grams = {
                other_text[index:index + 3] for index in range(len(other_text) - 2)
            }
            union = current_grams | other_grams
            similarity = len(current_grams & other_grams) / len(union) if union else 0.0
            if similarity >= 0.82:
                raise ExamBlueprintError(
                    f"第 {other_number} 题与第 {question.number} 题题干疑似重复。"
                )
        seen[normalized] = question.number


def _check_layout_budget(questions: tuple[ExamQuestion, ...]) -> None:
    choices = tuple(item for item in questions if item.question_type == "single_choice")
    fills = tuple(item for item in questions if item.question_type == "fill_blank")
    calculations = tuple(item for item in questions if item.question_type == "calculation")
    choice_units = sum(
        len(item.stem) + sum(len(option) for option in item.options)
        for item in choices
    )
    if choice_units > CHOICE_LAYOUT_BUDGET:
        raise ExamBlueprintError(
            f"选择题总文本超出三页试卷版面预算（{choice_units} > "
            f"{CHOICE_LAYOUT_BUDGET}）。"
        )
    fill_units = sum(len(item.stem) for item in fills)
    if fill_units > FILL_LAYOUT_BUDGET:
        raise ExamBlueprintError(
            f"填空题总文本超出三页试卷版面预算（{fill_units} > "
            f"{FILL_LAYOUT_BUDGET}）。"
        )
    if fill_units + len(calculations[0].stem) > PAGE_TWO_LEFT_LAYOUT_BUDGET:
        raise ExamBlueprintError("第二页左栏题干超出版面预算，请精简填空题或第三大题。")
    if len(calculations[2].stem) + len(calculations[3].stem) > PAGE_THREE_LEFT_LAYOUT_BUDGET:
        raise ExamBlueprintError("第三页左栏题干超出版面预算，请精简第五、六大题。")


def _contains_makeup(value: str) -> bool:
    return bool(_MAKEUP_RE.search(value or ""))


def _validate_title_exam_type(title: str, exam_type: str) -> None:
    is_makeup = _contains_makeup(exam_type)
    title_has_makeup = _contains_makeup(title)
    if is_makeup and not title_has_makeup:
        raise ExamBlueprintError("补考试卷的 title 必须含“补考”。")
    if not is_makeup and title_has_makeup:
        raise ExamBlueprintError("非补考试卷的 title 不得含“补考”。")


def _check_course_topic_policy(
    course: str,
    questions: tuple[ExamQuestion, ...],
) -> None:
    normalized_course = re.sub(r"\s+", "", course)
    if not _COURSE_WITHOUT_RELATIVITY_RE.search(normalized_course):
        return
    for question in questions:
        fields = (
            ("stem", question.stem),
            ("title", question.title),
            ("options", " ".join(question.options)),
            ("answer", question.answer),
            ("analysis", question.analysis),
            ("chapter", question.chapter),
            ("rubric", " ".join(item.criterion for item in question.rubric)),
        )
        for field, value in fields:
            if _RELATIVITY_TOPIC_RE.search(value):
                raise ExamBlueprintError(
                    f"大学物理1/A不涉及相对论；第 {question.number} 题 {field} "
                    "含有明确的相对论主题。"
                )


def _parse_exam_blueprint_data(
    data: dict,
    *,
    allow_duplicate_options: bool = False,
    allow_invalid_fill_blank_markers: bool = False,
) -> ExamBlueprint:
    _require_exact_keys(data, _TOP_LEVEL_KEYS, "结构化命题 JSON")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ExamBlueprintError(f"schema_version 必须为 {SCHEMA_VERSION}。")
    kind = str(data.get("kind") or "").strip().lower()
    summary = _plain_text(data.get("summary"), "summary", maximum=800)
    if kind == "message":
        if (
            any(data.get(field) not in (None, "") for field in (
                "title", "course", "academic_year", "term", "exam_type", "exam_date"
            ))
            or data.get("duration_minutes") != 0
            or data.get("total_score") != 0
            or data.get("questions") != []
        ):
            raise ExamBlueprintError("message 类型不得携带试卷元数据、题目或分值。")
        return ExamBlueprint(kind=kind, summary=summary)
    if kind != "exam":
        raise ExamBlueprintError("kind 必须是 exam 或 message。")

    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list) or len(raw_questions) != 20:
        raise ExamBlueprintError("标准试卷必须包含 20 题：10 道单选、5 道双空填空、5 道计算。")
    expected_types = (
        ["single_choice"] * STANDARD_COUNTS["single_choice"]
        + ["fill_blank"] * STANDARD_COUNTS["fill_blank"]
        + ["calculation"] * STANDARD_COUNTS["calculation"]
    )
    questions = tuple(
        _parse_question(
            value,
            number,
            expected_types[number - 1],
            allow_duplicate_options=allow_duplicate_options,
            allow_invalid_fill_blank_markers=allow_invalid_fill_blank_markers,
        )
        for number, value in enumerate(raw_questions, 1)
    )
    _check_layout_budget(questions)
    _check_duplicate_questions(questions)
    total_score = _positive_integer(data.get("total_score"), "total_score", maximum=300)
    if total_score != 100 or sum(question.score for question in questions) != total_score:
        raise ExamBlueprintError("标准试卷总分必须为 100 分，且各题分值之和必须等于总分。")
    duration = _positive_integer(
        data.get("duration_minutes", 120), "duration_minutes", maximum=360
    )
    title = _plain_text(data.get("title"), "title", maximum=120)
    course = _plain_text(data.get("course"), "course", maximum=60)
    exam_type = _plain_text(data.get("exam_type"), "exam_type", maximum=40)
    _validate_title_exam_type(title, exam_type)
    _check_course_topic_policy(course, questions)
    return ExamBlueprint(
        kind=kind,
        summary=summary,
        title=title,
        course=course,
        academic_year=_plain_text(data.get("academic_year"), "academic_year", maximum=40),
        term=_plain_text(data.get("term"), "term", maximum=40),
        exam_type=exam_type,
        exam_date=_optional_text(data.get("exam_date"), "exam_date", maximum=40),
        duration_minutes=duration,
        total_score=total_score,
        questions=questions,
    )


def parse_exam_blueprint(text: str) -> ExamBlueprint:
    return _parse_exam_blueprint_data(_parse_json(text))


def _choice_option_repair_specs_from_validated(
    data: dict,
    blueprint: ExamBlueprint,
) -> tuple[ChoiceOptionRepairSpec, ...]:
    raw_questions = data["questions"]
    specs: list[ChoiceOptionRepairSpec] = []
    for question in blueprint.questions:
        if question.question_type != "single_choice":
            continue
        groups = _duplicate_option_groups(question.options)
        if not groups:
            continue
        correct_index = ord(question.answer) - ord("A")
        keeper_indices: list[int] = []
        editable_indices: list[int] = []
        for group in groups:
            keeper = correct_index if correct_index in group else group[0]
            keeper_indices.append(keeper)
            editable_indices.extend(index for index in group if index != keeper)
        editable = frozenset(editable_indices)
        # Keep the validated source spelling byte-for-byte. Repair responses must
        # echo locked options exactly, including otherwise harmless whitespace.
        raw_option_list = raw_questions[question.number - 1]["options"]
        raw_options = (
            raw_option_list[0],
            raw_option_list[1],
            raw_option_list[2],
            raw_option_list[3],
        )
        specs.append(ChoiceOptionRepairSpec(
            number=question.number,
            stem=question.stem,
            options=raw_options,
            answer=question.answer,
            analysis=question.analysis,
            editable_labels=tuple(chr(ord("A") + index) for index in sorted(editable)),
            keeper_labels=tuple(chr(ord("A") + index) for index in keeper_indices),
            locked_labels=tuple(
                chr(ord("A") + index) for index in range(4) if index not in editable
            ),
        ))
    return tuple(specs)


def choice_option_repair_specs(raw: str) -> tuple[ChoiceOptionRepairSpec, ...]:
    """Return repair bounds only after every non-duplicate check succeeds."""
    data = _parse_json(raw)
    blueprint = _parse_exam_blueprint_data(data, allow_duplicate_options=True)
    if blueprint.kind != "exam":
        return ()
    return _choice_option_repair_specs_from_validated(data, blueprint)


def targeted_exam_repair_plan(raw: str) -> TargetedExamRepairPlan:
    """Authorize supported local repairs after all unrelated checks pass.

    This deliberately permits only two defects while validating the source:
    normalized duplicate choice options and a fill stem whose ``[[BLANK]]``
    marker count is not exactly two. Any other defect fails before a repair
    request can be constructed.
    """
    data = _parse_json(raw)
    blueprint = _parse_exam_blueprint_data(
        data,
        allow_duplicate_options=True,
        allow_invalid_fill_blank_markers=True,
    )
    if blueprint.kind != "exam":
        raise ExamBlueprintError("当前结构不是可局部修复的整卷试题。")

    choice_repairs = _choice_option_repair_specs_from_validated(data, blueprint)
    fill_stem_repairs = tuple(
        FillBlankStemRepairSpec(
            number=question.number,
            stem=question.stem,
            answer=question.answer,
            analysis=question.analysis,
            chapter=question.chapter,
            difficulty=question.difficulty,
        )
        for question in blueprint.questions
        if question.question_type == "fill_blank"
        and question.stem.count("[[BLANK]]") != 2
    )
    if not choice_repairs and not fill_stem_repairs:
        raise ExamBlueprintError("原始试卷不存在可局部修复的重复选项或填空题占位符错误。")
    return TargetedExamRepairPlan(
        choice_repairs=choice_repairs,
        fill_stem_repairs=fill_stem_repairs,
    )


def apply_choice_option_repairs(raw: str, repair_json: str) -> ExamBlueprint:
    """Apply a complete, options-only repair and revalidate the entire exam."""
    original_data = _parse_json(raw)
    specs = choice_option_repair_specs(raw)
    if not specs:
        raise ExamBlueprintError("原始试卷不存在可局部修复的重复选择题选项。")

    payload = _parse_json(repair_json)
    _require_exact_keys(payload, _OPTION_REPAIR_KEYS, "选项修复 JSON")
    repairs = payload.get("repairs")
    if not isinstance(repairs, list):
        raise ExamBlueprintError("选项修复 JSON 的 repairs 必须是数组。")

    expected = {spec.number: spec for spec in specs}
    submitted: dict[int, list[str]] = {}
    for index, item in enumerate(repairs, 1):
        if not isinstance(item, dict):
            raise ExamBlueprintError(f"选项修复 repairs[{index}] 必须是对象。")
        _require_exact_keys(item, _OPTION_REPAIR_ITEM_KEYS, f"选项修复 repairs[{index}]")
        number = _positive_integer(
            item.get("number"), f"选项修复 repairs[{index}].number", maximum=20
        )
        if number in submitted:
            raise ExamBlueprintError(f"选项修复重复提交第 {number} 题。")
        if number not in expected:
            raise ExamBlueprintError(f"选项修复包含未授权的第 {number} 题。")
        options = item.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ExamBlueprintError(f"第 {number} 题修复必须恰有 A、B、C、D 四个选项。")
        for option_index, option in enumerate(options):
            _plain_text(
                option,
                f"第 {number} 题修复选项 {chr(ord('A') + option_index)}",
                maximum=OPTION_LENGTH_LIMIT,
            )
        submitted[number] = options

    missing = sorted(set(expected) - set(submitted))
    if missing:
        raise ExamBlueprintError(
            "选项修复未覆盖全部重复题：" + "、".join(f"第 {number} 题" for number in missing)
        )

    repaired_data = copy.deepcopy(original_data)
    for number, options in submitted.items():
        spec = expected[number]
        restored_options = list(spec.options)
        for label in spec.editable_labels:
            option_index = ord(label) - ord("A")
            restored_options[option_index] = options[option_index]
        # The model returns all four options for schema compatibility, but the
        # server authorizes only editable_labels. Ignore any attempted changes
        # to locked/correct options and restore them byte-for-byte from source.
        repaired_data["questions"][number - 1]["options"] = restored_options

    return parse_exam_blueprint(
        json.dumps(repaired_data, ensure_ascii=False, separators=(",", ":"))
    )


def apply_targeted_exam_repairs(raw: str, repair_json: str) -> ExamBlueprint:
    """Apply exactly one authorized batch of option/stem repairs and revalidate."""
    original_data = _parse_json(raw)
    plan = targeted_exam_repair_plan(raw)
    payload = _parse_json(repair_json)
    _require_exact_keys(payload, _TARGETED_REPAIR_KEYS, "局部修复 JSON")

    raw_choice_repairs = payload.get("choice_repairs")
    raw_fill_repairs = payload.get("fill_stem_repairs")
    if not isinstance(raw_choice_repairs, list):
        raise ExamBlueprintError("局部修复 JSON 的 choice_repairs 必须是数组。")
    if not isinstance(raw_fill_repairs, list):
        raise ExamBlueprintError("局部修复 JSON 的 fill_stem_repairs 必须是数组。")

    expected_choices = {spec.number: spec for spec in plan.choice_repairs}
    submitted_choices: dict[int, list[str]] = {}
    for index, item in enumerate(raw_choice_repairs, 1):
        if not isinstance(item, dict):
            raise ExamBlueprintError(f"局部修复 choice_repairs[{index}] 必须是对象。")
        _require_exact_keys(
            item,
            _TARGETED_CHOICE_REPAIR_ITEM_KEYS,
            f"局部修复 choice_repairs[{index}]",
        )
        number = _positive_integer(
            item.get("number"),
            f"局部修复 choice_repairs[{index}].number",
            maximum=20,
        )
        if number in submitted_choices:
            raise ExamBlueprintError(f"局部修复重复提交第 {number} 题选项。")
        if number not in expected_choices:
            raise ExamBlueprintError(f"局部修复包含未授权的第 {number} 题选项。")
        options = item.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ExamBlueprintError(f"第 {number} 题修复必须恰有 A、B、C、D 四个选项。")
        for option_index, option in enumerate(options):
            _plain_text(
                option,
                f"第 {number} 题修复选项 {chr(ord('A') + option_index)}",
                maximum=OPTION_LENGTH_LIMIT,
            )
        submitted_choices[number] = options

    missing_choices = sorted(set(expected_choices) - set(submitted_choices))
    if missing_choices:
        raise ExamBlueprintError(
            "局部修复未覆盖全部重复选项题："
            + "、".join(f"第 {number} 题" for number in missing_choices)
        )

    expected_fills = {spec.number: spec for spec in plan.fill_stem_repairs}
    submitted_fills: dict[int, str] = {}
    for index, item in enumerate(raw_fill_repairs, 1):
        if not isinstance(item, dict):
            raise ExamBlueprintError(f"局部修复 fill_stem_repairs[{index}] 必须是对象。")
        _require_exact_keys(
            item,
            _TARGETED_FILL_REPAIR_ITEM_KEYS,
            f"局部修复 fill_stem_repairs[{index}]",
        )
        number = _positive_integer(
            item.get("number"),
            f"局部修复 fill_stem_repairs[{index}].number",
            maximum=20,
        )
        if number in submitted_fills:
            raise ExamBlueprintError(f"局部修复重复提交第 {number} 题填空题题干。")
        if number not in expected_fills:
            raise ExamBlueprintError(f"局部修复包含未授权的第 {number} 题填空题题干。")
        stem = _plain_text(
            item.get("stem"),
            f"第 {number} 题修复 stem",
            maximum=STEM_LENGTH_LIMITS["fill_blank"],
        )
        if stem.count("[[BLANK]]") != 2:
            raise ExamBlueprintError(f"第 {number} 题修复 stem 必须且只能包含两个 [[BLANK]]。")
        submitted_fills[number] = stem

    missing_fills = sorted(set(expected_fills) - set(submitted_fills))
    if missing_fills:
        raise ExamBlueprintError(
            "局部修复未覆盖全部填空题题干："
            + "、".join(f"第 {number} 题" for number in missing_fills)
        )

    repaired_data = copy.deepcopy(original_data)
    for number, options in submitted_choices.items():
        spec = expected_choices[number]
        restored_options = list(spec.options)
        for label in spec.editable_labels:
            option_index = ord(label) - ord("A")
            restored_options[option_index] = options[option_index]
        repaired_data["questions"][number - 1]["options"] = restored_options
    for number, stem in submitted_fills.items():
        repaired_data["questions"][number - 1]["stem"] = stem

    return parse_exam_blueprint(
        json.dumps(repaired_data, ensure_ascii=False, separators=(",", ":"))
    )


def blueprint_to_dict(blueprint: ExamBlueprint) -> dict:
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": blueprint.kind,
        "summary": blueprint.summary,
        "title": blueprint.title,
        "course": blueprint.course,
        "academic_year": blueprint.academic_year,
        "term": blueprint.term,
        "exam_type": blueprint.exam_type,
        "exam_date": blueprint.exam_date,
        "duration_minutes": blueprint.duration_minutes,
        "total_score": blueprint.total_score,
        "questions": [],
    }
    if blueprint.kind != "exam":
        return result
    result.update({
        "title": blueprint.title,
        "course": blueprint.course,
        "academic_year": blueprint.academic_year,
        "term": blueprint.term,
        "exam_type": blueprint.exam_type,
        "exam_date": blueprint.exam_date,
        "duration_minutes": blueprint.duration_minutes,
        "total_score": blueprint.total_score,
        "questions": [
            {
                "number": item.number,
                "type": item.question_type,
                "score": item.score,
                "title": item.title,
                "stem": item.stem,
                "options": list(item.options),
                "answer": item.answer,
                "analysis": item.analysis,
                "rubric": [
                    {"points": rubric.points, "criterion": rubric.criterion}
                    for rubric in item.rubric
                ],
                "chapter": item.chapter,
                "difficulty": item.difficulty,
            }
            for item in blueprint.questions
        ],
    })
    return result


def canonical_blueprint_json(blueprint: ExamBlueprint) -> str:
    return json.dumps(blueprint_to_dict(blueprint), ensure_ascii=False, separators=(",", ":"))


_TEX_ESCAPE: Final = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "^": r"\^{}",
    "~": r"\~{}",
}

_INLINE_PHYSICS_FORMULA_RE: Final = re.compile(
    r"(?<![A-Za-z])(?:\\(?:miu|mu|epsilon|varepsilon|lambda|theta|omega|alpha|beta|gamma|delta|eta|zeta|iota|kappa|nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|Omega)"
    r"|[A-Za-zαβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ])"
    r"(?:[A-Za-z0-9αβγδεζηθικλμνξοπρστυφχψωΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹\\{}_^+\-*/().= ]{0,78})"
    r"(?=[\u3400-\u9fff，。；：！？、（）]|$)"
)
_ALLOWED_PHYSICS_COMMANDS: Final = frozenset({
    "mu", "epsilon", "varepsilon", "lambda", "theta", "omega", "alpha",
    "beta", "gamma", "delta", "eta", "zeta", "iota", "kappa", "nu",
    "xi", "pi", "rho", "sigma", "tau", "upsilon", "phi", "varphi",
    "chi", "psi", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi",
    "Sigma", "Upsilon", "Phi", "Psi", "Omega",
})
_GREEK_CHAR_TEX: Final = str.maketrans({
    "α": r"\alpha ", "β": r"\beta ", "γ": r"\gamma ", "δ": r"\delta ",
    "ε": r"\epsilon ", "ζ": r"\zeta ", "η": r"\eta ", "θ": r"\theta ",
    "ι": r"\iota ", "κ": r"\kappa ", "λ": r"\lambda ", "μ": r"\mu ",
    "ν": r"\nu ", "ξ": r"\xi ", "ο": "o", "π": r"\pi ",
    "ρ": r"\rho ", "σ": r"\sigma ", "τ": r"\tau ", "υ": r"\upsilon ",
    "φ": r"\phi ", "χ": r"\chi ", "ψ": r"\psi ", "ω": r"\omega ",
    "Γ": r"\Gamma ", "Δ": r"\Delta ", "Θ": r"\Theta ", "Λ": r"\Lambda ",
    "Ξ": r"\Xi ", "Π": r"\Pi ", "Σ": r"\Sigma ", "Υ": r"\Upsilon ",
    "Φ": r"\Phi ", "Ψ": r"\Psi ", "Ω": r"\Omega ",
})
_UNICODE_SUBSCRIPT_DIGITS: Final = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_UNICODE_SUPERSCRIPT_DIGITS: Final = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def _safe_inline_physics_formula(value: str) -> str | None:
    """Return a small, server-owned TeX math expression or ``None``.

    Blueprint fields are untrusted.  This deliberately accepts only ASCII
    arithmetic plus a short Greek-letter allow-list; document-level TeX can
    therefore never pass through this renderer.
    """
    normalized = value.strip()
    normalized = re.sub(
        r"(?<![A-Za-z])([A-Za-zαβγδεζηθικλμνξοπρστυφχψωΩ])([₀₁₂₃₄₅₆₇₈₉]+)",
        lambda match: f"{match.group(1)}_{{{match.group(2).translate(_UNICODE_SUBSCRIPT_DIGITS)}}}",
        normalized,
    )
    normalized = re.sub(
        r"([A-Za-z0-9αβγδεζηθικλμνξοπρστυφχψωΩ})])([⁰¹²³⁴⁵⁶⁷⁸⁹]+)",
        lambda match: f"{match.group(1)}^{{{match.group(2).translate(_UNICODE_SUPERSCRIPT_DIGITS)}}}",
        normalized,
    )
    normalized = re.sub(
        r"([αβγδεζηθικλμνξοπρστυφχψωΩ])([0-9])",
        r"\1_{\2}",
        normalized,
    )
    normalized = normalized.translate(_GREEK_CHAR_TEX)
    normalized = re.sub(r"\\miu(?![A-Za-z])", r"\\mu", normalized, flags=re.I)
    normalized = re.sub(r"(\\[A-Za-z]+)([0-9])", r"\1_{\2}", normalized)
    normalized = re.sub(
        r"([qQvVxXyYzZrRIUuEeFfpP])([0-9])",
        r"\1_{\2}",
        normalized,
    )
    normalized = re.sub(r"(?<![A-Za-z])E([kp])(?![A-Za-z])", r"E_{\1}", normalized)
    normalized = re.sub(r"\s+(?=[_^])", "", normalized)
    normalized = re.sub(r"\\([A-Za-z]+)\s+(?=[_^])", r"\\\1", normalized)
    has_math_marker = any(mark in normalized for mark in ("=", "/", "^", "\\"))
    has_simple_subscript = re.search(r"(?<![A-Za-z])[A-Za-z]_[A-Za-z0-9{}]+", normalized)
    if not normalized or not (has_math_marker or has_simple_subscript):
        return None
    if re.search(r"[^A-Za-z0-9\\{}_^+\-*/().= ]", normalized):
        return None
    commands = re.findall(r"\\([A-Za-z]+)", normalized)
    if any(command not in _ALLOWED_PHYSICS_COMMANDS for command in commands):
        return None
    if normalized.count("{") != normalized.count("}"):
        return None
    return normalized


def _tex_escape_text_with_physics(value: str) -> str:
    output: list[str] = []
    cursor = 0
    for match in _INLINE_PHYSICS_FORMULA_RE.finditer(value):
        raw_formula = match.group(0)
        formula = _safe_inline_physics_formula(raw_formula)
        if formula is None:
            continue
        output.append("".join(_TEX_ESCAPE.get(char, char) for char in value[cursor:match.start()]))
        output.append(r"\(" + formula + r"\)")
        output.append(raw_formula[len(raw_formula.rstrip()):])
        cursor = match.end()
    output.append("".join(_TEX_ESCAPE.get(char, char) for char in value[cursor:]))
    return "".join(output)


def tex_escape(value: str, *, allow_blank: bool = False) -> str:
    parts = value.split("[[BLANK]]") if allow_blank else [value]
    escaped = [_tex_escape_text_with_physics(part) for part in parts]
    return r"\underline{\hspace{3cm}}".join(escaped)


def _preamble(*, wide: bool) -> str:
    geometry = (
        r"\usepackage[top=1.2cm,bottom=1.2cm,left=2cm,right=2cm]{geometry}"
        "\n" r"\geometry{paperwidth=380mm,paperheight=265mm}"
        if wide
        else r"\usepackage[top=1.6cm,bottom=1.6cm,left=1.8cm,right=1.8cm]{geometry}"
    )
    return (
        "\\documentclass[12pt,onecolumn]{article}\n"
        f"{geometry}\n"
        "\\usepackage[UTF8]{ctex}\n"
        "\\usepackage{mdframed}\n"
        "\\usepackage{tabularx}\n"
        "\\usepackage{multicol}\n"
        "\\usepackage{enumitem}\n"
        "\\pagestyle{empty}\n"
        "\\setlength{\\parindent}{0pt}\n"
        "\\setlength{\\columnsep}{1.6em}\n"
    )


def _display_exam_title(blueprint: ExamBlueprint) -> str:
    title = _MAKEUP_RE.sub("补考", blueprint.title).strip()
    prefix = []
    for value in (blueprint.academic_year, blueprint.term, blueprint.exam_type):
        value = _MAKEUP_RE.sub("补考", value).strip()
        if not value or value in title:
            continue
        if value == blueprint.exam_type:
            type_core = re.sub(r"(?:考试|试卷)$", "", value).strip()
            if type_core and type_core in title:
                continue
        prefix.append(value)
    return "".join(prefix) + title


def _page_header(blueprint: ExamBlueprint, page: int) -> str:
    return (
        "\\begin{center}\n"
        "{\\fontsize{14}{16}\\selectfont 天津仁爱学院试卷专用纸}\\\\[0.5em]\n"
        "\\begin{tabularx}{\\textwidth}{@{}lX lX lX lX lX lX r@{}}\n"
        "{\\heiti 学院} & \\hrulefill & {\\heiti 专业} & \\hrulefill & "
        "{\\heiti 班级} & \\hrulefill & {\\heiti 年级} & \\hrulefill & "
        "{\\heiti 学号} & \\hrulefill & {\\heiti 姓名} & \\hrulefill & "
        f"共 3 页　第 {page} 页 \\\\\n"
        "\\end{tabularx}\n"
        "\\end{center}\n"
    )


def _exam_title_block(blueprint: ExamBlueprint) -> str:
    title = tex_escape(_display_exam_title(blueprint))
    course = tex_escape(blueprint.course)
    exam_date = tex_escape(blueprint.exam_date) if blueprint.exam_date else "\\hspace{5em}"
    return (
        "\\begin{center}\n"
        f"{{\\heiti\\fontsize{{14}}{{16}}\\selectfont {title}}}\\\\[0.35em]\n"
        f"{{\\heiti\\fontsize{{14}}{{16}}\\selectfont 《{course}》（共 3 页）}}\\\\[0.5em]\n"
        f"{{\\heiti（考试时间：{exam_date}）}}\\\\[0.7em]\n"
        "\\end{center}\n"
    )


def _score_table() -> str:
    return (
        "\\renewcommand{\\arraystretch}{1.35}\n"
        "\\begin{center}\n"
        "\\begin{tabularx}{0.98\\linewidth}{|*{9}{>{\\centering\\arraybackslash}X|}}\n"
        "\\hline 题号 & 一 & 二 & 三 & 四 & 五 & 六 & 七 & 成绩 \\\\ \n"
        "\\hline 得分 & & & & & & & & \\\\ \n"
        "\\hline 评分人 & & & & & & & & \\\\ \n"
        "\\hline\n\\end{tabularx}\n\\end{center}\n"
    )


def _choice_column(
    questions: tuple[ExamQuestion, ...],
    *,
    start: int,
    include_heading: bool,
) -> str:
    lines = []
    if include_heading:
        lines.append(r"\textbf{一、单项选择题（每题 3 分，共 30 分）}")
    lines.append(
        rf"\begin{{enumerate}}[label=\arabic*.,start={start},leftmargin=2em,"
        r"itemsep=0.2em,topsep=0.25em,parsep=0pt,partopsep=0pt]"
    )
    for question in questions:
        lines.append(f"\\item {tex_escape(question.stem)} \\hfill（　　）")
        lines.append(r"\begin{tabularx}{\linewidth}{@{}X X@{}}")
        lines.append(
            f"(A) {tex_escape(question.options[0])} & (B) {tex_escape(question.options[1])} \\\\"
        )
        lines.append(
            f"(C) {tex_escape(question.options[2])} & (D) {tex_escape(question.options[3])}"
        )
        lines.append(r"\end{tabularx}")
    lines.append(r"\end{enumerate}")
    return "\n".join(lines) + "\n"


def _choice_section(
    questions: tuple[ExamQuestion, ...],
    *,
    first_column_prefix: str = "",
) -> str:
    midpoint = len(questions) // 2
    layout_units = sum(
        len(item.stem) + sum(len(option) for option in item.options)
        for item in questions
    )
    bottom_space = max(3, 10 - max(0, layout_units - 1000 + 79) // 80)
    return (
        "{\\footnotesize\\setlength{\\tabcolsep}{3pt}\n"
        "\\begin{multicols}{2}\n"
        + first_column_prefix
        + _choice_column(questions[:midpoint], start=1, include_heading=True)
        + f"\\vspace*{{{bottom_space}em}}\n"
        + "\\columnbreak\n"
        + _choice_column(questions[midpoint:], start=midpoint + 1, include_heading=False)
        + f"\\vspace*{{{bottom_space}em}}\n"
        + "\\end{multicols}\n}\n"
    )


def _fill_section(questions: tuple[ExamQuestion, ...]) -> str:
    lines = [
        r"\textbf{二、填空题（每空 2 分，共 20 分）}",
        r"\begin{enumerate}[label=\arabic*.,leftmargin=2em,itemsep=0.85em]",
    ]
    lines.extend(
        f"\\item {tex_escape(question.stem, allow_blank=True)}"
        for question in questions
    )
    lines.append(r"\end{enumerate}")
    return "\n".join(lines) + "\n"


_CALC_SECTION_NUMERALS: Final = ("三", "四", "五", "六", "七")


def _calculation_section(
    question: ExamQuestion,
    index: int,
    *,
    answer_space: str,
) -> str:
    title = tex_escape(question.title)
    return (
        "\\noindent\\begin{minipage}[t]{\\linewidth}\n"
        f"\\textbf{{{_CALC_SECTION_NUMERALS[index]}、{title}（共 10 分）}}\n"
        f"\\par\\vspace*{{0.6em}}\\noindent {tex_escape(question.stem)}\n"
        "\\end{minipage}\n"
        f"\\par\\vspace*{{{answer_space}}}\n"
    )


def _calculation_answer_space(
    question: ExamQuestion,
    *,
    base: int,
    minimum: int,
) -> str:
    extra = max(0, len(question.stem) - 120)
    reduction = 2 * ((extra + 39) // 40)
    return f"{max(minimum, base - reduction)}em"


def _page_frame(content: str) -> str:
    return (
        "\\begin{mdframed}[linewidth=2pt, linecolor=black, "
        "innerleftmargin=2pt,innerrightmargin=8pt,\n"
        "innerbottommargin=35pt]\n"
        f"{content}"
        "\\end{mdframed}\n"
    )


def render_main_tex(blueprint: ExamBlueprint) -> str:
    if blueprint.kind != "exam":
        raise ExamBlueprintError("message 类型不能生成试卷 TeX。")
    choice = tuple(item for item in blueprint.questions if item.question_type == "single_choice")
    fill = tuple(item for item in blueprint.questions if item.question_type == "fill_blank")
    calculation = tuple(item for item in blueprint.questions if item.question_type == "calculation")
    pages = [
        _page_header(blueprint, 1)
        + _page_frame(
            _choice_section(
                choice,
                first_column_prefix=_exam_title_block(blueprint) + _score_table(),
            )
        ),
        _page_header(blueprint, 2)
        + _page_frame(
            "\\begin{multicols}{2}\n"
            + _fill_section(fill)
            + _calculation_section(
                calculation[0],
                0,
                answer_space=_calculation_answer_space(calculation[0], base=12, minimum=8),
            )
            + "\\columnbreak\n"
            + _calculation_section(
                calculation[1],
                1,
                answer_space=_calculation_answer_space(calculation[1], base=40, minimum=28),
            )
            + "\\end{multicols}\n"
        ),
        _page_header(blueprint, 3)
        + _page_frame(
            "\\begin{multicols}{2}\n"
            + _calculation_section(
                calculation[2],
                2,
                answer_space=_calculation_answer_space(calculation[2], base=11, minimum=8),
            )
            + _calculation_section(
                calculation[3],
                3,
                answer_space=_calculation_answer_space(calculation[3], base=10, minimum=8),
            )
            + "\\columnbreak\n"
            + _calculation_section(
                calculation[4],
                4,
                answer_space=_calculation_answer_space(calculation[4], base=40, minimum=28),
            )
            + "\\end{multicols}\n"
        ),
    ]
    return _preamble(wide=True) + "\\begin{document}\n" + "\\newpage\n".join(pages) + "\\end{document}\n"


def _answer_preamble() -> str:
    """Return the server-owned preamble derived from the standard answer.tex."""
    return (
        "\\documentclass[a4paper]{ctexart}\n"
        "\\usepackage[a4paper,top=2.54cm,bottom=2.54cm]{geometry}\n"
        "\\usepackage{multirow}\n"
        "\\usepackage{diagbox}\n"
        "\\usepackage{array}\n"
        "\\usepackage{tabularx}\n"
    )


def _answer_choice_table(questions: tuple[ExamQuestion, ...]) -> str:
    numbers = " & ".join(str(index) for index in range(1, len(questions) + 1))
    answers = " & ".join(tex_escape(question.answer) for question in questions)
    columns = "|c|" + "c|" * len(questions)
    return (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        f"\\begin{{tabular}}{{{columns}}}\n"
        "\\hline\n"
        f"题号 & {numbers} \\\\ \\hline\n"
        f"选项 & {answers} \\\\ \\hline\n"
        "\\end{tabular}\n"
        "\\end{table}\n"
    )


def _answer_fill_table(questions: tuple[ExamQuestion, ...]) -> str:
    numbers = " & ".join(str(index) for index in range(1, len(questions) + 1))
    answers = " & ".join(tex_escape(question.answer) for question in questions)
    columns = "|c|" + ">{\\centering\\arraybackslash}X|" * len(questions)
    return (
        "\\begin{table}[htbp]\n"
        "\\centering\\small\n"
        f"\\begin{{tabularx}}{{0.98\\textwidth}}{{{columns}}}\n"
        "\\hline\n"
        f"题号 & {numbers} \\\\ \\hline\n"
        f"答案 & {answers} \\\\ \\hline\n"
        "\\end{tabularx}\n"
        "\\end{table}\n"
    )


def _answer_calculation_section(question: ExamQuestion, index: int) -> str:
    title = tex_escape(question.title)
    scoring_steps = "\n".join(
        f"({step}){tex_escape(item.criterion)}\\hfill({item.points}分)\\\\"
        for step, item in enumerate(question.rubric, 1)
    )
    return (
        f"\\subsection*{{{_CALC_SECTION_NUMERALS[index]}.{title}(本题10分)}}\n"
        f"\\textbf{{答案：}}{tex_escape(question.answer)}\\par\n"
        f"\\textbf{{解析：}}{tex_escape(question.analysis)}\\par\n"
        f"{scoring_steps}\n\\par\n"
    )


def render_answer_tex(blueprint: ExamBlueprint) -> str:
    if blueprint.kind != "exam":
        raise ExamBlueprintError("message 类型不能生成答案 TeX。")
    choice = tuple(
        question for question in blueprint.questions
        if question.question_type == "single_choice"
    )
    fill = tuple(
        question for question in blueprint.questions
        if question.question_type == "fill_blank"
    )
    title = tex_escape(_display_exam_title(blueprint) + "解析")
    body = [
        f"\\section*{{{title}}}\n",
        "\\subsection*{一.单选题(每题3分，共计30分)}\n",
        _answer_choice_table(choice),
        "\\subsection*{二.填空题(每空2分，共计20分)}\n",
        _answer_fill_table(fill),
    ]
    calculations = tuple(
        question for question in blueprint.questions
        if question.question_type == "calculation"
    )
    body.extend(
        _answer_calculation_section(question, index)
        for index, question in enumerate(calculations)
    )
    return (
        _answer_preamble()
        + "\\begin{document}\n"
        + "\\setlength{\\parindent}{0pt}\n"
        + "".join(body)
        + "\\end{document}\n"
    )


def render_exam_tex(blueprint: ExamBlueprint) -> tuple[str, str]:
    return render_main_tex(blueprint), render_answer_tex(blueprint)
