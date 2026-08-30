from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final


PORTAL_ASSISTANT: Final = "assistant"
PORTAL_TEACHING_EXAM: Final = "teaching_exam"
TEACHER_EXAM_AGENT_MODE: Final = PORTAL_TEACHING_EXAM
EXAM_REQUEST_FULL_GENERATION: Final = "full_exam_generation"
EXAM_REQUEST_SOURCE_MATERIAL: Final = "source_material_task"
EXAM_REQUEST_GENERAL: Final = "teacher_task"
TEACHER_EXAM_PORTAL: Final = "teaching-exam"
TEACHER_EXAM_PORTAL_QUERY_KEY: Final = "portal"
DEFAULT_EXAM_TEMPLATE_RELATIVE_PATH: Final = (
    "考试素材/试卷/2025-2026-2/25262大物1补考/main.tex"
)
DEFAULT_ANSWER_TEMPLATE_RELATIVE_PATH: Final = (
    "考试素材/试卷/2025-2026-2/25262大物1补考/answer.tex"
)
MANDATORY_EXAM_GUIDE_RELATIVE_PATH: Final = (
    "考试素材/大学物理课程章节与组卷分值规范.md"
)
TEACHER_EXAM_PORTAL_ALLOWLIST: Final = frozenset({
    TEACHER_EXAM_PORTAL,
    "teacher-exam",  # compatibility with the first teacher-portal draft
})
TEACHER_EXAM_QUERY_ALLOWLIST: Final = frozenset({
    "portal",
    "chapter",
    "topics",
    "question_types",
    "difficulty",
    "question_count",
    "total_score",
    "duration_minutes",
    "include_answers",
    "include_rubric",
})

EXAM_DESIGN_STANDARDS: Final = (
    "题目条件充分、表述无歧义并且可以求解",
    "物理量、符号、方向、单位和适用条件完整一致",
    "试卷、参考答案和评分标准分区呈现",
    "计算结果经过验算，题目分值之和等于设定总分",
    "依据知识库重构题目，不照抄现成题目，也不虚构资料",
)

QUICK_EXAM_TASKS: Final = (
    ("命题蓝图", "请依据知识库设计一份命题蓝图，列出知识点、能力层级、题型、题量和分值分布。"),
    ("单元测验", "请依据知识库生成一份单元测验，并将试卷、参考答案和评分标准分开呈现。"),
    ("计算题专项", "请依据知识库生成一组由易到难的计算题，逐题验算并给出评分细则。"),
    ("实验题专项", "请依据知识库生成大学物理实验题，检查实验条件、数据合理性和不确定度要求。"),
    ("审核现有试题", "请审核我提供的试题，检查可解性、歧义、量纲、答案、难度和分值，并给出修订稿。"),
    ("生成评分标准", "请为我提供的试卷生成逐题参考答案与可操作的分步评分标准。"),
)
EXAM_QUICK_TASKS: Final = tuple(prompt for _label, prompt in QUICK_EXAM_TASKS)

