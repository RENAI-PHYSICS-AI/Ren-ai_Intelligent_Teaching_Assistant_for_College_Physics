from __future__ import annotations

import html
import random
import re
import threading
import time
import traceback
import uuid

import streamlit as st
import streamlit.components.v1 as components

from answer_artifacts import build_answer_artifact_bundle
from build_kb import build
import admin_auth
import analytics_db
import user_session
from config import (
    APP_DIR,
    KB_FILE,
    TEACHER_EXAM_KB_FILE,
    TEACHER_EXAM_TEMPLATE_FILE,
    setting,
)
from exam_blueprint import (
    ExamBlueprintError,
    parse_exam_blueprint,
    render_exam_tex,
)
from exam_artifacts import (
    ExamArtifactError,
    build_exam_artifact_bundles,
    build_exam_download_archive,
    extract_named_tex_documents,
    stabilize_exam_tex_layout,
    validate_tex_document,
)
from experiment_hub import render_experiment_hub
from llm import ExamGenerationError, plan_visualization, stream_answer, visualization_requested
from proxy_paths import with_public_prefix
from rag import KnowledgeBase, context_text
from storage import (
    authenticate,
    clear_messages,
    create_user,
    delete_answer_turn,
    delete_unanswered_question,
    init_db,
    image_data_url,
    load_context_messages,
    load_message_artifacts,
    load_message_images,
    load_message_reference,
    load_messages,
    load_messages_page,
    messages_to_markdown,
    pdf_attachment_data,
    save_message,
)
from teacher_exam import (
    EXAM_QUICK_TASKS,
    EXAM_REQUEST_FULL_GENERATION,
    EXAM_REQUEST_SOURCE_MATERIAL,
    MANDATORY_EXAM_POLICY_CONTEXT,
    PORTAL_ASSISTANT,
    PORTAL_TEACHING_EXAM,
    classify_teacher_exam_request,
    exam_generation_metadata_prompt,
    exam_retrieval_query,
    is_verified_teacher,
    portal_query_value,
    resolve_teacher_portal,
    source_material_answer_requested,
    source_material_artifact_requested,
    source_material_artifact_revision_requested,
)
from text_formatting import normalize_latex_markdown
from uploaded_documents import prepare_uploaded_documents, raster_image_attachments
from visualization import apply_requested_media_format, extract_visualizations, render_visualizations
from voice_input import render_voice_input
from web_search import append_web_sources, search_web, should_search_web, web_context_text

st.set_page_config(page_title="大学物理智能助教", page_icon="⚛️", layout="wide", initial_sidebar_state="expanded")

theme_mode = st.query_params.get("mode", "system")
if theme_mode not in {"light", "system", "dark"}:
    theme_mode = "system"
dark_rules = """
.stApp,[data-testid="stAppViewContainer"] {background:linear-gradient(145deg,#111923 0%,#182431 100%)!important;color:#e8eef5!important;--mode-title:#edf3f8;--mode-muted:#9eafbf;--mode-hover:rgba(111,151,184,.12);--mode-active:rgba(255,93,102,.12);--mode-border:rgba(255,93,102,.36)}
[data-testid="stBottomBlockContainer"] {background:#0d141d!important}
.welcome,.welcome *,.quick-head {color:#edf3f8!important}
.quick-note,.tip {color:#c7d2de!important}
.course-map,.course-map * {color:#d7e0e9!important}
.course-map b {color:#f4f7fa!important}
.stButton>button {background:#1e2b38!important;color:#edf3f8!important;border-color:#425a70!important}
.stButton>button p {color:#edf3f8!important}
.stButton>button:hover {background:#263747!important;color:white!important;border-color:#69a4d2!important}
[data-testid="stChatInput"] {background:#182431!important;border-color:#425a70!important}
[data-testid="stChatInput"] textarea {color:#edf3f8!important;-webkit-text-fill-color:#edf3f8!important}
[data-testid="stChatInput"] textarea::placeholder {color:#9eafbf!important;-webkit-text-fill-color:#9eafbf!important}
"""
light_rules = """
.stApp {background:linear-gradient(145deg,#f7f9fc 0%,#edf2f7 100%);color:#26384a;--mode-title:#17324d;--mode-muted:#718296;--mode-hover:rgba(55,103,140,.07);--mode-active:rgba(255,75,85,.08);--mode-border:rgba(255,75,85,.28)}
"""
if theme_mode == "dark":
    theme_css = dark_rules
elif theme_mode == "light":
    theme_css = light_rules
else:
    theme_css = light_rules + "\n@media (prefers-color-scheme: dark) {\n" + dark_rules + "\n}"

portal_link_value = portal_query_value(st.query_params.get("portal", ""))
portal_link_suffix = f"&portal={portal_link_value}" if portal_link_value else ""
theme_links = "".join(
    f'<a class="theme-option{" active" if theme_mode == value else ""}" href="?mode={value}{portal_link_suffix}" '
    f'target="_self" title="{label}" aria-label="{label}">{icon}</a>'
    for value, icon, label in (
        ("light", "☀️", "亮色模式"),
        ("system", "◐", "跟随系统"),
        ("dark", "🌙", "暗色模式"),
    )
)

page_markup = """
<style>
__THEME_CSS__
#MainMenu,[data-testid="stToolbarActions"],[data-testid="stStatusWidget"],[data-testid="stAppDeployButton"] {display:none!important}
[data-testid="stHeader"] {display:block!important;background:transparent!important;pointer-events:none!important}
[data-testid="stHeader"] [data-testid="stExpandSidebarButton"] {display:flex!important;z-index:999999!important;pointer-events:auto!important;border:1px solid rgba(128,145,163,.26)!important;border-radius:.65rem!important;background:rgba(128,145,163,.16)!important;color:var(--mode-title,#edf3f8)!important;box-shadow:0 3px 12px rgba(9,20,31,.16)!important;backdrop-filter:blur(8px);transition:background .16s ease,transform .16s ease}
[data-testid="stHeader"] [data-testid="stExpandSidebarButton"]:hover {background:rgba(128,145,163,.28)!important;transform:translateY(-1px)}
[data-testid="stHeader"] [data-testid="stExpandSidebarButton"] svg {color:inherit!important;fill:currentColor!important}
.theme-switcher {position:fixed;right:1.15rem;top:.72rem;z-index:999999;display:flex;align-items:center;gap:.12rem;padding:.2rem;border-radius:1.4rem;background:rgba(128,145,163,.13);border:1px solid rgba(128,145,163,.2);backdrop-filter:blur(8px)}
.theme-option {text-decoration:none!important;width:1.9rem;height:1.9rem;border-radius:50%;display:flex;align-items:center;justify-content:center;color:inherit;font-size:.92rem;opacity:.58;transition:background .16s ease,opacity .16s ease,transform .16s ease}
.theme-option:hover {background:rgba(128,145,163,.18);opacity:1;transform:translateY(-1px)}
.theme-option.active {background:rgba(76,119,153,.24);box-shadow:0 1px 5px rgba(23,50,77,.14);opacity:1}
.block-container {max-width: 980px; padding-top: 3.2rem; padding-bottom: 1rem}
.sidebar-brand {position:relative;overflow:hidden;margin:.15rem 0 .85rem;padding:.85rem .8rem .75rem;border-radius:15px;background:linear-gradient(135deg,#17324d 0%,#214b6c 100%);color:#fff;box-shadow:0 8px 22px rgba(15,42,66,.18)}
.sidebar-brand::after {content:"";position:absolute;width:6rem;height:6rem;right:-2.7rem;top:-3.2rem;border-radius:50%;background:rgba(126,101,229,.18);pointer-events:none}
.sidebar-brand-head {position:relative;z-index:1;display:flex;align-items:center;gap:.55rem;white-space:nowrap}
.sidebar-brand-logo {display:inline-flex;width:2.3rem;height:2.3rem;align-items:center;justify-content:center;flex:0 0 auto;border-radius:10px;background:linear-gradient(145deg,#7654db,#a47cf0);color:#fff;font-family:"Segoe UI Symbol",sans-serif;font-size:1.48rem;line-height:1;box-shadow:0 5px 13px rgba(87,54,172,.32)}
.sidebar-brand-name {font-size:1.04rem;font-weight:830;letter-spacing:-.02em}
.sidebar-brand-subtitle {position:relative;z-index:1;margin:.62rem 0 0;color:rgba(255,255,255,.82);font-size:.74rem;line-height:1.55}
.sidebar-brand-features {position:relative;z-index:1;margin-top:.28rem;color:rgba(255,255,255,.64);font-size:.68rem;line-height:1.5}
.welcome {max-width:800px;margin:0 auto .6rem;color:#26384a;font-size:.91rem;line-height:1.42}
.welcome-line {display:flex;align-items:center;gap:.65rem;margin-bottom:.25rem}
.bot-icon {display:inline-flex;width:2rem;height:2rem;align-items:center;justify-content:center;border-radius:9px;background:#ff9f1c;color:white;flex:0 0 auto}
.welcome ul {margin:.15rem 0 .35rem 2.75rem;padding-left:1rem}
.course-map {margin:.2rem 0 0 2.75rem;color:#40556a}
.course-map b {color:#17324d}
.tip {margin:.4rem 0 0 2.75rem;color:#66788a}
.quick-head {text-align:center;margin:.65rem 0 .1rem;color:#17324d;font-size:1.2rem;font-weight:750}
.quick-note {text-align:center;color:#66788a;margin-bottom:.45rem;font-size:.9rem}
[data-testid="stSegmentedControl"] {margin-bottom:.45rem}
[data-testid="stSegmentedControl"] button {min-height:2.5rem;font-weight:700}
.auth-card {padding:.3rem 0 .7rem;text-align:center}
.auth-card h2 {margin:.15rem 0 .35rem;color:inherit;font-size:1.35rem}
.auth-card p {margin:0 0 .8rem;opacity:.72;font-size:.92rem;line-height:1.6}
.teacher-portal-card {box-sizing:border-box;display:flex;height:10.25rem;min-height:10.25rem;flex-direction:column;margin:.25rem 0 .55rem;padding:1.05rem 1.1rem;border:1px solid rgba(128,145,163,.25);border-radius:16px;background:rgba(128,145,163,.08)}
.teacher-portal-card h3 {margin:0 0 .45rem;font-size:1.12rem;color:inherit}
.teacher-portal-card p {margin:0;opacity:.76;line-height:1.65;font-size:.9rem}
@media (max-width:640px) {.teacher-portal-card {height:auto;min-height:0}}
.teacher-agent-badge {margin:-.15rem 0 .65rem;padding:.5rem .65rem;border-radius:10px;background:rgba(117,105,220,.11);font-size:.84rem;font-weight:700}
.stButton>button {min-height:2.55rem;border:1px solid #d7e0e8;border-radius:12px;background:rgba(255,255,255,.94);color:#17324d;font-weight:650;text-align:left;padding:.35rem .85rem;box-shadow:0 4px 14px rgba(23,50,77,.05);transition:all .16s ease}
.stButton>button:hover {border-color:#3d739d;color:#0f3555;transform:translateY(-1px);box-shadow:0 8px 20px rgba(23,50,77,.1)}
.source {border-left:4px solid #c8923a;padding:.55rem .8rem;background:white;border-radius:6px;margin:.35rem 0}
.thinking-state {display:flex;align-items:center;gap:.8rem;padding:.6rem .1rem;color:inherit;font-weight:650}
.thinking-orb {width:1.15rem;height:1.15rem;border-radius:50%;border:3px solid rgba(80,126,163,.28);border-top-color:#5f9ccc;animation:thinking-spin .85s linear infinite;flex:0 0 auto}
.thinking-dots span {display:inline-block;animation:thinking-bounce 1.2s infinite;opacity:.28}
.thinking-dots span:nth-child(2){animation-delay:.16s}.thinking-dots span:nth-child(3){animation-delay:.32s}
[data-testid="stSidebar"] .stButton>button {min-height:2.7rem;font-size:.86rem;text-align:left;margin-bottom:.12rem}
[data-testid="stSidebar"] .sidebar-quick-note {font-size:.8rem;opacity:.7;margin:-.3rem 0 .55rem}
.sidebar-mode-title {display:flex;align-items:center;gap:.55rem;margin:.15rem .15rem .65rem;color:var(--mode-title);line-height:1}
.sidebar-mode-icon {display:inline-flex;width:1.9rem;height:1.9rem;align-items:center;justify-content:center;border-radius:9px;background:linear-gradient(145deg,rgba(117,105,220,.2),rgba(70,154,196,.16));font-size:1.02rem;box-shadow:inset 0 0 0 1px rgba(127,145,170,.14)}
.sidebar-mode-label {font-size:1.05rem;font-weight:780;letter-spacing:.02em}
.sidebar-mode-help {display:inline-flex;width:1.15rem;height:1.15rem;align-items:center;justify-content:center;margin-left:.05rem;border:1.5px solid var(--mode-muted);border-radius:50%;color:var(--mode-muted);font-size:.73rem;font-weight:800;cursor:help}
[data-testid="stSidebar"] [data-testid="stRadio"] {margin-top:-.2rem}
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {gap:.18rem}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {width:100%;min-height:2.65rem;margin:0;padding:.46rem .62rem;border:1px solid transparent;border-radius:11px;color:var(--mode-title);transition:background .16s ease,border-color .16s ease,transform .16s ease}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover {background:var(--mode-hover);transform:translateX(2px)}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {background:var(--mode-active);border-color:var(--mode-border)}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] p {font-size:.98rem;font-weight:680;color:var(--mode-title);line-height:1.35}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p {font-weight:800}
@keyframes thinking-spin {to{transform:rotate(360deg)}}
@keyframes thinking-bounce {0%,60%,100%{transform:translateY(0);opacity:.28}30%{transform:translateY(-3px);opacity:1}}
</style>
<div class="theme-switcher" role="group" aria-label="亮度模式">__THEME_LINKS__</div>
"""
st.markdown(page_markup.replace("__THEME_CSS__", theme_css)
                       .replace("__THEME_LINKS__", theme_links), unsafe_allow_html=True)

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
          <div class="sidebar-brand-head">
            <span class="sidebar-brand-logo">⚛</span>
            <span class="sidebar-brand-name">大学物理智能助教</span>
          </div>
          <div class="sidebar-brand-subtitle">以祝之光《物理学》第5版为课程基准</div>
          <div class="sidebar-brand-features">本地 RAG 核心 · 网络内容补充 · 图片识题 · 交互式物理实验</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