MANDATORY_EXAM_POLICY_CONTEXT: Final = """[教师端默认组卷规范｜每次命题必须执行]
教材采用祝之光《物理学》第5版12章体系。大学物理1与大学物理A覆盖第1、2、3、6、7、8章；大学物理2覆盖第4、5、9、10、11章；大学物理B覆盖第4、5、9、10、11、12章。
大学物理1与大学物理A的考试范围明确排除相对论；即使模板、历史试卷或联网资料中出现相对论内容，也不得选入这两门课程的试卷、答案或评分标准。
默认100分题型结构：单项选择10题×3分=30分；填空10空×2分=20分；计算题5题×10分=50分。
大题编号必须连续：单项选择题为“一”、填空题为“二”，五道计算题分别为“三、四、五、六、七”。每道计算题都要有独立、具体的知识主题标题并标注“（共 10 分）”，不得合并成一个笼统的“计算题”栏目；五个知识主题的顺序可依据课程蓝图和版面需要调整。题图优先用可独立编译的TikZ绘制；确需外部图件时，只能引用标准模板目录中真实存在的可信相对路径图片。
默认章节分值：大学物理1为第1/2/3/6/7/8章=21/15/21/20/17/6；大学物理A=17/16/20/22/18/7；大学物理2第4/5/9/10/11/12章=5/14/21/21/39/0；大学物理B=4/15/19/19/39/4。因题型粒度可在单章约±2分内调整，但总分、课程范围和领域权重必须满足要求。
未明确指定其他版式时，使用“考试素材/试卷/2025-2026-2/25262大物1补考/main.tex”作为唯一标准题面模板；它规定三页、双栏、校名与考生信息栏、评分表以及30+20+50题型结构，不固定模板中的旧题内容。三张物理页面必须分别具有页眉和独立的2pt黑色外框，不得用一个跨页边框包裹整卷；页眉在外框之外，题面在框内按模板对齐。第1页左栏为标题、评分表和选择题1—5，右栏为选择题6—10；第2页左栏为填空题和第三大题、右栏为第四大题；第3页左栏为第五与第六大题、右栏为第七大题。必须显式换栏并仅在三张物理页之间分页，每道计算题后须保留足够的学生答题空间，不得让下一道大题紧贴上一题。题干必须简洁并服从三页版面预算，不得通过删除答题空间或缩小字号强行容纳冗长题面。大学物理2/B须按实际课程替换计算题栏目。
对应的“考试素材/试卷/2025-2026-2/25262大物1补考/answer.tex”是唯一标准答案版式：A4单栏、上下边距2.54cm、标题为“试卷解析”；单选题和填空题分别使用紧凑的题号/答案横表，不逐题展开客观题解析；五道计算题按“三.”至“七.”连续排列，每个评分步骤独立成行并用 \\hfill(分值) 右对齐。答案页不得套用题面页眉、考生信息栏、双栏或外框，也不得依赖 bibliography、外部 .bib/.tex 文件。
生成整套试卷前，教师必须明确提供学年、学期以及考试名称或类型；缺少任一项时只能列出缺失项并请教师补充，不得先行组卷或自行推断。考试日期可以留空，未提供时不得虚构。考试名称或类型为补考时，大标题必须含“补考”；其余考试的大标题不得出现“补考”。
完整依据文件为“考试素材/大学物理课程章节与组卷分值规范.md”。教师对本次考试的明确要求或更新教学大纲优先；试卷、answer.tex与分步评分标准须相互一致，待复核材料不得直接选入正式试卷。"""

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_SPACE_RE = re.compile(r"\s+")
_FULL_EXAM_ACTION_RE = re.compile(
    r"(?:生成|组卷|命制|编制|制作|拟定|拟制|设计|出|做)"
    r"[^。！？!?\n]{0,48}(?:试卷|考试卷|补考卷|重修卷|整卷)|"
    r"(?:试卷|考试卷|补考卷|重修卷|整卷)"
    r"[^。！？!?\n]{0,24}(?:生成|组卷|命制|编制|制作|拟定|拟制|设计|出|做)",
)
_EXAM_INQUIRY_RE = re.compile(r"(?:如何|怎样|怎么).{0,12}(?:生成|组卷|命制|编制)")
_UNIVERSITY_PHYSICS_COURSE_RE = re.compile(
    r"(?:大学物理|大物)\s*(?:1|2|Ⅰ|Ⅱ|I|II|一|二|A|B|Ａ|Ｂ)"
    r"(?![A-Za-z0-9一二三四五六七八九十])",
    re.I,
)
_COURSE_ONE_OR_A_RE = re.compile(
    r"(?:大学物理|大物)\s*(?:1|Ⅰ|I|一|A|Ａ)(?![A-Za-z0-9一二三四五六七八九十])",
    re.I,
)
_ACADEMIC_YEAR_RE = re.compile(
    r"(?:20)?\d{2}\s*[-—–至/]\s*(?:20)?\d{2}(?:\s*学年)?|"
    r"学年\s*[:：]\s*(?:20)?\d{2}\s*[-—–至/]\s*(?:20)?\d{2}",
)
_TERM_RE = re.compile(
    r"(?:第\s*)?(?:一|二|1|2|上|下|春季|秋季)\s*(?:个)?学期|"
    r"学期\s*[:：]\s*(?:第一|第二|一|二|1|2|上|下|春季|秋季)",
)
_EXAM_NAME_LABEL_RE = re.compile(
    r"(?:考试名称|考试名|试卷名称|试卷名)\s*[:：]\s*([^\n，,；;]+)",
)
_EXAM_DATE_RE = re.compile(
    r"(?:20\d{2}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?|"
    r"20\d{2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,2})",
)
_EXAM_TYPE_RE = re.compile(
    r"(?:期末|期中|补考|重修|结课|毕业|模拟|单元|随堂|开学|摸底)"
    r"\s*(?:考试|考查|测验|试卷)?",
)
_NON_MAKEUP_EXAM_TYPE_RE = re.compile(
    r"(?:期末|期中|重修|结课|毕业|模拟|单元|随堂|开学|摸底)"
    r"\s*(?:考试|考查|测验|试卷)?",
)
_NOT_MAKEUP_RE = re.compile(r"(?:不是|并非|非|不要|无需|不属于)\s*补考")
_SOURCE_MATERIAL_ACTION_RE = re.compile(
    r"(?:答案|解析|解答|评分(?:标准|细则)?|审核|审题|改题|批改|判卷|"
    r"讲解|校对|验算|评价|分析)"
)
_SOURCE_MATERIAL_REFERENCE_RE = re.compile(
    r"(?:上传|附件|附带|所附|这份|该份|此份|现有|已有|原(?:试卷|试题|题目)|"
    r"我(?:提供|上传)的|上述|前述|图片中|文件中)"
)
_ANSWER_FOR_EXISTING_MATERIAL_RE = re.compile(
    r"(?:为|给|根据|依据)[^。！？!?\n]{0,24}(?:试卷|试题|题目)"
    r"[^。！？!?\n]{0,16}(?:生成|制作|写|给出|做)"
    r"[^。！？!?\n]{0,12}(?:答案|解析|评分)"
)
_SOURCE_ANSWER_TARGET = r"(?:(?:参考)?答案|解答|解析|评分(?:标准|细则))"
_SOURCE_ANSWER_TARGET_RE = re.compile(_SOURCE_ANSWER_TARGET)
_SOURCE_ANSWER_DELIVERY_RE = re.compile(
    r"(?:生成|制作|给出|提供|写出?|整理|补充|输出|列出|做|完成|只(?:要|需)|需要)"
)
_SOURCE_ANSWER_DIRECT_RE = re.compile(
    r"(?:^|[，,。！？!?；;\s])(?:请|帮我|麻烦)?\s*"
    r"(?:逐题|完整(?:地)?|详细(?:地)?|分步)?\s*(?:解答|解析)"
    r"(?:这份|该份|此份|上述|前述|上传的|附件中的|试卷|试题|题目|$)"
)
_SOURCE_ANSWER_BARE_RE = re.compile(
    rf"^(?:请)?\s*(?:逐题|完整|详细|分步)?\s*{_SOURCE_ANSWER_TARGET}"
    rf"(?:\s*(?:和|与|及|、)\s*{_SOURCE_ANSWER_TARGET})?\s*[。！!？?]?$"
)
_SOURCE_ANSWER_NEGATED_RE = re.compile(
    rf"(?:不要|无需|不需要|不必|不用|暂不|别)"
    rf"(?:再|先|生成|给出|提供|写|做|输出|附上|包含)?"
    rf"[^。！？!?，,；;\n]{{0,8}}{_SOURCE_ANSWER_TARGET}"
)
_EXAM_DOCUMENT_NOUN_RE = re.compile(r"(?:试卷|考试卷|补考卷|重修卷|整卷)")
_ARTIFACT_FORMAT = r"(?:PDF|TeX|LaTeX)"
_ARTIFACT_FORMAT_LIST = (
    rf"{_ARTIFACT_FORMAT}"
    rf"(?:\s*(?:和|与|及|、|/|\\)\s*{_ARTIFACT_FORMAT})?"
)
_ARTIFACT_DELIVERY_ACTION = (
    rf"(?:"
    rf"(?:重新|再次|再)?\s*编译(?:一下)?"
    rf"(?:\s*(?:成|为)\s*{_ARTIFACT_FORMAT})?(?:\s*文件)?|"
    rf"(?:生成|制作|导出|输出|提供|给出|下载)"
    rf"(?:\s*(?:成|为))?\s*(?:一份|一个)?\s*"
    rf"(?:编译好(?:的)?\s*)?{_ARTIFACT_FORMAT_LIST}(?:\s*文件)?|"
    rf"(?:转(?:换)?\s*(?:成|为))\s*{_ARTIFACT_FORMAT_LIST}(?:\s*文件)?"
    rf")"
)
_ARTIFACT_DELIVERY_ACTION_RE = re.compile(_ARTIFACT_DELIVERY_ACTION, re.I)
_ARTIFACT_DELIVERY_VERB_RE = re.compile(
    r"(?:重新|再次|再)?\s*编译|生成|制作|导出|输出|提供|给出|下载|转(?:换)?\s*(?:成|为)",
    re.I,
)
_ARTIFACT_FORMAT_RE = re.compile(_ARTIFACT_FORMAT, re.I)
_ARTIFACT_DELIVERY_SHORT_RE = re.compile(
    rf"^(?:(?:请|请你|请帮我|帮我|麻烦|劳驾)\s*)?"
    rf"(?:给我\s*)?{_ARTIFACT_DELIVERY_ACTION}"
    rf"(?:\s*(?:给我|一下|吧))?\s*[。！!？?]?$",
    re.I,
)
_ARTIFACT_EXISTING_REFERENCE_RE = re.compile(
    r"(?:上(?:面|述|一条)|前(?:面|述|一条)|刚才|方才|此前|之前|已有|现有|历史(?:回答|答案)|"
    r"这(?:份|段|个)|该(?:份|段|个)|此(?:份|段|个)|"
    r"(?:回答|答案|解答|解析|内容|代码|文件|TeX|LaTeX)(?:中|里|代码|文件)?)",
    re.I,
)
_ARTIFACT_DELIVERY_INQUIRY_RE = re.compile(
    r"(?:如何|怎样|怎么).{0,24}(?:编译|转(?:换)?(?:成|为)|生成|导出).{0,16}(?:PDF|TeX|LaTeX)?|"
    r"(?:为什么|为何).{0,24}(?:编译|PDF|TeX|LaTeX)|"
    r"(?:编译|PDF|TeX|LaTeX).{0,24}(?:为什么|为何|原因(?:是什么|是|在于)?|怎么回事)|"
    r"(?:分析|解释|说明|检查|排查).{0,20}(?:编译|PDF|TeX|LaTeX).{0,20}"
    r"(?:失败|错误|异常|问题|原因)",
    re.I,
)
_ARTIFACT_REVISION_RE = re.compile(
    r"(?:修改|修正|更正|改写|重写|重新排版|重排|排版|替换|补充|增补|"
    r"删(?:除|去)|移除|调整|更新|完善|优化|润色|改成|改为)",
    re.I,
)