QUICK_QUESTIONS = [
    "速度和速率有什么本质区别？", "为什么圆周运动的加速度指向圆心？",
    "牛顿第二定律适用于哪些参考系？", "动量守恒需要满足什么条件？",
    "功能原理与机械能守恒有什么区别？", "如何计算刚体绕定轴的转动惯量？",
    "简谐振动的相位有什么物理意义？", "受迫振动为什么会发生共振？",
    "机械波传递的究竟是什么？", "如何判断驻波的波节和波腹？",
    "气体压强的微观本质是什么？", "卡诺循环效率为什么不能达到100%？",
    "高斯定理什么时候最适合求电场？", "电势为零的地方电场一定为零吗？",
    "洛伦兹力为什么不对带电粒子做功？", "楞次定律如何快速判断感应电流方向？",
    "杨氏双缝干涉条纹间距怎样推导？", "单缝衍射中央明纹为什么最宽？",
    "光电效应为什么支持光的粒子性？", "德布罗意波长与动量有什么关系？",
    "请给我一道动量守恒的典型例题", "请用能量法讲解一道斜面问题",
    "如何检查大学物理计算题的单位？", "矢量分解时最容易犯哪些错误？",
]


def new_quick_questions() -> list[str]:
    return random.sample(QUICK_QUESTIONS, 4)


def normalize_latex(text: str) -> str:
    """Convert model-style TeX delimiters to Streamlit's reliable dollar syntax."""
    return normalize_latex_markdown(text)


_EXAM_TEX_FENCE_RE = re.compile(
    r"```\s*(?:latex|tex)(?:[^\r\n`]*)\r?\n.*?```", re.I | re.S
)
_EXAM_TEX_LABEL_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?(?:文件\s*[:：]\s*)?(?:main|answer)\.tex\s*[:：]?\s*$"
)
_EXAM_BINARY_MARKER_RE = re.compile(
    r"(?:%PDF-\d|\b(?:xref|startxref|endstream)\b|<~[!-u\s]{12,}~>)", re.I | re.S
)
_EXAM_REVISION_WORDS = (
    "继续", "续写", "修改", "改为", "调整", "补充", "重做", "重新", "上一版",
    "刚才", "重复", "严格", "每题", "不要", "删除", "保持", "沿用", "修正",
)
_EXAM_ARTIFACT_ORDER = {
    "main.tex": 0,
    "main.pdf": 1,
    "answer.tex": 2,
    "answer.pdf": 3,
    "大学物理试卷完整包.zip": 4,
}
_EXAM_ARTIFACT_TOTAL_BYTES = 16 * 1024**2


def _append_exam_download_archive(artifacts: list[dict], archive) -> None:
    """Add a ZIP without exceeding history storage; ZIP alone is self-contained."""
    if archive is None:
        return
    entry = {
        "name": archive.zip_name,
        "mime": archive.zip_mime,
        "data": archive.zip_bytes,
    }
    current_bytes = sum(len(item.get("data", b"")) for item in artifacts)
    if current_bytes + len(archive.zip_bytes) <= _EXAM_ARTIFACT_TOTAL_BYTES:
        artifacts.append(entry)
    else:
        # The archive already contains both TeX/PDF pairs and all referenced
        # images, so it is the lossless compact handoff when duplicates would
        # exceed the database total-size limit.
        artifacts[:] = [entry]


def exam_output_looks_binary(text: str) -> bool:
    """Reject model-produced PDF/ASCII85 streams before Markdown sees them."""
    candidate = str(text or "")
    if _EXAM_BINARY_MARKER_RE.search(candidate):
        return True
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", candidate):
        return True
    if (
        not _EXAM_TEX_FENCE_RE.search(candidate)
        and "\\documentclass" in candidate
        and "\\begin{document}" in candidate
        and "\\end{document}" in candidate
    ):
        return False
    probe = _EXAM_TEX_FENCE_RE.sub("\n", candidate)
    samples = [probe[:1600], *re.split(r"[\u3400-\u9fff]+", probe)]
    for sample in samples:
        if len(sample) < 240:
            continue
        printable = [char for char in sample[:1600] if not char.isspace()]
        if not printable:
            continue
        punctuation = sum(
            not (char.isalnum() or char in "_\\{}[]().,:;+-=*/") for char in printable
        )
        if punctuation / len(printable) >= 0.18:
            return True
    return False


def exam_response_summary(text: str, *, maximum: int = 1200) -> str:
    """Keep concise Chinese prose while removing generated TeX source fences."""
    cleaned = _EXAM_TEX_FENCE_RE.sub("\n", str(text or ""))
    cleaned = _EXAM_TEX_LABEL_RE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if len(cleaned) > maximum:
        cleaned = cleaned[:maximum].rstrip() + "……"
    return cleaned


def exam_retrieval_task(question: str, messages: list[dict]) -> str:
    """Resolve short revision requests against the preceding teacher task."""
    current = str(question or "").strip()
    is_revision = len(current) <= 160 or any(word in current for word in _EXAM_REVISION_WORDS)
    if not is_revision:
        return current
    previous = next(
        (
            str(message.get("content") or "").strip()
            for message in reversed(messages)
            if message.get("role") == "user" and str(message.get("content") or "").strip()
        ),
        "",
    )
    if not previous or previous == current:
        return current
    return f"上一轮教师命题任务：{previous}\n本轮修订要求：{current}"


def merge_exam_retrieval_results(
    private_results: list[tuple[object, float]],
    public_results: list[tuple[object, float]],
    *,
    maximum: int = 10,
) -> list[tuple[object, float]]:
    """Keep private exam evidence first and remove public/private duplicates."""
    merged: list[tuple[object, float]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk, score in [*private_results, *public_results]:
        key = (
            str(getattr(chunk, "relative_path", "") or getattr(chunk, "source", "")).strip(),
            str(getattr(chunk, "locator", "") or getattr(chunk, "page", "")).strip(),
            re.sub(r"\s+", "", str(getattr(chunk, "text", "")))[:240],
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append((chunk, score))
        if len(merged) >= maximum:
            break
    return merged


@st.cache_resource(show_spinner=False)
def load_kb(stamp: float):
    return KnowledgeBase(KB_FILE)


@st.cache_resource(show_spinner=False)
def load_private_teacher_exam_kb(private_stamp: float):
    return KnowledgeBase(TEACHER_EXAM_KB_FILE)


@st.cache_resource(show_spinner=False)
def exam_generation_lock():
    """Match the dedicated DeepSeek service's single generation slot."""
    return threading.Lock()


@st.cache_resource(show_spinner=False)
def initialize_storage():
    init_db()
    analytics_db.init_db()
    admin_username = setting("ADMIN_USERNAME")
    admin_password = setting("ADMIN_PASSWORD")
    if admin_username and len(admin_password) >= 12:
        analytics_db.ensure_admin_user(
            admin_username,
            admin_password,
            setting("ADMIN_DISPLAY_NAME", "管理员"),
        )
    return True


initialize_storage()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "username" not in st.session_state:
    st.session_state.username = "匿名用户"
if "user_role" not in st.session_state:
    st.session_state.user_role = "anonymous"
if "access_granted" not in st.session_state:
    st.session_state.access_granted = False
if "quick_questions" not in st.session_state:
    st.session_state.quick_questions = new_quick_questions()
if "_answer_in_progress" not in st.session_state:
    st.session_state._answer_in_progress = False
if "_history_has_more" not in st.session_state:
    st.session_state._history_has_more = False
if "_history_paged_user_id" not in st.session_state:
    st.session_state._history_paged_user_id = None
if "_history_paged_agent_mode" not in st.session_state:
    st.session_state._history_paged_agent_mode = None
if "_analytics_last_touch" not in st.session_state:
    st.session_state._analytics_last_touch = 0.0
if "_voice_commit_id" not in st.session_state:
    st.session_state._voice_commit_id = None
if "_quoted_message" not in st.session_state:
    st.session_state._quoted_message = None
HISTORY_PAGE_SIZE = 8
REFERENCE_PREVIEW_CHARS = 180
REFERENCE_CONTEXT_CHARS = 48_000


def reset_analytics_session() -> None:
    previous = st.session_state.get("analytics_session_id")
    if previous:
        analytics_db.end_session(
            previous,
            st.session_state.get("analytics_total_questions", 0),
            st.session_state.get("analytics_total_errors", 0),
            st.session_state.get("analytics_tokens_input", 0),
            st.session_state.get("analytics_tokens_output", 0),
        )
    st.session_state.analytics_session_id = analytics_db.start_session(st.session_state.user_id)
    st.session_state.analytics_session_user_id = st.session_state.user_id
    st.session_state.analytics_total_questions = 0
    st.session_state.analytics_total_errors = 0
    st.session_state.analytics_tokens_input = 0
    st.session_state.analytics_tokens_output = 0


def refresh_account_state() -> dict:
    if st.session_state.user_id is None:
        st.session_state.user_role = "anonymous"
        return {}
    account = analytics_db.get_user_by_id(st.session_state.user_id)
    if not account or not account.get("is_active"):
        st.session_state.user_id = None
        st.session_state.username = "匿名用户"
        st.session_state.user_role = "anonymous"
        st.session_state.messages = []
        reset_history_view()
        st.session_state.access_granted = False
        st.session_state.pop("teacher_portal", None)
        return {}
    st.session_state.user_role = account.get("role", "student")
    return account


def active_agent_mode() -> str:
    if st.session_state.get("teacher_portal") == PORTAL_TEACHING_EXAM:
        return PORTAL_TEACHING_EXAM
    return PORTAL_ASSISTANT


def select_teacher_portal(portal: str) -> None:
    st.session_state.teacher_portal = portal
    st.query_params["portal"] = portal_query_value(portal)
    st.session_state.pop("workspace_mode", None)
    st.session_state.messages = []
    reset_history_view()


def leave_teacher_portal() -> None:
    st.session_state.pop("teacher_portal", None)
    if "portal" in st.query_params:
        del st.query_params["portal"]
    st.session_state.messages = []
    st.session_state.pop("workspace_mode", None)
    reset_history_view()


def render_teacher_portal_picker() -> None:
    left_space, chooser, right_space = st.columns([1, 2.15, 1])
    with chooser:
        st.markdown(
            """
            <div class="auth-card">
              <h2>选择教师工作入口</h2>
              <p>两个智能体使用同一大学物理知识库；教研考试另有教师专用命题资料层。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        assistant_col, exam_col = st.columns(2)
        with assistant_col:
            st.markdown(
                """<div class="teacher-portal-card"><h3>💬 智能助教</h3>
                <p>进入现有课程问答、图片识题和可视化物理实验。</p></div>""",
                unsafe_allow_html=True,
            )
            if st.button(
                "进入智能助教",
                key="choose_teacher_assistant",
                use_container_width=True,
            ):
                select_teacher_portal(PORTAL_ASSISTANT)
                st.rerun()
        with exam_col:
            st.markdown(
                """<div class="teacher-portal-card"><h3>📝 教研考试</h3>
                <p>依据知识库命题、组卷、生成参考答案与评分标准。</p></div>""",
                unsafe_allow_html=True,
            )
            if st.button(
                "进入教研考试",
                key="choose_teacher_exam",
                use_container_width=True,
                type="primary",
            ):
                select_teacher_portal(PORTAL_TEACHING_EXAM)
                st.rerun()


def session_signing_secret() -> str:
    return (
        setting("ADMIN_TOKEN")
        or setting("ADMIN_ANALYTICS_TOKEN")
        or admin_auth.load_or_create_local_secret(
            APP_DIR / "data" / "admin_signing_secret"
        )
    )


def restore_persistent_login() -> bool:
    """Restore a signed browser login after a full page refresh."""
    if st.session_state.access_granted or st.session_state.user_id is not None:
        return False
    try:
        token = str(st.context.cookies.get(user_session.USER_SESSION_COOKIE, ""))
    except Exception:
        token = ""
    account = user_session.resolve_session(
        session_signing_secret(), token, analytics_db.get_user_by_username
    )
    if not account:
        return False
    st.session_state.user_id = int(account["id"])
    st.session_state.username = str(account["username"])
    st.session_state.user_role = str(account.get("role") or "student")
    st.session_state.access_granted = True
    return True


def user_session_target(action: str, username: str) -> str:
    if action == "login":
        internal_path = setting("USER_SESSION_LOGIN_URL", "/session-login")
        ticket = user_session.issue_login_ticket(session_signing_secret(), username)
    elif action == "logout":
        internal_path = setting("USER_SESSION_LOGOUT_URL", "/session-logout")
        ticket = user_session.issue_logout_ticket(session_signing_secret(), username)
    else:
        raise ValueError(f"Unsupported browser session action: {action}")
    target = with_public_prefix(
        internal_path,
        setting("PHYSICS_PUBLIC_BASE_URL", ""),
        setting("PHYSICS_GATEWAY_PUBLIC_PREFIX", ""),
    )
    separator = "&" if "?" in target else "?"
    return f"{target}{separator}ticket={ticket}&mode={theme_mode}"


def redirect_browser(target: str, message: str, button_label: str) -> None:
    safe_target = html.escape(target, quote=True)
    safe_message = html.escape(message)
    safe_button_label = html.escape(button_label)
    st.markdown(
        f"""
        <meta http-equiv="refresh" content="0; url={safe_target}">
        <div role="status" aria-live="polite" style="padding:.7rem 0;color:inherit">
          {safe_message}
          <small style="display:block;margin-top:.45rem;opacity:.72">
            若浏览器未自动跳转，<a href="{safe_target}" target="_self">{safe_button_label}</a>。
          </small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()


def admin_login_target() -> str:
    admin_token = session_signing_secret()
    admin_login_url = with_public_prefix(
        setting("ADMIN_LOGIN_URL", "/admin-login"),
        setting("PHYSICS_PUBLIC_BASE_URL", ""),
        setting("PHYSICS_GATEWAY_PUBLIC_PREFIX", ""),
    )
    ticket = admin_auth.issue_token(
        admin_token, st.session_state.username, "admin-login", 60
    )
    separator = "&" if "?" in admin_login_url else "?"
    return f"{admin_login_url}{separator}ticket={ticket}"


def redirect_admin_after_login() -> None:
    if st.session_state.user_role != "admin":
        return
    target = admin_login_target()
    redirect_browser(
        target,
        "管理员身份验证成功，正在进入管理后台……",
        "立即进入管理员后台",
    )


def message_ui_key(message: dict) -> str:
    message_id = message.get("id")
    if message_id is not None:
        return f"db_{int(message_id)}"
    ui_id = message.get("_ui_id")
    if not ui_id:
        ui_id = uuid.uuid4().hex
        message["_ui_id"] = ui_id
    return f"session_{ui_id}"


def reference_preview(value: object, maximum: int = REFERENCE_PREVIEW_CHARS) -> str:
    """Return a compact, single-line preview for a quoted assistant answer."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.replace("```", "").strip()
    limit = max(24, int(maximum))
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def select_history_reference(message: dict) -> None:
    """Remember one visible assistant answer for the next user turn."""
    if message.get("role") != "assistant":
        return
    st.session_state._quoted_message = {
        "id": message.get("id"),
        "agent_mode": active_agent_mode(),
        "content": str(message.get("content") or ""),
        "artifacts": list(message.get("artifacts") or []),
        "preview": reference_preview(message.get("content")),
        "session_key": message_ui_key(message),
    }


def resolve_selected_reference(*, include_artifacts: bool = False) -> dict | None:
    """Resolve the selected answer while enforcing user and portal ownership."""
    selected = st.session_state.get("_quoted_message")
    if not isinstance(selected, dict):
        return None
    mode = active_agent_mode()
    if selected.get("agent_mode") != mode:
        return None
    message_id = selected.get("id")
    if message_id is not None and st.session_state.user_id is not None:
        return load_message_reference(
            st.session_state.user_id,
            int(message_id),
            agent_mode=mode,
            include_artifacts=include_artifacts,
        )
    content = str(selected.get("content") or "")
    if not content:
        return None
    return {
        "id": None,
        "role": "assistant",
        "content": content,
        "artifacts": list(selected.get("artifacts") or []) if include_artifacts else [],
        "agent_mode": mode,
        "session_key": selected.get("session_key"),
    }


def latest_assistant_reference(*, include_artifacts: bool = False) -> dict | None:
    """Resolve the latest answer when an immediate PDF follow-up omits a quote."""
    mode = active_agent_mode()
    for message in reversed(st.session_state.messages):
        if message.get("role") != "assistant":
            continue
        message_id = message.get("id")
        if message_id is not None and st.session_state.user_id is not None:
            reference = load_message_reference(
                st.session_state.user_id,
                int(message_id),
                agent_mode=mode,
                include_artifacts=include_artifacts,
            )
            if reference is not None:
                return reference
            continue
        content = str(message.get("content") or "")
        if content:
            return {
                "id": None,
                "role": "assistant",
                "content": content,
                "artifacts": (
                    list(message.get("artifacts") or []) if include_artifacts else []
                ),
                "agent_mode": mode,
                "session_key": message_ui_key(message),
            }
    return None


def reference_model_context(reference: dict | None) -> str:
    """Build bounded context for the answer explicitly selected by the user."""
    if not reference:
        return ""
    sections = [str(reference.get("content") or "").strip()]
    for artifact in reference.get("artifacts") or []:
        name = str(artifact.get("name") or "").strip()
        if not name.lower().endswith(".tex"):
            continue
        payload = artifact.get("data", b"")
        if isinstance(payload, str):
            source = payload
        else:
            try:
                source = bytes(payload).decode("utf-8")
            except (TypeError, ValueError, UnicodeDecodeError):
                continue
        sections.append(f"[引用回答的可编辑文件：{name}]\n```latex\n{source}\n```")
    body = "\n\n".join(section for section in sections if section).strip()
    if not body:
        return ""
    if len(body) > REFERENCE_CONTEXT_CHARS:
        body = body[:REFERENCE_CONTEXT_CHARS].rstrip() + "\n[引用内容已截断]"
    return (
        "[用户本轮明确引用的历史回答]\n"
        "以下内容仅作为本轮问题的明确指代对象，请围绕用户当前要求处理。\n"
        f"{body}\n[历史回答引用结束]"
    )


def reference_compilation_input(reference: dict) -> str:
    """Prefer an attached answer TeX; otherwise compile the referenced response."""
    tex_artifacts = []
    for artifact in reference.get("artifacts") or []:
        name = str(artifact.get("name") or "").strip()
        if not name.lower().endswith(".tex"):
            continue
        payload = artifact.get("data", b"")
        if isinstance(payload, str):
            source = payload
        else:
            try:
                source = bytes(payload).decode("utf-8")
            except (TypeError, ValueError, UnicodeDecodeError):
                continue
        tex_artifacts.append((name, source))
    if tex_artifacts:
        name, source = next(
            (item for item in tex_artifacts if item[0].lower().endswith("answer.tex")),
            tex_artifacts[0],
        )
        return f"```latex answer.tex\n{source}\n```"
    return str(reference.get("content") or "")


def reusable_reference_artifacts(reference: dict) -> list[dict]:
    """Return already generated TeX/PDF bytes instead of recompiling them."""
    reusable = []
    for artifact in reference.get("artifacts") or []:
        name = str(artifact.get("name") or "").strip()
        if not name.lower().endswith((".tex", ".pdf")):
            continue
        payload = artifact.get("data", b"")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            continue
        reusable.append({
            "name": name,
            "mime": str(artifact.get("mime") or "application/octet-stream"),
            "data": bytes(payload),
        })
    has_tex = any(item["name"].lower().endswith(".tex") for item in reusable)
    has_pdf = any(item["name"].lower().endswith(".pdf") for item in reusable)
    return reusable if has_tex and has_pdf else []


def render_quoted_reference(message: dict) -> None:
    """Show the quoted-answer relationship on user messages."""
    if message.get("role") != "user":
        return
    preview = reference_preview(message.get("_quoted_preview"), maximum=120)
    quoted_id = message.get("quoted_message_id")
    if not preview and quoted_id is None:
        return
    label = f"回答 #{int(quoted_id)}" if quoted_id is not None else "历史回答"
    detail = f"：{preview}" if preview else ""
    st.caption(f"↪ 已引用{label}{detail}")


def save_session_history(user_id: int, agent_mode: str = PORTAL_ASSISTANT) -> None:
    """Persist an anonymous in-memory history while preserving turn links."""
    latest_user_message_id: int | None = None
    saved_reference_ids: dict[str, int] = {}
    for existing_message in st.session_state.messages:
        original_key = message_ui_key(existing_message)
        if existing_message.get("role") == "user":
            quoted_session_key = existing_message.get("_quoted_session_key")
            if quoted_session_key in saved_reference_ids:
                existing_message["quoted_message_id"] = saved_reference_ids[
                    quoted_session_key
                ]
            existing_message["id"] = save_message(
                user_id, existing_message, agent_mode=agent_mode
            )
            latest_user_message_id = int(existing_message["id"])
            continue
        existing_message["parent_message_id"] = latest_user_message_id
        existing_message["id"] = save_message(
            user_id, existing_message, agent_mode=agent_mode
        )
        saved_reference_ids[original_key] = int(existing_message["id"])


def clear_history_render_state() -> None:
    for key in list(st.session_state):
        if key.startswith(("_history_images_", "_history_artifacts_", "_history_viz_open_")):
            st.session_state.pop(key, None)


def load_initial_history(user_id: int, agent_mode: str | None = None) -> None:
    mode = agent_mode or active_agent_mode()
    messages, has_more = load_messages_page(
        user_id, limit=HISTORY_PAGE_SIZE, agent_mode=mode
    )
    st.session_state.messages = messages
    st.session_state._history_has_more = has_more
    st.session_state._history_paged_user_id = int(user_id)
    st.session_state._history_paged_agent_mode = mode
    st.session_state.pop("_pending_delete_message", None)
    st.session_state.pop("_quoted_message", None)
    clear_history_render_state()


def load_earlier_history() -> None:
    user_id = st.session_state.user_id
    if user_id is None or not st.session_state.messages:
        st.session_state._history_has_more = False
        return
    oldest_id = next(
        (message.get("id") for message in st.session_state.messages if message.get("id") is not None),
        None,
    )
    if oldest_id is None:
        st.session_state._history_has_more = False
        return
    earlier, has_more = load_messages_page(
        user_id,
        before_id=int(oldest_id),
        limit=HISTORY_PAGE_SIZE,
        agent_mode=active_agent_mode(),
    )
    known_ids = {
        int(message["id"])
        for message in st.session_state.messages
        if message.get("id") is not None
    }
    st.session_state.messages = [
        message for message in earlier if int(message["id"]) not in known_ids
    ] + st.session_state.messages
    st.session_state._history_has_more = has_more
    st.session_state.pop("_pending_delete_message", None)


def reset_history_view() -> None:
    st.session_state._history_has_more = False
    st.session_state._history_paged_user_id = None
    st.session_state._history_paged_agent_mode = None
    st.session_state.pop("_pending_delete_message", None)
    st.session_state.pop("_quoted_message", None)
    clear_history_render_state()


def render_history_images(message: dict) -> None:
    """Render raster images and uploaded PDF attachments for one chat message."""
    images = message.get("images", [])
    stable_key = message_ui_key(message)
    cache_key = f"_history_images_{stable_key}"
    if not images and message.get("_has_images") and st.session_state.user_id is not None:
        cached_images = st.session_state.get(cache_key)
        if cached_images is None:
            if st.button(
                "📎 显示历史附件",
                key=f"load_history_images_{stable_key}",
                help="仅在需要时读取原始图片或 PDF，以加快历史页面加载",
            ):
                st.session_state[cache_key] = load_message_images(
                    st.session_state.user_id,
                    int(message["id"]),
                    agent_mode=active_agent_mode(),
                )
                st.rerun()
            return
        images = cached_images
    for index, image in enumerate(images):
        source = image_data_url(image)
        if source:
            st.image(source, caption=image.get("name"), width=360)
            continue
        pdf_data = pdf_attachment_data(image)
        if pdf_data:
            name = str(image.get("name") or "document.pdf")
            st.caption(f"📄 PDF 附件：{name}")
            st.download_button(
                f"⬇️ 下载 {name}",
                data=pdf_data,
                file_name=name,
                mime="application/pdf",
                key=f"download_message_pdf_{stable_key}_{index}",
                on_click="ignore",
            )
            continue
        st.caption(f"附件无法显示：{image.get('name', '未命名文件')}")


def render_message_artifacts(message: dict) -> None:
    """Render teacher artifacts, loading historical bytes only when requested."""
    artifacts = list(message.get("artifacts") or [])
    stable_key = message_ui_key(message)
    cache_key = f"_history_artifacts_{stable_key}"
    if (
        not artifacts
        and message.get("_has_artifacts")
        and message.get("id") is not None
        and st.session_state.user_id is not None
    ):
        cached = st.session_state.get(cache_key)
        if cached is None:
            st.caption("此回答包含已生成的教研文件。")
            if st.button(
                "📎 加载教研文件",
                key=f"load_history_artifacts_{stable_key}",
                help="仅在需要下载时读取 TeX 与 PDF，以保持历史页面流畅",
            ):
                st.session_state[cache_key] = load_message_artifacts(
                    st.session_state.user_id,
                    int(message["id"]),
                    agent_mode=active_agent_mode(),
                )
                st.rerun()
            return
        artifacts = list(cached or [])
    if not artifacts:
        return

    ordered = sorted(
        artifacts,
        key=lambda item: (
            _EXAM_ARTIFACT_ORDER.get(str(item.get("name") or "").lower(), 99),
            str(item.get("name") or ""),
        ),
    )
    st.caption("教研文件已在服务器端安全生成：")
    columns = st.columns(min(4, len(ordered)))
    for index, artifact in enumerate(ordered):
        name = str(artifact.get("name") or f"exam-{index + 1}.bin")
        payload = artifact.get("data", b"")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        if not isinstance(payload, (bytes, bytearray)) or not payload:
            continue
        mime = str(artifact.get("mime") or "application/octet-stream")
        with columns[index % len(columns)]:
            st.download_button(
                f"⬇️ {name}",
                data=bytes(payload),
                file_name=name,
                mime=mime,
                key=f"download_exam_artifact_{stable_key}_{index}_{name}",
                use_container_width=True,
                on_click="ignore",
            )


def prepare_exam_response(
    raw_response: str,
    *,
    progress_callback=None,
) -> tuple[str, list[dict], str]:
    """Validate model text, compile named TeX files, and return safe chat prose."""
    def notify(event: str) -> None:
        if progress_callback is not None:
            progress_callback(event)

    raw = str(raw_response or "")
    notify("tex_validation_started")
    try:
        blueprint = parse_exam_blueprint(raw)
    except ExamBlueprintError:
        blueprint = None
    # A successfully parsed blueprint has already passed the stricter JSON,
    # field, control-character and binary-marker checks in exam_blueprint.py.
    # Running the generic punctuation-density heuristic first can misclassify
    # formula-heavy canonical JSON as an encoded file stream.
    if blueprint is None and exam_output_looks_binary(raw):
        notify("tex_validation_failed")
        return (
            "检测到模型返回了不可显示的文件数据流，本次内容已拦截，未写入历史记录。请重新生成试卷。",
            [],
            "binary_output",
        )
    if blueprint is not None:
        if blueprint.kind == "message":
            notify("artifact_generation_skipped")
            return normalize_latex(blueprint.summary), [], ""
        main_source, answer_source = render_exam_tex(blueprint)
        main_source = stabilize_exam_tex_layout(main_source)
        answer_source = stabilize_exam_tex_layout(answer_source)
        try:
            validate_tex_document(main_source)
            validate_tex_document(answer_source)
        except ExamArtifactError:
            notify("tex_validation_failed")
            return (
                "结构化命题已生成，但服务器端 TeX 安全校验未通过，"
                "本次未保存文件内容。请重新生成试卷。",
                [],
                "tex_validation_failed",
            )
        artifacts = [
            {
                "name": "main.tex",
                "mime": "application/x-tex",
                "data": main_source.encode("utf-8"),
            },
            {
                "name": "answer.tex",
                "mime": "application/x-tex",
                "data": answer_source.encode("utf-8"),
            },
        ]
        compiler_input = (
            f"```latex main.tex\n{main_source}```\n"
            f"```latex answer.tex\n{answer_source}```"
        )
        notify("tex_validation_complete")
        notify("pdf_compile_started")
        try:
            bundles = build_exam_artifact_bundles(compiler_input)
        except ExamArtifactError:
            notify("pdf_compile_failed")
            return (
                normalize_latex(
                    f"{blueprint.summary}\n\n结构化命题已经通过校验并生成 TeX，"
                    "但 PDF 服务器端编译失败。可先下载 TeX；详细编译日志不会写入聊天正文。"
                ),
                artifacts,
                "pdf_compile_failed",
            )
        notify("pdf_compile_complete")
        artifacts.extend({
            "name": bundle.pdf_name,
            "mime": bundle.pdf_mime,
            "data": bundle.pdf_bytes,
        } for bundle in bundles)
        # Structured fallback does not reference external images, so this is
        # normally None. Keeping the call here makes the delivery behavior
        # consistent if a future validated renderer gains trusted diagrams.
        try:
            archive = build_exam_download_archive(bundles)
        except ExamArtifactError:
            archive = None
        _append_exam_download_archive(artifacts, archive)
        return (
            normalize_latex(
                f"{blueprint.summary}\n\n试卷与参考答案已经通过结构、分值和重复题检查，"
                "并在服务器端生成 TeX 与 PDF。"
            ),
            artifacts,
            "",
        )

    artifact_intent = bool(
        "\\documentclass" in raw
        or re.search(r"(?i)(?:main|answer)\.tex", raw)
        or re.search(r"```\s*(?:latex|tex)\b", raw)
    )
    if not artifact_intent:
        notify("artifact_generation_skipped")
        return normalize_latex(raw), [], ""

    asset_root = TEACHER_EXAM_TEMPLATE_FILE.parent
    allow_graphics = asset_root.is_dir()
    documents: dict[str, str] = {}
    for name in ("main.tex", "answer.tex"):
        try:
            document = extract_named_tex_documents(raw, required_names=(name,))[0]
            source = stabilize_exam_tex_layout(document.source)
            validate_tex_document(source, allow_graphics=allow_graphics)
            documents[name] = source
        except ExamArtifactError:
            continue

    if not documents:
        notify("tex_validation_failed")
        return (
            "模型未生成可安全使用的 main.tex 与 answer.tex，本次原始文件内容已隐藏。请重新生成试卷。",
            [],
            "tex_validation_failed",
        )

    artifacts = [
        {
            "name": name,
            "mime": "application/x-tex",
            "data": documents[name].encode("utf-8"),
        }
        for name in ("main.tex", "answer.tex")
        if name in documents
    ]
    summary = exam_response_summary(raw)
    if set(documents) != {"main.tex", "answer.tex"}:
        notify("tex_validation_incomplete")
        missing = "、".join(name for name in ("main.tex", "answer.tex") if name not in documents)
        status = f"仅生成了部分安全 TeX 文件；缺少 {missing}，因此尚未编译 PDF。"
        response = f"{summary}\n\n{status}" if summary else status
        return normalize_latex(response), artifacts, "tex_incomplete"

    notify("tex_validation_complete")
    notify("pdf_compile_started")
    try:
        compiler_input = "\n".join(
            f"```latex {name}\n{documents[name]}```"
            for name in ("main.tex", "answer.tex")
        )
        bundles = build_exam_artifact_bundles(
            compiler_input,
            asset_root=asset_root if allow_graphics else None,
        )
    except ExamArtifactError:
        notify("pdf_compile_failed")
        status = (
            "TeX 文件已经生成，但 PDF 服务器端编译失败。"
            "可先下载 TeX；详细编译日志不会写入聊天正文。"
        )
        response = f"{summary}\n\n{status}" if summary else status
        return normalize_latex(response), artifacts, "pdf_compile_failed"

    notify("pdf_compile_complete")
    for bundle in bundles:
        artifacts.append({
            "name": bundle.pdf_name,
            "mime": bundle.pdf_mime,
            "data": bundle.pdf_bytes,
        })
    try:
        archive = build_exam_download_archive(
            bundles,
            asset_root=asset_root if allow_graphics else None,
        )
    except ExamArtifactError:
        # Individual validated TeX/PDF files remain usable even when an
        # optional all-in-one archive exceeds its separate safety limit.
        archive = None
    _append_exam_download_archive(artifacts, archive)
    status = (
        "试卷与参考答案已经生成并通过服务器端编译；所用外部图件已连同 TeX、PDF "
        "打包为 ZIP，请使用下方按钮下载。"
        if archive is not None
        else "试卷与参考答案已经生成并通过服务器端编译，请使用下方按钮下载 TeX 和 PDF 文件。"
    )
    response = f"{summary}\n\n{status}" if summary else status
    return normalize_latex(response), artifacts, ""


def render_history_visualizations(message: dict) -> None:
    visualizations = message.get("visualizations", [])
    if not visualizations:
        return
    stable_key = message_ui_key(message)
    state_key = f"_history_viz_open_{stable_key}"
    if not st.session_state.get(state_key):
        st.caption(f"此回答包含 {len(visualizations)} 个可视化演示，按需运行可加快历史加载。")
        if st.button(
            "▶ 运行此回答的可视化",
            key=f"open_history_viz_{stable_key}",
        ):
            st.session_state[state_key] = True
            st.rerun()
        return
    render_visualizations(visualizations, key_prefix=f"history_{stable_key}")
    if st.button("收起可视化", key=f"close_history_viz_{stable_key}"):
        st.session_state.pop(state_key, None)
        st.rerun()


def delete_history_turn(message_index: int, message: dict) -> None:
    if st.session_state.get("_answer_in_progress"):
        st.session_state._history_notice = "回答生成期间暂不能删除历史记录。"
        st.rerun()

    user_id = st.session_state.user_id
    deleted_messages: list[dict] = []
    deleted_count = 0
    if user_id is not None:
        message_id = message.get("id")
        if message_id is None:
            load_initial_history(user_id)
            st.session_state._history_notice = "历史记录已刷新，请再次选择要删除的条目。"
            st.rerun()
        try:
            if message.get("role") == "user":
                deleted_ids = (
                    {int(message_id)}
                    if delete_unanswered_question(
                        user_id, int(message_id), agent_mode=active_agent_mode()
                    )
                    else set()
                )
            else:
                deleted_ids = set(
                    delete_answer_turn(
                        user_id, int(message_id), agent_mode=active_agent_mode()
                    )
                )
        except Exception:
            st.session_state._history_notice = "删除历史记录失败，请稍后重试。"
            st.rerun()
        if not deleted_ids:
            load_initial_history(user_id)
            st.session_state._history_notice = "该条目已不存在或已经有回答，历史记录已刷新。"
            st.rerun()
        deleted_count = len(deleted_ids)
        deleted_messages = [
            item
            for item in st.session_state.messages
            if item.get("id") is not None and int(item["id"]) in deleted_ids
        ]
        st.session_state.messages = [
            item
            for item in st.session_state.messages
            if item.get("id") is None or int(item["id"]) not in deleted_ids
        ]
        if not st.session_state.messages and st.session_state._history_has_more:
            load_initial_history(user_id)
    elif 0 <= message_index < len(st.session_state.messages):
        first_index = message_index
        if (
            message.get("role") == "assistant"
            and message_index > 0
            and st.session_state.messages[message_index - 1].get("role") == "user"
        ):
            first_index -= 1
        deleted_messages = st.session_state.messages[first_index : message_index + 1]
        deleted_count = len(deleted_messages)
        del st.session_state.messages[first_index : message_index + 1]
    st.session_state.pop("_pending_delete_message", None)
    for deleted_message in deleted_messages:
        stable_key = message_ui_key(deleted_message)
        st.session_state.pop(f"_history_images_{stable_key}", None)
        st.session_state.pop(f"_history_viz_open_{stable_key}", None)
    if message.get("role") == "user" and deleted_count == 1:
        st.session_state._history_notice = "已删除未回答的问题。"
    elif deleted_count >= 2:
        st.session_state._history_notice = "已删除本轮问题和回答。"
    else:
        st.session_state._history_notice = "已删除回答；未找到可配对的问题。"
    st.rerun()


def question_has_answer(message_index: int, message: dict) -> bool:
    """Return whether a visible user message already has a paired answer."""
    if message.get("role") != "user":
        return False
    message_id = message.get("id")
    later_messages = st.session_state.messages[message_index + 1:]
    if message_id is not None:
        for candidate in later_messages:
            if (
                candidate.get("role") == "assistant"
                and candidate.get("parent_message_id") is not None
                and int(candidate["parent_message_id"]) == int(message_id)
            ):
                return True
    if later_messages and later_messages[0].get("role") == "assistant":
        return later_messages[0].get("parent_message_id") is None or message_id is None
    return False


def render_history_delete(message: dict, message_index: int) -> None:
    stable_key = message_ui_key(message)
    pending_key = st.session_state.get("_pending_delete_message")
    disabled = bool(st.session_state.get("_answer_in_progress"))
    unanswered_question = message.get("role") == "user"
    help_text = "删除这条未回答的问题" if unanswered_question else "删除本轮问题和回答"
    if pending_key != stable_key:
        if message.get("role") == "assistant":
            _, quote_col, delete_col = st.columns([6.25, 1.6, 1.35])
            if quote_col.button(
                "↩ 引用回答",
                key=f"quote_history_{stable_key}",
                help="下一条问题将明确引用这条回答，并优先使用其内容和 TeX 文件",
                use_container_width=True,
                disabled=disabled,
            ):
                select_history_reference(message)
                st.rerun()
        else:
            _, delete_col = st.columns([8, 1.35])
        if delete_col.button(
            "🗑 删除",
            key=f"delete_history_{stable_key}",
            help=help_text,
            use_container_width=True,
            disabled=disabled,
        ):
            st.session_state._pending_delete_message = stable_key
            st.rerun()
        return

    if unanswered_question:
        st.caption("确认删除这条未回答的问题？删除后无法恢复。")
    else:
        st.caption("确认删除本轮问题和回答？删除后无法恢复。")
    _, confirm_col, cancel_col = st.columns([6, 1.45, 1.2])
    if confirm_col.button(
        "确认删除",
        key=f"confirm_delete_history_{stable_key}",
        type="primary",
        use_container_width=True,
        disabled=disabled,
    ):
        delete_history_turn(message_index, message)
    if cancel_col.button(
        "取消",
        key=f"cancel_delete_history_{stable_key}",
        use_container_width=True,
    ):
        st.session_state.pop("_pending_delete_message", None)
        st.rerun()


def mark_answer_in_progress() -> None:
    st.session_state._answer_in_progress = True

restore_persistent_login()

if not st.session_state.access_granted:
    left_space, auth_column, right_space = st.columns([1, 1.35, 1])
    with auth_column:
        st.markdown(
            """
            <div class="auth-card">
              <h2>登录后开始学习</h2>
              <p>登录可永久保留对话历史；也可以匿名进入，无需注册。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        landing_login_tab, landing_register_tab = st.tabs(["登录", "注册"])
        with landing_login_tab:
            with st.form("landing_login_form"):
                landing_username = st.text_input(
                    "用户名或学号/工号", key="landing_login_username"
                )
                landing_password = st.text_input(
                    "密码", type="password", key="landing_login_password"
                )
                landing_login_submit = st.form_submit_button(
                    "登录", use_container_width=True
                )
            if landing_login_submit:
                user_id, canonical_username = authenticate(
                    landing_username, landing_password
                )
                if user_id is None:
                    st.error("用户名、学号/工号或密码错误。")
                else:
                    st.session_state.user_id = user_id
                    st.session_state.username = canonical_username
                    st.session_state.access_granted = True
                    redirect_browser(
                        user_session_target("login", canonical_username),
                        "登录成功，正在建立安全会话……",
                        "完成登录",
                    )
        with landing_register_tab:
            with st.form("landing_register_form"):
                landing_register_username = st.text_input(
                    "用户名", key="landing_register_username"
                )
                landing_register_password = st.text_input(
                    "密码（至少8位）", type="password", key="landing_register_password"
                )
                landing_register_confirm = st.text_input(
                    "确认密码", type="password", key="landing_register_confirm"
                )
                landing_register_submit = st.form_submit_button(
                    "注册并登录", use_container_width=True
                )
            if landing_register_submit:
                if landing_register_password != landing_register_confirm:
                    st.error("两次输入的密码不一致。")
                else:
                    user_id, register_message = create_user(
                        landing_register_username, landing_register_password
                    )
                    if user_id is None:
                        st.error(register_message)
                    else:
                        save_session_history(user_id)
                        load_initial_history(user_id)
                        st.session_state.user_id = user_id
                        st.session_state.username = landing_register_username.strip()
                        st.session_state.access_granted = True
                        redirect_browser(
                            user_session_target(
                                "login", landing_register_username.strip()
                            ),
                            "注册成功，正在建立安全会话……",
                            "完成登录",
                        )
        st.markdown("<div style='height:.35rem'></div>", unsafe_allow_html=True)
        if st.button("无需注册，匿名进入", key="anonymous_login", use_container_width=True):
            st.session_state.user_id = None
            st.session_state.username = "匿名用户"
            st.session_state.access_granted = True
            st.rerun()
        st.caption("匿名模式不会将历史记录保存到服务器，但仍可导出 Markdown。")
    st.stop()

account_state = refresh_account_state()
if not st.session_state.access_granted:
    st.rerun()
redirect_admin_after_login()
if is_verified_teacher(account_state):
    resolved_portal = resolve_teacher_portal(
        account_state,
        st.query_params.get("portal", ""),
        st.session_state.get("teacher_portal"),
    )
    if resolved_portal is None:
        st.session_state.pop("teacher_portal", None)
        st.session_state.messages = []
        reset_history_view()
        render_teacher_portal_picker()
        st.stop()
    st.session_state.teacher_portal = resolved_portal
else:
    st.session_state.pop("teacher_portal", None)
    if "portal" in st.query_params:
        del st.query_params["portal"]

agent_mode = active_agent_mode()
if (
    st.session_state.user_id is not None
    and (
        st.session_state._history_paged_user_id != st.session_state.user_id
        or st.session_state._history_paged_agent_mode != agent_mode
    )
):
    load_initial_history(st.session_state.user_id, agent_mode)
history_notice = st.session_state.pop("_history_notice", None)
if history_notice:
    st.toast(history_notice)
if st.session_state.get("analytics_session_user_id", object()) != st.session_state.user_id:
    reset_analytics_session()
    st.session_state._analytics_last_touch = time.monotonic()
elif time.monotonic() - st.session_state._analytics_last_touch >= 60:
    analytics_db.touch_session(st.session_state.get("analytics_session_id"))
    st.session_state._analytics_last_touch = time.monotonic()

quick_question = None
chapter = "全部"
try:
    top_k = int(setting("RAG_TOP_K", "6"))
except (TypeError, ValueError):
    top_k = 6
top_k = max(1, min(top_k, 12))

try:
    context_chars_limit = int(setting("KB_CONTEXT_MAX_CHARS", "2500"))
except (TypeError, ValueError):
    context_chars_limit = 2500
context_chars_limit = max(800, min(context_chars_limit, 12000))
try:
    history_message_limit = int(setting("PHYSICS_HISTORY_MAX_MESSAGES", "4"))
except (TypeError, ValueError):
    history_message_limit = 4
history_message_limit = max(2, min(history_message_limit, 200))
with st.sidebar:
    if agent_mode == PORTAL_TEACHING_EXAM:
        st.markdown(
            '<div class="teacher-agent-badge">📝 当前入口：教研考试</div>',
            unsafe_allow_html=True,
        )
        if st.button(
            "⇄ 切换教师工作入口",
            key="switch_teacher_portal_top",
            use_container_width=True,
        ):
            leave_teacher_portal()
            st.rerun()
    st.markdown(
        """
        <div class="sidebar-mode-title">
          <span class="sidebar-mode-icon">🎛️</span>
          <span class="sidebar-mode-label">模式</span>
          <span class="sidebar-mode-help" title="在课程问答与交互式物理实验之间切换">?</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    workspace_options = (
        ["教研考试"]
        if agent_mode == PORTAL_TEACHING_EXAM
        else ["智能助教", "可视化实验"]
    )
    previous_workspace_mode = st.session_state.get("_previous_workspace_mode")
    workspace_mode = st.radio(
        "学习模式",
        workspace_options,
        format_func=lambda value: (
            "💬  智能助教"
            if value == "智能助教"
            else ("📝  教研考试" if value == "教研考试" else "📊  可视化实验")
        ),
        key="workspace_mode",
        label_visibility="collapsed",
        width="stretch",
    ) or workspace_options[0]
    if (
        workspace_mode == "可视化实验"
        and previous_workspace_mode != "可视化实验"
    ):
        st.session_state.visual_experiment_category = "力学实验"
        st.session_state.visual_experiment_name = "杨氏模量"
    st.session_state._previous_workspace_mode = workspace_mode
    st.divider()

    if workspace_mode in {"智能助教", "教研考试"}:
        if workspace_mode == "教研考试":
            st.subheader("⚡ 快速教研任务")
            st.markdown(
                '<div class="sidebar-quick-note">可直接生成试题、组卷、答案或评分标准</div>',
                unsafe_allow_html=True,
            )
            visible_quick_questions = EXAM_QUICK_TASKS
        else:
            st.subheader("⚡ 快速提问")
            st.markdown('<div class="sidebar-quick-note">点击问题即可直接开始，也可随时换一组</div>', unsafe_allow_html=True)
            if st.button("↻ 换一换", key="sidebar_refresh_quick", use_container_width=True):
                st.session_state.quick_questions = new_quick_questions()
                st.rerun()
            visible_quick_questions = st.session_state.quick_questions
        for index, quick in enumerate(visible_quick_questions):
            if st.button(quick, key=f"sidebar_quick_{index}", use_container_width=True):
                st.session_state._answer_in_progress = True
                quick_question = quick
    else:
        st.subheader("🧪 实验导航")
        st.markdown(
            '<div class="sidebar-quick-note">选择一个实验，在主区域调节参数并观察结果</div>',
            unsafe_allow_html=True,
        )
        st.markdown("**力学实验**")
        if st.button("↕ 杨氏模量", key="sidebar_young_modulus", use_container_width=True):
            st.session_state.visual_experiment_name = "杨氏模量"
            st.session_state.visual_experiment_category = "力学实验"
            st.rerun()
        if st.button("↻ 转动惯量", key="sidebar_rotational_inertia", use_container_width=True):
            st.session_state.visual_experiment_name = "转动惯量"
            st.session_state.visual_experiment_category = "力学实验"
            st.rerun()
        if st.button("◉ 粘滞系数测定", key="sidebar_viscosity", use_container_width=True):
            st.session_state.visual_experiment_name = "粘滞系数测定"
            st.session_state.visual_experiment_category = "力学实验"
            st.rerun()

        st.markdown("**热学实验**")
        if st.button("♨ 固体比热容的测定", key="sidebar_specific_heat", use_container_width=True):
            st.session_state.visual_experiment_name = "固体比热容的测定"
            st.session_state.visual_experiment_category = "热学实验"
            st.rerun()
        if st.button("🌡 温度传感器特性的测定", key="sidebar_temperature_sensor", use_container_width=True):
            st.session_state.visual_experiment_name = "温度传感器特性的测定"
            st.session_state.visual_experiment_category = "热学实验"
            st.rerun()
        if st.button("▥ 固体热传导系数测定", key="sidebar_thermal_conductivity", use_container_width=True):
            st.session_state.visual_experiment_name = "固体热传导系数测定"
            st.session_state.visual_experiment_category = "热学实验"
            st.rerun()

        st.markdown("**振动波动**")
        if st.button("∿ 声速测量", key="sidebar_sound_speed", use_container_width=True):
            st.session_state.visual_experiment_name = "声速测量"
            st.session_state.visual_experiment_category = "振动波动"
            st.rerun()
        if st.button("〽 李萨如图形", key="sidebar_lissajous", use_container_width=True):
            st.session_state.visual_experiment_name = "李萨如图形"
            st.session_state.visual_experiment_category = "振动波动"
            st.rerun()

        st.markdown("**电磁实验**")
        if st.button("⊖ 电子荷质比", key="sidebar_electron_em", use_container_width=True):
            st.session_state.visual_experiment_name = "电子荷质比"
            st.session_state.visual_experiment_category = "电磁实验"
            st.rerun()
        if st.button("⏚ 惠斯通电桥测电阻", key="sidebar_wheatstone_bridge", use_container_width=True):
            st.session_state.visual_experiment_name = "惠斯通电桥测电阻"
            st.session_state.visual_experiment_category = "电磁实验"
            st.rerun()
        if st.button("⊞ 霍尔效应测磁场分布", key="sidebar_hall_effect", use_container_width=True):
            st.session_state.visual_experiment_name = "霍尔效应测磁场分布"
            st.session_state.visual_experiment_category = "电磁实验"
            st.rerun()
        if st.button("↯ 铁磁滞回线测定与观察", key="sidebar_magnetic_hysteresis", use_container_width=True):
            st.session_state.visual_experiment_name = "铁磁滞回线测定与观察"
            st.session_state.visual_experiment_category = "电磁实验"
            st.rerun()

        st.markdown("**光学实验**")
        if st.button("◎ 牛顿环", key="sidebar_newton_rings", use_container_width=True):
            st.session_state.visual_experiment_name = "牛顿环"
            st.session_state.visual_experiment_category = "光学实验"
            st.rerun()
        if st.button("◇ 双棱镜干涉测波长", key="sidebar_biprism", use_container_width=True):
            st.session_state.visual_experiment_name = "双棱镜干涉"
            st.session_state.visual_experiment_category = "光学实验"
            st.rerun()
        if st.button("◉ 薄透镜焦距的测定", key="sidebar_thin_lens_focal", use_container_width=True):
            st.session_state.visual_experiment_name = "薄透镜焦距的测定"
            st.session_state.visual_experiment_category = "光学实验"
            st.rerun()
        if st.button("△ 三棱镜折射率测定", key="sidebar_prism_refractive_index", use_container_width=True):
            st.session_state.visual_experiment_name = "三棱镜折射率测定"
            st.session_state.visual_experiment_category = "光学实验"
            st.rerun()

        st.markdown("**近代物理实验**")
        if st.button("☀ 光电效应", key="sidebar_photoelectric", use_container_width=True):
            st.session_state.visual_experiment_name = "光电效应"
            st.session_state.visual_experiment_category = "近代物理实验"
            st.rerun()
        if st.button("⚛ 弗兰克-赫兹", key="sidebar_franck_hertz", use_container_width=True):
            st.session_state.visual_experiment_name = "弗兰克-赫兹"
            st.session_state.visual_experiment_category = "近代物理实验"
            st.rerun()

    st.divider()
    with st.expander("👤 用户与历史", expanded=False):
        if st.session_state.user_id is None:
            st.caption("当前为匿名使用，无需登录；记录仅保留在本次会话中。")
            login_tab, register_tab = st.tabs(["登录", "注册"])
            with login_tab:
                with st.form("login_form"):
                    login_username = st.text_input(
                        "用户名或学号/工号", key="login_username"
                    )
                    login_password = st.text_input("密码", type="password", key="login_password")
                    login_submit = st.form_submit_button("登录", use_container_width=True)
                if login_submit:
                    user_id, canonical_username = authenticate(login_username, login_password)
                    if user_id is None:
                        st.error("用户名、学号/工号或密码错误。")
                    else:
                        st.session_state.user_id = user_id
                        st.session_state.username = canonical_username
                        load_initial_history(user_id)
                        redirect_browser(
                            user_session_target("login", canonical_username),
                            "登录成功，正在建立安全会话……",
                            "完成登录",
                        )
            with register_tab:
                with st.form("register_form"):
                    register_username = st.text_input("用户名", key="register_username")
                    register_password = st.text_input("密码（至少8位）", type="password", key="register_password")
                    register_confirm = st.text_input("确认密码", type="password", key="register_confirm")
                    register_submit = st.form_submit_button("注册并登录", use_container_width=True)
                if register_submit:
                    if register_password != register_confirm:
                        st.error("两次输入的密码不一致。")
                    else:
                        user_id, register_message = create_user(register_username, register_password)
                        if user_id is None:
                            st.error(register_message)
                        else:
                            # Keep the conversation that was started anonymously.
                            save_session_history(user_id)
                            load_initial_history(user_id)
                            st.session_state.user_id = user_id
                            st.session_state.username = register_username.strip()
                            redirect_browser(
                                user_session_target(
                                    "login", register_username.strip()
                                ),
                                "注册成功，正在建立安全会话……",
                                "完成登录",
                            )
            if st.button("返回登录入口", key="leave_anonymous", use_container_width=True):
                st.session_state.access_granted = False
                st.rerun()
        else:
            st.success(f"已登录：{st.session_state.username}")
            account = analytics_db.get_user_by_id(st.session_state.user_id) or {}
            if (
                is_verified_teacher(account)
                and agent_mode == PORTAL_ASSISTANT
                and st.button(
                    "⇄ 切换教师工作入口",
                    key="switch_teacher_portal_account",
                    use_container_width=True,
                )
            ):
                leave_teacher_portal()
                st.rerun()
            if st.session_state.user_role == "admin":
                st.link_button(
                    "📊 打开管理员后台",
                    admin_login_target(),
                    use_container_width=True,
                )
            elif not account.get("identity_verified"):
                with st.expander("绑定学生/教师身份", expanded=False):
                    identity_label = st.selectbox(
                        "身份", ["学生", "教师"], key="identity_type"
                    )
                    institutional_id = st.text_input(
                        "学号或工号", key="institutional_id"
                    )
                    real_name = st.text_input("姓名", key="identity_real_name")
                    if st.button("核验并绑定", key="bind_identity", use_container_width=True):
                        try:
                            verified = analytics_db.bind_user_identity(
                                st.session_state.user_id,
                                "student" if identity_label == "学生" else "teacher",
                                institutional_id,
                                real_name,
                            )
                            st.session_state.user_role = verified.get("role", "student")
                            st.success("身份绑定成功。")
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))
            if st.button("退出登录", key="logout", use_container_width=True):
                logout_target = user_session_target(
                    "logout", str(st.session_state.username)
                )
                analytics_db.end_session(
                    st.session_state.get("analytics_session_id", ""),
                    st.session_state.get("analytics_total_questions", 0),
                    st.session_state.get("analytics_total_errors", 0),
                    st.session_state.get("analytics_tokens_input", 0),
                    st.session_state.get("analytics_tokens_output", 0),
                )
                st.session_state.pop("analytics_session_id", None)
                st.session_state.pop("analytics_session_user_id", None)
                st.session_state.user_id = None
                st.session_state.username = "匿名用户"
                st.session_state.user_role = "anonymous"
                st.session_state.messages = []
                reset_history_view()
                st.session_state.access_granted = False
                st.session_state.pop("workspace_mode", None)
                st.session_state.pop("teacher_portal", None)
                if "portal" in st.query_params:
                    del st.query_params["portal"]
                st.session_state.pop("_pending_delete_message", None)
                st.session_state._answer_in_progress = False
                redirect_browser(
                    logout_target,
                    "正在安全退出并清除浏览器登录状态……",
                    "返回登录页面",
                )

        if st.session_state.messages or (
            st.session_state.user_id is not None and st.session_state._history_has_more
        ):
            if st.session_state.user_id is None:
                markdown_data = messages_to_markdown(
                    st.session_state.messages, st.session_state.username
                ).encode("utf-8-sig")
            else:
                export_user_id = int(st.session_state.user_id)
                export_username = str(st.session_state.username)
                markdown_data = lambda uid=export_user_id, username=export_username: (
                    messages_to_markdown(
                        load_messages(
                            uid,
                            include_image_data=False,
                            agent_mode=active_agent_mode(),
                        ),
                        username,
                    ).encode("utf-8-sig")
                )
            st.download_button(
                "⬇ 导出完整 Markdown",
                data=markdown_data,
                file_name="大学物理智能助教_对话记录.md",
                mime="text/markdown; charset=utf-8",
                use_container_width=True,
                on_click="ignore",
                help="点击下载时才读取完整历史，避免拖慢日常页面加载",
            )
            confirm_clear = st.checkbox("确认清空全部对话记录", key="confirm_clear_history")
            if st.button(
                "清空记录", key="clear_history", use_container_width=True,
                disabled=not confirm_clear,
            ):
                if st.session_state.user_id is not None:
                    clear_messages(
                        st.session_state.user_id, agent_mode=active_agent_mode()
                    )
                st.session_state.messages = []
                reset_history_view()
                st.rerun()

        with st.expander("💬 意见反馈", expanded=False):
            with st.form("general_feedback_form", clear_on_submit=True):
                feedback_type = st.selectbox("类型", ["建议", "问题", "内容纠错"])
                feedback_text = st.text_area("反馈内容", max_chars=2000)
                feedback_submit = st.form_submit_button("提交", use_container_width=True)
            if feedback_submit:
                if feedback_text.strip():
                    analytics_db.log_feedback(
                        None,
                        st.session_state.get("analytics_session_id", ""),
                        "opinion",
                        f"[{feedback_type}] {feedback_text.strip()}",
                        st.session_state.user_id,
                    )
                    st.success("反馈已提交。")
                else:
                    st.warning("请先填写反馈内容。")

if workspace_mode == "可视化实验":
    render_experiment_hub()
    st.stop()

if not KB_FILE.exists():
    with st.spinner("首次运行：正在生成本地知识库……"):
        build()
kb = load_kb(KB_FILE.stat().st_mtime)
teacher_exam_kb = None
if agent_mode == PORTAL_TEACHING_EXAM and TEACHER_EXAM_KB_FILE.is_file():
    teacher_exam_kb = load_private_teacher_exam_kb(
        TEACHER_EXAM_KB_FILE.stat().st_mtime
    )

if st.session_state.user_id is not None and st.session_state._history_has_more:
    st.caption("为提升加载速度，默认显示最近 8 条消息；更早记录可按需加载。")
    if st.button(
        "↑ 加载更早记录",
        key="load_earlier_history",
        disabled=bool(st.session_state.get("_answer_in_progress")),
    ):
        load_earlier_history()
        st.rerun()

for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        render_quoted_reference(message)
        render_history_images(message)
        st.markdown(normalize_latex(message["content"]))
        if message["role"] == "assistant" and agent_mode == PORTAL_TEACHING_EXAM:
            render_message_artifacts(message)
        render_history_visualizations(message)
        if message["role"] == "assistant" or not question_has_answer(message_index, message):
            render_history_delete(message, message_index)

if not st.session_state.messages and agent_mode == PORTAL_TEACHING_EXAM:
    st.markdown("""
    <div class="welcome">
      <div class="welcome-line"><span class="bot-icon">📝</span><span>你好！我是面向教师的<b>大学物理教研考试智能体</b>。</span></div>
      <ul>
        <li><b>依据知识库命题：</b>复用现有教材、课程资料和实验知识库</li>
        <li><b>教研与组卷：</b>可按章节、题型、难度、题量、时长和总分组织试卷</li>
        <li><b>答案与评价：</b>可分别生成参考答案、解析、评分细则及知识点分布</li>
      </ul>
      <div class="tip">💡 后续加入教师专用题库、历年试卷或命题规范后，会在基础知识库之上自动参与教师端检索。</div>
    </div>
    """, unsafe_allow_html=True)
elif not st.session_state.messages:
    st.markdown("""
    <div class="welcome">
      <div class="welcome-line"><span class="bot-icon">🤖</span><span>你好！我是你的<b>大学物理智能助教</b>，可以陪你理解概念、推导公式和分析习题。</span></div>
      <ul>
        <li><b>知识增强：</b>以祝之光教材和本地课程资料为核心，结合网络内容补充回答</li>
        <li><b>分步讲解：</b>给出思路、公式条件、计算过程与易错点</li>
        <li><b>可视化辅助：</b>根据问题生成绘图代码，并在回答后直接运行演示</li>
      </ul>
      <div class="course-map"><b>力学与热学：</b>运动、动力学、刚体、振动与波、气体动理论、热力学</div>
      <div class="course-map"><b>电磁与近代物理：</b>静电场、磁场、电磁感应、波动光学、量子物理</div>
      <div class="tip">💡 支持LaTeX公式、图片识题、Paraformer流式语音输入和交互式物理图表。</div>
    </div>
    """, unsafe_allow_html=True)

selected_quote = st.session_state.get("_quoted_message")
if isinstance(selected_quote, dict):
    quote_col, cancel_quote_col = st.columns([8, 1.15])
    with quote_col:
        st.caption(
            "↪ 下一条消息将引用此回答："
            + reference_preview(selected_quote.get("preview") or selected_quote.get("content"))
        )
    if cancel_quote_col.button(
        "取消引用",
        key="cancel_history_reference",
        use_container_width=True,
        disabled=bool(st.session_state.get("_answer_in_progress")),
    ):
        st.session_state.pop("_quoted_message", None)
        st.rerun()

voice_commit = render_voice_input(
    disabled=bool(st.session_state.get("_answer_in_progress")),
)
if voice_commit:
    commit_id = str(voice_commit.get("id") or "")
    commit_text = str(voice_commit.get("text") or "").strip()
    if commit_id and commit_text and commit_id != st.session_state._voice_commit_id:
        st.session_state._voice_commit_id = commit_id
        st.session_state["physics_chat_input"] = commit_text
        # Recreate the fixed bottom chat input after the component event so
        # mobile browsers receive the draft value reliably.
        st.rerun()
typed_input = st.chat_input(
    (
        "输入命题或教研任务，也可上传试题、试卷图片或 PDF……"
        if agent_mode == PORTAL_TEACHING_EXAM
        else "输入问题，或将题目图片直接粘贴到这里……"
    ),
    key="physics_chat_input",
    accept_file="multiple",
    file_type=["png", "jpg", "jpeg", "webp", "pdf"],
    max_upload_size=20,
    submit_mode="disable",
    on_submit=mark_answer_in_progress,
)
uploaded_images = []
typed_question = ""
if typed_input:
    typed_question = typed_input.text.strip()
    for uploaded in typed_input.files:
        uploaded_images.append({
            "data": uploaded.getvalue(),
            "mime": uploaded.type or "image/png",
            "name": uploaded.name,
        })
if uploaded_images and not typed_question:
    typed_question = (
        "请读取上传附件中的试题、答案或教学资料，并依据知识库进行审题、改题或命题分析。"
        if agent_mode == PORTAL_TEACHING_EXAM
        else "请读取上传附件中的大学物理题目或物理信息，并给出完整、清晰的分析与解答。"
    )
question = quick_question or typed_question
if question:
    request_started = time.monotonic()
    request_timing: dict[str, float] = {}
    request_error = None
    request_traceback = ""
    message_images = [] if quick_question else uploaded_images
    teacher_exam_request_kind = (
        classify_teacher_exam_request(
            question,
            st.session_state.messages,
            has_attachments=bool(message_images),
        )
        if agent_mode == PORTAL_TEACHING_EXAM
        else ""
    )
    is_full_exam_generation = (
        teacher_exam_request_kind == EXAM_REQUEST_FULL_GENERATION
    )
    uses_dedicated_exam_model = agent_mode == PORTAL_TEACHING_EXAM
    artifact_file_requested = (
        agent_mode == PORTAL_TEACHING_EXAM
        and teacher_exam_request_kind == EXAM_REQUEST_SOURCE_MATERIAL
        and source_material_artifact_requested(question)
    )
    artifact_revision_requested = (
        artifact_file_requested
        and source_material_artifact_revision_requested(question)
    )
    artifact_delivery_requested = (
        artifact_file_requested and not artifact_revision_requested
    )
    quoted_reference = resolve_selected_reference(
        include_artifacts=agent_mode == PORTAL_TEACHING_EXAM
    )
    if artifact_file_requested and quoted_reference is None:
        quoted_reference = latest_assistant_reference(include_artifacts=True)
    st.session_state.pop("_quoted_message", None)
    source_answer_artifacts_requested = (
        agent_mode == PORTAL_TEACHING_EXAM
        and teacher_exam_request_kind == EXAM_REQUEST_SOURCE_MATERIAL
        and (
            source_material_answer_requested(question)
            or artifact_revision_requested
        )
    )
    user_message = {
        "role": "user",
        "content": question,
        "images": message_images,
        "quoted_message_id": (
            quoted_reference.get("id") if quoted_reference is not None else None
        ),
        "_quoted_preview": (
            reference_preview(quoted_reference.get("content"))
            if quoted_reference is not None
            else ""
        ),
        "_quoted_session_key": (
            quoted_reference.get("session_key")
            if quoted_reference is not None
            else None
        ),
    }
    st.session_state.messages.append(user_message)
    if st.session_state.user_id is not None:
        user_message["id"] = save_message(
            st.session_state.user_id, user_message, agent_mode=agent_mode
        )
    with st.chat_message("user"):
        render_quoted_reference(user_message)
        render_history_images(user_message)
        st.markdown(question)
    exam_metadata_prompt = (
        exam_generation_metadata_prompt(question, st.session_state.messages[:-1])
        if is_full_exam_generation
        else ""
    )
    if exam_metadata_prompt:
        with st.chat_message("assistant"):
            st.markdown(exam_metadata_prompt)
        elapsed = time.monotonic() - request_started
        interaction_id = analytics_db.log_interaction(
            st.session_state.get("analytics_session_id", ""),
            question,
            exam_metadata_prompt,
            "教研考试元数据核验",
            "metadata-preflight",
            "rule-based",
            max(1, len(question) // 4),
            max(1, len(exam_metadata_prompt) // 4),
            int(elapsed * 1000),
            None,
            [],
            st.session_state.user_id,
            request_timing={"端到端耗时": elapsed},
            agent_mode=agent_mode,
        )
        assistant_message = {
            "role": "assistant",
            "content": exam_metadata_prompt,
            "visualizations": [],
            "artifacts": [],
            "interaction_id": interaction_id,
            "parent_message_id": user_message.get("id"),
        }
        st.session_state.messages.append(assistant_message)
        if st.session_state.user_id is not None:
            assistant_message["id"] = save_message(
                st.session_state.user_id,
                assistant_message,
                agent_mode=agent_mode,
            )
        st.session_state.analytics_total_questions += 1
        st.session_state.analytics_tokens_input += max(1, len(question) // 4)
        st.session_state.analytics_tokens_output += max(1, len(exam_metadata_prompt) // 4)
        st.session_state._answer_in_progress = False
        st.rerun()

    if artifact_delivery_requested:
        artifacts = []
        compile_error = None
        compile_traceback = ""
        compile_started = time.monotonic()
        if quoted_reference is None:
            response = (
                "没有找到可编译的历史回答。请先点击目标回答下方的“引用回答”，"
                "再发送“编译成 PDF”。"
            )
        else:
            try:
                artifacts = reusable_reference_artifacts(quoted_reference)
                if artifacts:
                    response = "已加载引用回答中现有的 TeX 与 PDF 文件，请使用下方按钮下载。"
                else:
                    compilation_input = reference_compilation_input(quoted_reference)
                    if not compilation_input.strip():
                        raise ValueError("引用回答不包含可编译内容。")
                    with st.spinner("正在校验并编译引用回答中的 TeX……"):
                        answer_bundle = build_answer_artifact_bundle(
                            compilation_input,
                            title="大学物理参考答案",
                        )
                    artifacts = [
                        {
                            "name": answer_bundle.tex_name,
                            "mime": answer_bundle.tex_mime,
                            "data": answer_bundle.tex_bytes,
                        },
                        {
                            "name": answer_bundle.pdf_name,
                            "mime": answer_bundle.pdf_mime,
                            "data": answer_bundle.pdf_bytes,
                        },
                    ]
                    response = "已根据引用的历史回答完成安全校验，并生成 TeX 与 PDF 文件。"
            except Exception as artifact_exc:
                compile_error = str(artifact_exc)
                compile_traceback = traceback.format_exc()
                compiler_log = str(getattr(artifact_exc, "log", "") or "")
                if compiler_log:
                    compile_traceback += "\n\n[TeX compiler log]\n" + compiler_log[-12_000:]
                response = (
                    "已找到引用回答，但其中的 TeX 未能通过安全校验或服务器编译。"
                    "错误详情已写入系统日志，请检查后重试。"
                )
        request_timing["历史引用解析与文件编译耗时"] = (
            time.monotonic() - compile_started
        )
        request_timing["端到端耗时"] = time.monotonic() - request_started
        with st.chat_message("assistant"):
            st.markdown(response)
            render_message_artifacts({
                "role": "assistant",
                "content": response,
                "artifacts": artifacts,
                "_ui_id": f"referenced_artifacts_{uuid.uuid4().hex}",
            })
        interaction_id = analytics_db.log_interaction(
            st.session_state.get("analytics_session_id", ""),
            question,
            response,
            "历史回答文件交付",
            "server-side",
            "Tectonic",
            max(1, len(question) // 4),
            max(1, len(response) // 4),
            int((time.monotonic() - request_started) * 1000),
            compile_error,
            [],
            st.session_state.user_id,
            request_timing=request_timing,
            agent_mode=agent_mode,
        )
        if compile_error:
            analytics_db.log_error(
                st.session_state.get("analytics_session_id", ""),
                question,
                "tex_compile",
                compile_error,
                compile_traceback,
                st.session_state.user_id,
            )
            st.session_state.analytics_total_errors += 1
        assistant_message = {
            "role": "assistant",
            "content": response,
            "visualizations": [],
            "artifacts": artifacts,
            "interaction_id": interaction_id,
            "parent_message_id": user_message.get("id"),
        }
        st.session_state.messages.append(assistant_message)
        if st.session_state.user_id is not None:
            assistant_message["id"] = save_message(
                st.session_state.user_id,
                assistant_message,
                agent_mode=agent_mode,
            )
        st.session_state.analytics_total_questions += 1
        st.session_state.analytics_tokens_input += max(1, len(question) // 4)
        st.session_state.analytics_tokens_output += max(1, len(response) // 4)
        st.session_state._answer_in_progress = False
        st.rerun()

    model_images = raster_image_attachments(message_images)
    uploaded_document_bundle = None
    if any(pdf_attachment_data(item) for item in message_images):
        document_started = time.monotonic()
        with st.spinner("正在读取上传的 PDF 试卷或资料……"):
            uploaded_document_bundle = prepare_uploaded_documents(message_images)
        request_timing["上传PDF处理耗时"] = time.monotonic() - document_started
        model_images.extend(uploaded_document_bundle.vision_images)
        for warning in uploaded_document_bundle.warnings:
            st.info(f"附件处理提示：{warning}")

    exam_assistant_container = None
    exam_progress_status = None
    if is_full_exam_generation:
        # Create the assistant row before any blocking work so teachers see the
        # real pipeline from retrieval through PDF compilation.
        exam_assistant_container = st.chat_message("assistant")
        exam_progress_status = exam_assistant_container.status(
            "步骤 1/5：正在检索知识库与教师命题资料",
            expanded=True,
        )
        exam_progress_status.write(
            "优先查找教师专用试卷、命题规范与标准模板，再补充公共教材知识。"
        )
    search_started = time.monotonic()
    if agent_mode == PORTAL_TEACHING_EXAM:
        scoped_exam_task = exam_retrieval_task(
            question, st.session_state.messages[:-1]
        )
        retrieval_query = exam_retrieval_query(scoped_exam_task, chapter=chapter)
        private_results = (
            teacher_exam_kb.search(
                retrieval_query,
                chapter="全部",
                top_k=max(6, min(top_k, 8)),
            )
            if teacher_exam_kb is not None
            else []
        )
        public_results = kb.search(
            retrieval_query,
            chapter=chapter,
            top_k=min(4, max(2, top_k // 2)),
        )
        results = merge_exam_retrieval_results(
            private_results, public_results, maximum=10
        )
    else:
        retrieval_query = question
        results = kb.search(retrieval_query, chapter=chapter, top_k=top_k)
    request_timing["检索耗时"] = time.monotonic() - search_started
    if exam_progress_status is not None:
        exam_progress_status.write(
            f"✅ 步骤 1/5 完成（{request_timing['检索耗时']:.1f} 秒）："
            f"已合并去重 {len(results)} 段教师专用/公共知识库依据。"
        )
        exam_progress_status.update(
            label="步骤 2/5：正在按需联网补充并整理命题依据",
            state="running",
            expanded=True,
        )
    context_started = time.monotonic()
    exam_context_limit = max(context_chars_limit, 8000)
    context = context_text(
        results,
        max_chars=(
            exam_context_limit
            if agent_mode == PORTAL_TEACHING_EXAM
            else context_chars_limit
        ),
    )
    if agent_mode == PORTAL_TEACHING_EXAM:
        context = MANDATORY_EXAM_POLICY_CONTEXT + (f"\n\n{context}" if context else "")
    if uploaded_document_bundle is not None:
        document_context = uploaded_document_bundle.context
        if uploaded_document_bundle.warnings:
            warning_context = "\n".join(
                f"- {item}" for item in uploaded_document_bundle.warnings
            )
            document_context = (
                document_context
                + ("\n\n" if document_context else "")
                + "[上传附件处理提示]\n"
                + warning_context
            )
        if document_context:
            context = context + ("\n\n" if context else "") + document_context
    quoted_context = reference_model_context(quoted_reference)
    if quoted_context:
        context = context + ("\n\n" if context else "") + quoted_context
    request_timing["上下文拼装耗时"] = time.monotonic() - context_started
    web_results = []
    web_context = ""
    web_query = scoped_exam_task if agent_mode == PORTAL_TEACHING_EXAM else question
    web_search_required = should_search_web(web_query)
    if web_search_required:
        web_search_started = time.monotonic()
        if exam_progress_status is not None:
            web_results = search_web(web_query)
        else:
            with st.spinner("正在联网检索补充资料……"):
                web_results = search_web(web_query)
        request_timing["联网检索耗时"] = time.monotonic() - web_search_started
        web_context = web_context_text(web_results)
        if exam_progress_status is not None:
            result_note = (
                f"已取得 {len(web_results)} 条网络参考"
                if web_results
                else "未取得可用网络结果，已自动回退到本地知识库"
            )
            exam_progress_status.write(
                f"✅ 步骤 2/5 完成（{request_timing['联网检索耗时']:.1f} 秒）："
                f"{result_note}。"
            )
    elif exam_progress_status is not None:
        request_timing["联网检索耗时"] = 0.0
        exam_progress_status.write(
            "⏭️ 步骤 2/5 完成（0.0 秒）：当前要求不需联网，未向外部搜索服务发送请求。"
        )
    if st.session_state.user_id is not None and user_message.get("id") is not None:
        history_started = time.monotonic()
        history = load_context_messages(
            st.session_state.user_id,
            before_id=int(user_message["id"]),
            limit=history_message_limit,
            agent_mode=agent_mode,
            include_artifacts=(
                agent_mode == PORTAL_TEACHING_EXAM
                and quoted_reference is None
            ),
        )
        request_timing["历史加载耗时"] = time.monotonic() - history_started
    else:
        request_timing["历史加载耗时"] = 0.0
        history = [
            {"role": message["role"], "content": message["content"]}
            for message in st.session_state.messages[:-1]
        ]
    if exam_progress_status is not None:
        exam_progress_status.update(
            label="步骤 3/5：正在生成结构化试题、参考答案与评分标准",
            state="running",
            expanded=True,
        )
        exam_progress_status.write(
            "模型只生成一次结构化题目与答案，TeX/PDF 将由服务器固定模板生成。"
            "开始阶段需要处理命题资料，随后会持续显示接收进度，请勿刷新页面。"
        )
    assistant_container = (
        exam_assistant_container
        if exam_assistant_container is not None
        else st.chat_message("assistant")
    )
    with assistant_container:
        thinking = st.empty()
        if not is_full_exam_generation:
            thinking.markdown("""
            <div class="thinking-state"><span class="thinking-orb"></span>
            <span>正在组织答案<span class="thinking-dots"><span>·</span><span>·</span><span>·</span></span></span></div>
            """, unsafe_allow_html=True)
        components.html("""
        <script>
        (() => {
          try {
            const doc = window.parent.document;
            const scroller = doc.querySelector('[data-testid="stAppScrollToBottomContainer"]')
              || doc.querySelector('section.stMain')
              || doc.scrollingElement;
            let following = true;
            let lastTop = scroller.scrollTop || 0;
            const onScroll = () => {
              const now = scroller.scrollTop || 0;
              const remaining = scroller.scrollHeight - now - scroller.clientHeight;
              if (now < lastTop - 10) following = false;
              if (remaining < 140) following = true;
              lastTop = now;
            };
            scroller.addEventListener('scroll', onScroll, {passive:true});
            let followTimer = null;
            const follow = () => {
              followTimer = null;
              if (!following) return;
              scroller.scrollTop = scroller.scrollHeight;
            };
            const scheduleFollow = () => {
              if (followTimer !== null) return;
              followTimer = setTimeout(follow, 160);
            };
            const observer = new MutationObserver(scheduleFollow);
            observer.observe(doc.body, {subtree:true, childList:true, characterData:true});
            scheduleFollow();
            const cleanup = () => {
              observer.disconnect();
              scroller.removeEventListener('scroll', onScroll);
              if (followTimer !== null) clearTimeout(followTimer);
            };
            window.addEventListener('beforeunload', cleanup, {once:true});
            setTimeout(cleanup, 180000);
          } catch (_) {}
        })();
        </script>
        """, height=0)
        streamed_parts = []
        answer_placeholder = st.empty()
        visualizations = []
        artifacts = []
        artifact_status = ""
        model_start = time.monotonic()
        exam_artifact_stage_started = {"value": model_start}
        exam_model_progress_rendered_at = {"value": 0.0}

        def update_exam_model_progress(reasoning_chars: int, output_chars: int) -> None:
            if exam_progress_status is None:
                return
            now = time.monotonic()
            if now - exam_model_progress_rendered_at["value"] < 1.8:
                return
            exam_model_progress_rendered_at["value"] = now
            elapsed = now - model_start
            details = []
            if reasoning_chars:
                details.append(f"内部推理约 {reasoning_chars} 字符")
            if output_chars:
                details.append(f"已接收结构化内容约 {output_chars} 字符")
                if elapsed > 0:
                    details.append(f"平均 {output_chars / elapsed:.1f} 字符/秒")
            progress_note = "，".join(details) if details else "模型正在处理命题上下文"
            exam_progress_status.update(
                label=(
                    "步骤 3/5：正在生成结构化试题、参考答案与评分标准"
                    f"（{elapsed:.0f} 秒，{progress_note}）"
                ),
                state="running",
                expanded=True,
            )

        def update_exam_generation_event(
            event: str,
            details: dict | None = None,
        ) -> None:
            if exam_progress_status is None:
                return
            payload = details if isinstance(details, dict) else {}

            def normalize_question_numbers(value) -> list[str]:
                if value is None:
                    values = ()
                elif isinstance(value, (str, int)):
                    values = (value,)
                elif isinstance(value, (list, tuple, set)):
                    values = value
                else:
                    values = (value,)
                normalized: list[str] = []
                for number in values:
                    text = str(number).strip()
                    if text and text not in normalized:
                        normalized.append(text)
                return normalized

            question_numbers = normalize_question_numbers(
                payload.get("question_numbers", payload.get("questions", ()))
            )
            choice_question_numbers = normalize_question_numbers(
                payload.get("choice_question_numbers", ())
            )
            fill_question_numbers = normalize_question_numbers(
                payload.get("fill_question_numbers", ())
            )
            if not question_numbers:
                question_numbers = list(choice_question_numbers)
                question_numbers.extend(
                    number
                    for number in fill_question_numbers
                    if number not in question_numbers
                )
            question_label = (
                f"第 {'、'.join(question_numbers)} 题"
                if question_numbers
                else "已列出的题目"
            )
            choice_question_label = (
                question_label if question_numbers else "存在冲突选项的题目"
            )
            repair_fields: list[str] = []
            if choice_question_numbers:
                repair_fields.append(
                    f"第 {'、'.join(choice_question_numbers)} 题的重复选项"
                )
            if fill_question_numbers:
                repair_fields.append(
                    f"第 {'、'.join(fill_question_numbers)} 题的填空标记"
                )
            repair_field_label = "；".join(repair_fields) or f"{question_label}的结构字段"

            if event == "targeted_exam_repair_started":
                exam_progress_status.update(
                    label=f"步骤 3/5：正在局部修复{question_label}的结构字段",
                    state="running",
                    expanded=True,
                )
                exam_progress_status.write(
                    f"🔧 正在局部修复：{repair_field_label}。"
                    "仅修复以上列出的结构字段（重复选项 / 填空标记）；"
                    "其他题目、答案和评分标准均不重新生成，修复后将重新校验完整试卷。"
                )
            elif event == "targeted_exam_repair_completed":
                exam_progress_status.write(
                    f"✅ 已完成{repair_field_label}的局部修复；"
                    "其他题目、答案和评分标准均未重新生成，"
                    "正在重新校验完整试卷。"
                )
                exam_progress_status.update(
                    label="步骤 3/5：局部修复完成，正在校验完整试卷结构",
                    state="running",
                    expanded=True,
                )
            elif event == "targeted_exam_repair_failed":
                exam_progress_status.write(
                    f"⚠️ {repair_field_label}的局部修复未通过校验；"
                    "其他题目、答案和评分标准均未重新生成。"
                )
                exam_progress_status.update(
                    label="步骤 3/5：局部结构修复失败",
                    state="error",
                    expanded=True,
                )
            elif event == "choice_option_repair_started":
                exam_progress_status.update(
                    label=f"步骤 3/5：正在局部修复{choice_question_label}的重复选项",
                    state="running",
                    expanded=True,
                )
                exam_progress_status.write(
                    f"🔧 检测到{choice_question_label}存在重复选项；"
                    "仅局部修复冲突选项，其余试题不会重新生成。"
                )
            elif event == "choice_option_repair_completed":
                exam_progress_status.write(
                    f"✅ 已完成{choice_question_label}冲突选项的局部修复；"
                    "其余试题未重新生成，正在重新校验整卷。"
                )
                exam_progress_status.update(
                    label="步骤 3/5：局部修复完成，正在校验完整试卷结构",
                    state="running",
                    expanded=True,
                )
            elif event == "choice_option_repair_failed":
                exam_progress_status.write(
                    f"⚠️ {choice_question_label}的重复选项局部修复未通过校验；"
                    "其余试题未重新生成。"
                )
                exam_progress_status.update(
                    label="步骤 3/5：重复选项局部修复失败",
                    state="error",
                    expanded=True,
                )

        def update_exam_artifact_progress(event: str) -> None:
            if exam_progress_status is None:
                return
            now = time.monotonic()
            if event == "tex_validation_started":
                elapsed = now - model_start
                request_timing["模型流式总耗时"] = elapsed
                exam_progress_status.write(
                    f"✅ 步骤 3/5 完成（{elapsed:.1f} 秒）："
                    "已收到完整的结构化试题、答案与评分标准。"
                )
                exam_progress_status.update(
                    label="步骤 4/5：正在校验结构、分值并套用固定 TeX 模板",
                    state="running",
                    expanded=True,
                )
                exam_artifact_stage_started["value"] = now
            elif event == "tex_validation_complete":
                elapsed = now - exam_artifact_stage_started["value"]
                request_timing["TeX校验耗时"] = elapsed
                exam_progress_status.write(
                    f"✅ 步骤 4/5 完成（{elapsed:.1f} 秒）："
                    "结构、题型分值及固定模板 TeX 安全检查已通过。"
                )
            elif event == "pdf_compile_started":
                exam_progress_status.update(
                    label="步骤 5/5：正在编译试卷与参考答案 PDF",
                    state="running",
                    expanded=True,
                )
                exam_artifact_stage_started["value"] = now
            elif event == "pdf_compile_complete":
                elapsed = now - exam_artifact_stage_started["value"]
                request_timing["PDF编译耗时"] = elapsed
                exam_progress_status.write(
                    f"✅ 步骤 5/5 完成（{elapsed:.1f} 秒）："
                    "试卷与参考答案 PDF 已生成。"
                )

        def tracked_stream():
            nonlocal_first = {"value": True}
            generation_lock = None
            generation_lock_acquired = False
            queue_started = time.monotonic()
            try:
                if uses_dedicated_exam_model:
                    generation_lock = exam_generation_lock()
                    queue_notice_written = False
                    while not generation_lock.acquire(timeout=1.0):
                        waited = time.monotonic() - queue_started
                        if is_full_exam_generation and exam_progress_status is not None:
                            exam_progress_status.update(
                                label=(
                                    "步骤 3/5：正在等待专用命题模型空闲"
                                    f"（已等待 {waited:.0f} 秒）"
                                ),
                                state="running",
                                expanded=True,
                            )
                            if not queue_notice_written:
                                exam_progress_status.write(
                                    "专用 DeepSeek 当前一次处理一份试卷；"
                                    "前一份完成后本任务会自动开始，无需重复提交。"
                                )
                                queue_notice_written = True
                        elif not is_full_exam_generation:
                            thinking.markdown(
                                """
                                <div class="thinking-state"><span class="thinking-orb"></span>
                                <span>正在等待教研模型空闲（已等待 """
                                + f"{waited:.0f}"
                                + """ 秒）<span class="thinking-dots"><span>·</span><span>·</span><span>·</span></span></span></div>
                                """,
                                unsafe_allow_html=True,
                            )
                    generation_lock_acquired = True
                    request_timing["命题模型排队耗时"] = time.monotonic() - queue_started
                    if is_full_exam_generation and exam_progress_status is not None:
                        exam_progress_status.update(
                            label="步骤 3/5：正在生成结构化试题、参考答案与评分标准",
                            state="running",
                            expanded=True,
                        )
                    elif not is_full_exam_generation:
                        thinking.markdown("""
                        <div class="thinking-state"><span class="thinking-orb"></span>
                        <span>正在组织答案<span class="thinking-dots"><span>·</span><span>·</span><span>·</span></span></span></div>
                        """, unsafe_allow_html=True)
                for piece in stream_answer(
                    question,
                    context,
                    history,
                    model_images,
                    web_context=web_context,
                    agent_mode=agent_mode,
                    progress_callback=(
                        update_exam_model_progress
                        if is_full_exam_generation
                        else None
                    ),
                    exam_event_callback=(
                        update_exam_generation_event
                        if is_full_exam_generation
                        else None
                    ),
                    generate_exam_artifacts=is_full_exam_generation,
                ):
                    if nonlocal_first["value"]:
                        if not is_full_exam_generation:
                            thinking.empty()
                        request_timing["模型首片段耗时"] = time.monotonic() - model_start
                        nonlocal_first["value"] = False
                    streamed_parts.append(piece)
                    yield piece
            finally:
                if generation_lock_acquired and generation_lock is not None:
                    generation_lock.release()

        try:
            last_render_at = 0.0
            for _piece in tracked_stream():
                now = time.monotonic()
                # Re-rendering the full Markdown/KaTeX tree for every token causes
                # visible scroll judder. Six updates/second still feels live while
                # keeping Markdown and KaTeX layout work comfortably bounded.
                if not is_full_exam_generation and now - last_render_at >= 0.16:
                    answer_placeholder.markdown(normalize_latex("".join(streamed_parts)))
                    last_render_at = now
            thinking.empty()
            raw_response = "".join(streamed_parts)
            if is_full_exam_generation:
                response, artifacts, artifact_status = prepare_exam_response(
                    raw_response,
                    progress_callback=update_exam_artifact_progress,
                )
                if not artifact_status:
                    response = append_web_sources(response, web_results)
                answer_placeholder.markdown(response)
                render_message_artifacts({
                    "role": "assistant",
                    "content": response,
                    "artifacts": artifacts,
                    "_ui_id": f"current_{uuid.uuid4().hex}",
                })
                if exam_progress_status is not None:
                    if artifacts and not artifact_status:
                        exam_progress_status.update(
                            label="已完成：TeX 与 PDF 均可下载",
                            state="complete",
                            expanded=False,
                        )
                    elif artifact_status:
                        exam_progress_status.update(
                            label="处理结束：文件校验或编译未完成",
                            state="error",
                            expanded=True,
                        )
                    else:
                        exam_progress_status.update(
                            label="已完成：本次回答无需生成试卷文件",
                            state="complete",
                            expanded=False,
                        )
            else:
                response = normalize_latex(raw_response)
                response, visualizations = extract_visualizations(response)
                response = append_web_sources(response, web_results)
                visualizations = apply_requested_media_format(visualizations, question)
                answer_placeholder.markdown(response)
                if not visualizations and visualization_requested(question):
                    try:
                        with st.spinner("正在生成可视化代码并运行演示……"):
                            visualizations = plan_visualization(question, response)
                            visualizations = apply_requested_media_format(visualizations, question)
                    except Exception as viz_exc:
                        st.warning(f"可视化规划失败：{viz_exc}")
                render_visualizations(visualizations)
                if source_answer_artifacts_requested:
                    answer_artifact_started = time.monotonic()
                    try:
                        pdf_names = (
                            uploaded_document_bundle.pdf_names
                            if uploaded_document_bundle is not None
                            else ()
                        )
                        with st.spinner("正在安全排版并编译参考答案 PDF……"):
                            answer_bundle = build_answer_artifact_bundle(
                                response,
                                pdf_names=pdf_names,
                                title="大学物理参考答案",
                            )
                        artifacts = [
                            {
                                "name": answer_bundle.tex_name,
                                "mime": answer_bundle.tex_mime,
                                "data": answer_bundle.tex_bytes,
                            },
                            {
                                "name": answer_bundle.pdf_name,
                                "mime": answer_bundle.pdf_mime,
                                "data": answer_bundle.pdf_bytes,
                            },
                        ]
                        request_timing["答案文件编译耗时"] = (
                            time.monotonic() - answer_artifact_started
                        )
                        render_message_artifacts({
                            "role": "assistant",
                            "content": response,
                            "artifacts": artifacts,
                            "_ui_id": f"current_answer_{uuid.uuid4().hex}",
                        })
                    except Exception as artifact_exc:
                        request_timing["答案文件编译耗时"] = (
                            time.monotonic() - answer_artifact_started
                        )
                        request_error = f"参考答案 TeX/PDF 编译失败：{artifact_exc}"
                        request_traceback = traceback.format_exc()
                        compiler_log = str(getattr(artifact_exc, "log", "") or "")
                        if compiler_log:
                            request_traceback += (
                                "\n\n[TeX compiler log]\n" + compiler_log[-12_000:]
                            )
                        st.warning(
                            "答案正文已生成，但参考答案 TeX/PDF 编译未完成："
                            f"{artifact_exc}"
                        )
        except Exception as exc:
            request_error = str(exc)
            request_traceback = traceback.format_exc()
            thinking.empty()
            if is_full_exam_generation:
                artifacts = []
                artifact_status = "model_request_failed"
                response = (
                    str(exc)
                    if isinstance(exc, ExamGenerationError)
                    else "模型调用未能正常完成，本次未保存未校验的试卷内容。请稍后重试。"
                )
                answer_placeholder.markdown(response)
                if exam_progress_status is not None:
                    exam_progress_status.update(
                        label=(
                            "生成中断：结构化试卷未通过校验或超过时限"
                            if isinstance(exc, ExamGenerationError)
                            else "生成中断：模型请求未完成"
                        ),
                        state="error",
                        expanded=True,
                    )
            else:
                response = normalize_latex("".join(streamed_parts))
                response, visualizations = extract_visualizations(response)
                response = append_web_sources(response, web_results)
                visualizations = apply_requested_media_format(visualizations, question)
                answer_placeholder.markdown(response)
                render_visualizations(visualizations)
            if isinstance(exc, ExamGenerationError):
                st.error(str(exc))
            else:
                st.error(f"模型服务调用失败：{exc}")
    detected_chapter = results[0][0].chapter if results else "未分类"
    approximate_input_tokens = max(
        1,
        (len(question) + len(context) + len(web_context)
         + sum(len(item["content"]) for item in history)) // 4,
    )
    approximate_output_tokens = max(1, len("".join(streamed_parts)) // 4)
    request_timing.setdefault("模型流式总耗时", time.monotonic() - model_start)
    request_timing["端到端耗时"] = time.monotonic() - request_started
    interaction_id = analytics_db.log_interaction(
        st.session_state.get("analytics_session_id", ""),
        question,
        response,
        detected_chapter,
        "openai-compatible",
        setting("PHYSICS_MODEL", "未配置"),
        approximate_input_tokens,
        approximate_output_tokens,
        int((time.monotonic() - request_started) * 1000),
        request_error,
        [chunk.source for chunk, _score in results],
        st.session_state.user_id,
        request_timing=request_timing,
        agent_mode=agent_mode,
    )
    if request_error:
        analytics_db.log_error(
            st.session_state.get("analytics_session_id", ""),
            question,
            (
                "tex_compile"
                if request_error.startswith("参考答案 TeX/PDF 编译失败")
                else "model_request"
            ),
            request_error,
            request_traceback,
            st.session_state.user_id,
        )
        st.session_state.analytics_total_errors += 1
    st.session_state.analytics_total_questions += 1
    st.session_state.analytics_tokens_input += approximate_input_tokens
    st.session_state.analytics_tokens_output += approximate_output_tokens
    assistant_message = {
        "role": "assistant",
        "content": response,
        "visualizations": visualizations,
        "artifacts": artifacts,
        "interaction_id": interaction_id,
        "parent_message_id": user_message.get("id"),
    }
    st.session_state.messages.append(assistant_message)
    if st.session_state.user_id is not None:
        assistant_message["id"] = save_message(
            st.session_state.user_id,
            assistant_message,
            agent_mode=agent_mode,
        )
    st.session_state._answer_in_progress = False
    st.rerun()