def _enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return str(value or "").strip().lower() in _TRUE_VALUES


def _scalar(value: object, *, maximum: int = 300) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return ""
        value = value[0]
    normalized = _SPACE_RE.sub(" ", str(value or "")).strip()
    return normalized[:maximum]


def _terms(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidates = re.split(r"[,，;；、\n]+", value)
    elif isinstance(value, Sequence):
        candidates = [str(item) for item in value]
    else:
        candidates = [str(value)]
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _scalar(candidate, maximum=80)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        parts: list[str] = []
        for item in content:
            if isinstance(item, Mapping) and item.get("type") == "text":
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _full_exam_request_window(
    task: object,
    history: Sequence[Mapping[str, object]] | None = None,
) -> str:
    """Return the active full-exam user request and its metadata follow-ups.

    Requiring the course and full-exam action in the same anchor message keeps a
    completed older request from hijacking a later, unrelated teacher question.
    """
    current = _scalar(task, maximum=4000)
    user_messages: list[str] = []
    for message in list(history or ())[-12:]:
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        text = _message_text(message.get("content"))
        if text:
            user_messages.append(text[:4000])
    if not user_messages or user_messages[-1] != current:
        user_messages.append(current)
    user_messages = user_messages[-6:]

    anchor = -1
    for index in range(len(user_messages) - 1, -1, -1):
        candidate = user_messages[index]
        if (
            _FULL_EXAM_ACTION_RE.search(candidate)
            and _UNIVERSITY_PHYSICS_COURSE_RE.search(candidate)
            and not _EXAM_INQUIRY_RE.search(candidate)
        ):
            anchor = index
            break
    if anchor < 0:
        return ""
    if anchor != len(user_messages) - 1:
        # Only metadata-like replies continue a pending preflight. Ordinary
        # later questions must not inherit an old unfinished exam request.
        if not any(regex.search(current) for regex in (
            _ACADEMIC_YEAR_RE,
            _TERM_RE,
            _EXAM_NAME_LABEL_RE,
            _EXAM_TYPE_RE,
        )):
            return ""
    return "\n".join(user_messages[anchor:])


def classify_teacher_exam_request(
    task: object,
    history: Sequence[Mapping[str, object]] | None = None,
    *,
    has_attachments: bool = False,
) -> str:
    """Classify a teacher request without asking the model to infer routing.

    A full-exam request is the only kind allowed to enter the structured
    Blueprint/TeX/PDF pipeline.  Answering, reviewing or grading material that
    the teacher supplied must stay a normal teacher-model response, even when
    the supplied document itself contains words such as ``试卷`` or ``考试``.
    """
    current = _scalar(task, maximum=4000)
    source_material_action = bool(_SOURCE_MATERIAL_ACTION_RE.search(current))
    explicit_source_reference = bool(
        _SOURCE_MATERIAL_REFERENCE_RE.search(current)
        or _ANSWER_FOR_EXISTING_MATERIAL_RE.search(current)
    )
    if source_material_action and (has_attachments or explicit_source_reference):
        return EXAM_REQUEST_SOURCE_MATERIAL
    if _full_exam_request_window(current, history):
        return EXAM_REQUEST_FULL_GENERATION
    if source_material_artifact_requested(current):
        return EXAM_REQUEST_SOURCE_MATERIAL
    if source_material_action:
        return EXAM_REQUEST_SOURCE_MATERIAL
    return EXAM_REQUEST_GENERAL


def source_material_answer_requested(task: str) -> bool:
    """Return whether supplied material should produce an answer deliverable.

    This deliberately excludes broad review operations such as ``审核试卷`` or
    ``分析难度``.  It is limited to an explicit request for answers, solving,
    explanations, or an operational scoring standard/rubric.
    """
    text = _scalar(task, maximum=4000)
    if not text:
        return False
    positive_text = _SOURCE_ANSWER_NEGATED_RE.sub("", text).strip()
    if not _SOURCE_ANSWER_TARGET_RE.search(positive_text):
        return False

    explicit_source_reference = bool(
        _SOURCE_MATERIAL_REFERENCE_RE.search(positive_text)
        or _ANSWER_FOR_EXISTING_MATERIAL_RE.search(positive_text)
    )
    if (
        _FULL_EXAM_ACTION_RE.search(positive_text)
        and _EXAM_DOCUMENT_NOUN_RE.search(positive_text)
        and not explicit_source_reference
    ):
        # "生成一份新试卷并附答案" is still an exam-generation request.
        return False
    if _SOURCE_ANSWER_BARE_RE.fullmatch(positive_text):
        return True
    if _SOURCE_ANSWER_DIRECT_RE.search(positive_text):
        return True
    return bool(_SOURCE_ANSWER_DELIVERY_RE.search(positive_text))


def source_material_artifact_requested(task: object) -> bool:
    """Return whether an existing answer/TeX should be delivered as files.

    This is intentionally narrower than a keyword search.  Short imperative
    follow-ups such as ``编译成 PDF`` are accepted because their source is the
    preceding answer.  Longer requests must explicitly refer to existing
    content.  Questions about how compilation works or why it failed remain
    ordinary teacher Q&A, and creating a new exam remains the full-generation
    route.
    """
    text = _scalar(task, maximum=4000)
    if not text:
        return False
    if _ARTIFACT_DELIVERY_INQUIRY_RE.search(text):
        return False
    direct_action = bool(_ARTIFACT_DELIVERY_ACTION_RE.search(text))
    if direct_action and _ARTIFACT_DELIVERY_SHORT_RE.fullmatch(text):
        return True
    existing_reference = bool(_ARTIFACT_EXISTING_REFERENCE_RE.search(text))
    if not existing_reference:
        return False
    if not direct_action and not (
        _ARTIFACT_DELIVERY_VERB_RE.search(text)
        and _ARTIFACT_FORMAT_RE.search(text)
    ):
        return False
    if (
        _FULL_EXAM_ACTION_RE.search(text)
        and _EXAM_DOCUMENT_NOUN_RE.search(text)
        and not _SOURCE_MATERIAL_REFERENCE_RE.search(text)
    ):
        return False
    return True


def source_material_artifact_revision_requested(task: object) -> bool:
    """Return whether file delivery first requires revising existing content.

    Pure compile/export follow-ups may safely reuse an existing TeX/PDF pair.
    Requests that also ask to edit, replace, supplement or re-typeset content
    must go through the teacher model before the revised answer is compiled.
    """
    text = _scalar(task, maximum=4000)
    return bool(
        text
        and source_material_artifact_requested(text)
        and _ARTIFACT_REVISION_RE.search(text)
    )


def exam_generation_metadata_prompt(
    task: object,
    history: Sequence[Mapping[str, object]] | None = None,
) -> str:
    """Ask for mandatory full-exam metadata, or return an empty string."""
    request = _full_exam_request_window(task, history)
    if not request:
        return ""
    missing: list[str] = []
    if not _ACADEMIC_YEAR_RE.search(request):
        missing.append("学年（例如：2025—2026学年）")
    if not _TERM_RE.search(request):
        missing.append("学期（例如：第一学期）")
    if not (_EXAM_NAME_LABEL_RE.search(request) or _EXAM_TYPE_RE.search(request)):
        missing.append("考试名称或类型（例如：大学物理1期末考试、大学物理1补考）")
    if not missing:
        return ""
    lines = ["在生成整套试卷前，请补充以下信息："]
    lines.extend(f"- {item}" for item in missing)
    lines.extend((
        "",
        "考试日期可以暂不填写；未提供时会在试卷中留空，不会自行推断。",
        "请在下一条消息中一次性补全上述缺失信息，收到后我再生成试卷。",
    ))
    return "\n".join(lines)


def exam_direct_output_policy(
    task: object,
    history: Sequence[Mapping[str, object]] | None = None,
) -> tuple[bool | None, bool, bool | None]:
    """Return (must_be_makeup, exclude_relativity, exam_date_provided)."""
    request = _full_exam_request_window(task, history)
    if not request:
        return None, False, None

    classifications: list[tuple[int, bool]] = []
    for match in _NOT_MAKEUP_RE.finditer(request):
        classifications.append((match.start(), False))
    for match in re.finditer(r"补考", request):
        if not _NOT_MAKEUP_RE.search(request[max(0, match.start() - 8):match.end()]):
            classifications.append((match.start(), True))
    for match in _NON_MAKEUP_EXAM_TYPE_RE.finditer(request):
        classifications.append((match.start(), False))
    for match in _EXAM_NAME_LABEL_RE.finditer(request):
        name = match.group(1)
        classifications.append((match.start(), "补考" in name and not _NOT_MAKEUP_RE.search(name)))
    classifications.sort(key=lambda item: item[0])
    makeup = classifications[-1][1] if classifications else None
    return (
        makeup,
        bool(_COURSE_ONE_OR_A_RE.search(request)),
        bool(_EXAM_DATE_RE.search(request)),
    )


def is_verified_teacher(account: Mapping[str, object] | None) -> bool:
    """Return True only for an active, roster-verified teacher account."""
    if not isinstance(account, Mapping):
        return False
    return (
        str(account.get("role") or "").strip().lower() == "teacher"
        and str(account.get("identity_type") or "").strip().lower() == "teacher"
        and bool(str(account.get("institutional_id") or "").strip())
        and _enabled(account.get("identity_verified"))
        and _enabled(account.get("is_active"))
    )


def normalize_teacher_exam_portal(value: object) -> str:
    """Normalize an allow-listed portal query value; reject every other value."""
    candidate = _scalar(value, maximum=64).lower()
    return TEACHER_EXAM_PORTAL if candidate in TEACHER_EXAM_PORTAL_ALLOWLIST else ""


def portal_query_value(value: object) -> str:
    """Convert an internal portal or accepted URL alias to its canonical URL value."""
    candidate = _scalar(value, maximum=64).lower()
    if candidate == PORTAL_ASSISTANT:
        return PORTAL_ASSISTANT
    if candidate == PORTAL_TEACHING_EXAM or candidate in TEACHER_EXAM_PORTAL_ALLOWLIST:
        return TEACHER_EXAM_PORTAL
    return ""


def _internal_portal(value: object) -> str | None:
    candidate = _scalar(value, maximum=64).lower()
    if candidate == PORTAL_ASSISTANT:
        return PORTAL_ASSISTANT
    if candidate == PORTAL_TEACHING_EXAM or candidate in TEACHER_EXAM_PORTAL_ALLOWLIST:
        return PORTAL_TEACHING_EXAM
    return None


def resolve_teacher_portal(
    account: Mapping[str, object] | None,
    query_value: object,
    session_value: object,
) -> str | None:
    """Resolve a verified teacher's URL/session choice to an internal portal."""
    if not is_verified_teacher(account):
        return None
    raw_query = _scalar(query_value, maximum=64)
    if raw_query:
        return _internal_portal(raw_query)
    return _internal_portal(session_value)


def sanitize_exam_query_params(
    query: Mapping[str, object] | None,
) -> dict[str, str]:
    """Keep only harmless, documented teacher-portal query parameters."""
    if not isinstance(query, Mapping):
        return {}
    sanitized: dict[str, str] = {}
    for key, value in query.items():
        normalized_key = str(key or "").strip()
        if normalized_key not in TEACHER_EXAM_QUERY_ALLOWLIST:
            continue
        normalized_value = _scalar(value)
        if normalized_key == TEACHER_EXAM_PORTAL_QUERY_KEY:
            normalized_value = normalize_teacher_exam_portal(normalized_value)
        if normalized_value:
            sanitized[normalized_key] = normalized_value
    return sanitized


def exam_retrieval_query(
    task: object,
    *,
    chapter: object = "",
    topics: object = (),
    question_types: object = (),
) -> str:
    """Build a compact RAG query from the physical scope, not UI boilerplate."""
    parts: list[str] = []
    chapter_text = _scalar(chapter, maximum=120)
    if chapter_text and chapter_text != "全部":
        parts.append(f"课程章节：{chapter_text}")
    topic_terms = _terms(topics)
    if topic_terms:
        parts.append("目标知识点：" + " ".join(topic_terms))
    type_terms = _terms(question_types)
    if type_terms:
        parts.append("题型：" + " ".join(type_terms))
    task_text = _scalar(task, maximum=1200)
    if task_text:
        parts.append(f"教师命题任务：{task_text}")
    return "\n".join(parts)
