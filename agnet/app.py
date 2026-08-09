from __future__ import annotations

import json
import random
import re
import time
import traceback

import streamlit as st
import streamlit.components.v1 as components

from build_kb import build
import admin_auth
import analytics_db
from config import APP_DIR, KB_FILE, setting
from experiment_hub import render_experiment_hub
from llm import plan_visualization, stream_answer, visualization_requested
from rag import KnowledgeBase, context_text
from storage import (
    authenticate,
    clear_messages,
    create_user,
    init_db,
    load_messages,
    messages_to_markdown,
    save_message,
)
from visualization import apply_requested_media_format, extract_visualizations, render_visualizations

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

theme_links = "".join(
    f'<a class="theme-option{" active" if theme_mode == value else ""}" href="?mode={value}" '
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
#MainMenu,[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stAppDeployButton"] {display:none!important}
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
    text = re.sub(r"\s*\[资料\s*\d+\]", "", text)
    text = text.replace(r"\[", "\n$$\n").replace(r"\]", "\n$$\n")
    text = text.replace(r"\(", "$").replace(r"\)", "$")
    # Keep display delimiters on their own lines so Markdown cannot treat them as text.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


@st.cache_resource
def load_kb(stamp: float):
    return KnowledgeBase(KB_FILE)


@st.cache_resource
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


def refresh_account_state() -> None:
    if st.session_state.user_id is None:
        st.session_state.user_role = "anonymous"
        return
    account = analytics_db.get_user_by_id(st.session_state.user_id)
    st.session_state.user_role = (account or {}).get("role", "student")


def admin_login_target() -> str:
    admin_token = (
        setting("ADMIN_TOKEN")
        or setting("ADMIN_ANALYTICS_TOKEN")
        or admin_auth.load_or_create_local_secret(
            APP_DIR / "data" / "admin_signing_secret"
        )
    )
    admin_login_url = setting(
        "ADMIN_LOGIN_URL", "http://127.0.0.1:8603/admin-login"
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
    st.info("管理员身份验证成功，正在进入管理后台……")
    st.link_button("立即进入管理员后台", target, use_container_width=True)
    components.html(
        f"""
        <script>
        window.parent.setTimeout(() => {{
          window.parent.location.replace({json.dumps(target)});
        }}, 120);
        </script>
        """,
        height=0,
    )
    st.stop()


def record_feedback(message: dict, rating: str, comment: str = "") -> None:
    analytics_db.log_feedback(
        message.get("interaction_id"),
        st.session_state.get("analytics_session_id", ""),
        rating,
        comment,
        st.session_state.user_id,
    )


def render_answer_feedback(message: dict, key: str) -> None:
    interaction_id = message.get("interaction_id")
    if not interaction_id:
        return
    state_key = f"feedback_done_{interaction_id}"
    if st.session_state.get(state_key):
        st.caption("已收到你的评价，谢谢。")
        return
    good_col, bad_col, _ = st.columns([1, 1, 6])
    if good_col.button("👍 有帮助", key=f"{key}_good"):
        record_feedback(message, "good")
        st.session_state[state_key] = True
        st.rerun()
    if bad_col.button("👎 待改进", key=f"{key}_bad"):
        record_feedback(message, "bad")
        st.session_state[state_key] = True
        st.rerun()

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
                landing_username = st.text_input("用户名", key="landing_login_username")
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
                    st.error("用户名或密码错误。")
                else:
                    st.session_state.user_id = user_id
                    st.session_state.username = canonical_username
                    st.session_state.messages = load_messages(user_id)
                    st.session_state.access_granted = True
                    st.rerun()
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
                        for existing_message in st.session_state.messages:
                            save_message(user_id, existing_message)
                        st.session_state.user_id = user_id
                        st.session_state.username = landing_register_username.strip()
                        st.session_state.access_granted = True
                        st.rerun()
        st.markdown("<div style='height:.35rem'></div>", unsafe_allow_html=True)
        if st.button("无需注册，匿名进入", key="anonymous_login", use_container_width=True):
            st.session_state.user_id = None
            st.session_state.username = "匿名用户"
            st.session_state.access_granted = True
            st.rerun()
        st.caption("匿名模式不会将历史记录保存到服务器，但仍可导出 Markdown。")
    st.stop()

refresh_account_state()
redirect_admin_after_login()
if st.session_state.get("analytics_session_user_id", object()) != st.session_state.user_id:
    reset_analytics_session()
else:
    analytics_db.touch_session(st.session_state.get("analytics_session_id"))

quick_question = None
chapter = "全部"
top_k = 6
with st.sidebar:
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
    workspace_mode = st.radio(
        "学习模式",
        ["智能助教", "可视化实验"],
        format_func=lambda value: (
            "💬  智能助教" if value == "智能助教" else "📊  可视化实验"
        ),
        key="workspace_mode",
        label_visibility="collapsed",
        width="stretch",
    ) or "智能助教"
    st.divider()

    if workspace_mode == "智能助教":
        st.subheader("⚡ 快速提问")
        st.markdown('<div class="sidebar-quick-note">点击问题即可直接开始，也可随时换一组</div>', unsafe_allow_html=True)
        if st.button("↻ 换一换", key="sidebar_refresh_quick", use_container_width=True):
            st.session_state.quick_questions = new_quick_questions()
            st.rerun()
        for index, quick in enumerate(st.session_state.quick_questions):
            if st.button(quick, key=f"sidebar_quick_{index}", use_container_width=True):
                quick_question = quick
    else:
        st.subheader("🧪 实验导航")
        st.markdown(
            '<div class="sidebar-quick-note">选择一个实验，在主区域调节参数并观察结果</div>',
            unsafe_allow_html=True,
        )
        if st.button("〽 李萨如图形", key="sidebar_lissajous", use_container_width=True):
            st.session_state.visual_experiment_name = "李萨如图形"
            st.rerun()
        if st.button("∿ 声速测量", key="sidebar_sound_speed", use_container_width=True):
            st.session_state.visual_experiment_name = "声速测量"
            st.rerun()

    st.divider()
    with st.expander("👤 用户与历史", expanded=False):
        if st.session_state.user_id is None:
            st.caption("当前为匿名使用，无需登录；记录仅保留在本次会话中。")
            login_tab, register_tab = st.tabs(["登录", "注册"])
            with login_tab:
                with st.form("login_form"):
                    login_username = st.text_input("用户名", key="login_username")
                    login_password = st.text_input("密码", type="password", key="login_password")
                    login_submit = st.form_submit_button("登录", use_container_width=True)
                if login_submit:
                    user_id, canonical_username = authenticate(login_username, login_password)
                    if user_id is None:
                        st.error("用户名或密码错误。")
                    else:
                        st.session_state.user_id = user_id
                        st.session_state.username = canonical_username
                        st.session_state.messages = load_messages(user_id)
                        st.rerun()
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
                            for existing_message in st.session_state.messages:
                                save_message(user_id, existing_message)
                            st.session_state.user_id = user_id
                            st.session_state.username = register_username.strip()
                            st.rerun()
            if st.button("返回登录入口", key="leave_anonymous", use_container_width=True):
                st.session_state.access_granted = False
                st.rerun()
        else:
            st.success(f"已登录：{st.session_state.username}")
            account = analytics_db.get_user_by_id(st.session_state.user_id) or {}
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
                st.session_state.access_granted = False
                st.session_state.pop("workspace_mode", None)
                st.rerun()

        if st.session_state.messages:
            markdown_history = messages_to_markdown(
                st.session_state.messages, st.session_state.username
            )
            st.download_button(
                "⬇ 导出 Markdown",
                data=markdown_history.encode("utf-8-sig"),
                file_name="大学物理智能助教_对话记录.md",
                mime="text/markdown; charset=utf-8",
                use_container_width=True,
            )
            confirm_clear = st.checkbox("确认清空全部对话记录", key="confirm_clear_history")
            if st.button(
                "清空记录", key="clear_history", use_container_width=True,
                disabled=not confirm_clear,
            ):
                if st.session_state.user_id is not None:
                    clear_messages(st.session_state.user_id)
                st.session_state.messages = []
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

# Some browsers remember a collapsed sidebar after the login transition.
# Re-open it once the authenticated page has mounted so mode navigation and
# quick questions are always reachable.
components.html(
    """
    <script>
    (() => {
      let attempts = 0;
      const restoreSidebar = () => {
        attempts += 1;
        const doc = window.parent.document;
        const sidebar = doc.querySelector('[data-testid="stSidebar"]');
        if (sidebar && sidebar.getAttribute('aria-expanded') === 'false') {
          const button = sidebar.querySelector('[data-testid="stBaseButton-headerNoPadding"]');
          if (button) {
            button.click();
            return;
          }
        }
        if ((!sidebar || sidebar.getAttribute('aria-expanded') === 'false') && attempts < 30) {
          window.setTimeout(restoreSidebar, 100);
        }
      };
      restoreSidebar();
    })();
    </script>
    """,
    height=0,
)

if workspace_mode == "可视化实验":
    render_experiment_hub()
    st.stop()

if not KB_FILE.exists():
    with st.spinner("首次运行：正在生成本地知识库……"):
        build()
kb = load_kb(KB_FILE.stat().st_mtime)

for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        for image in message.get("images", []):
            st.image(image["data"], caption=image.get("name"), width=360)
        st.markdown(normalize_latex(message["content"]))
        render_visualizations(message.get("visualizations", []))
        if message["role"] == "assistant":
            render_answer_feedback(message, f"history_feedback_{message_index}")

if not st.session_state.messages:
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
      <div class="tip">💡 支持LaTeX公式、图片识题和交互式物理图表。</div>
    </div>
    """, unsafe_allow_html=True)
typed_input = st.chat_input(
    "输入问题，或将题目图片直接粘贴到这里……",
    accept_file="multiple",
    file_type=["png", "jpg", "jpeg", "webp"],
    max_upload_size=20,
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
    typed_question = "请识别图片中的大学物理题目或物理信息，并给出完整、清晰的分析与解答。"
question = quick_question or typed_question
if question:
    request_started = time.monotonic()
    request_error = None
    request_traceback = ""
    message_images = [] if quick_question else uploaded_images
    user_message = {"role": "user", "content": question, "images": message_images}
    st.session_state.messages.append(user_message)
    if st.session_state.user_id is not None:
        save_message(st.session_state.user_id, user_message)
    with st.chat_message("user"):
        for image in message_images:
            st.image(image["data"], caption=image.get("name"), width=360)
        st.markdown(question)
    results = kb.search(question, chapter=chapter, top_k=top_k)
    context = context_text(results)
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]]
    with st.chat_message("assistant"):
        thinking = st.empty()
        thinking.markdown("""
        <div class="thinking-state"><span class="thinking-orb"></span>
        <span>正在查阅本地知识并整合补充资料<span class="thinking-dots"><span>·</span><span>·</span><span>·</span></span></span></div>
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

        def tracked_stream():
            nonlocal_first = {"value": True}
            for piece in stream_answer(question, context, history, message_images):
                if nonlocal_first["value"]:
                    thinking.empty()
                    nonlocal_first["value"] = False
                streamed_parts.append(piece)
                yield piece

        try:
            last_render_at = 0.0
            for _piece in tracked_stream():
                now = time.monotonic()
                # Re-rendering the full Markdown/KaTeX tree for every token causes
                # visible scroll judder. Six updates/second still feels live while
                # keeping Markdown and KaTeX layout work comfortably bounded.
                if now - last_render_at >= 0.16:
                    answer_placeholder.markdown(normalize_latex("".join(streamed_parts)))
                    last_render_at = now
            thinking.empty()
            response = normalize_latex("".join(streamed_parts))
            response, visualizations = extract_visualizations(response)
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
        except Exception as exc:
            request_error = str(exc)
            request_traceback = traceback.format_exc()
            thinking.empty()
            response = normalize_latex("".join(streamed_parts))
            response, visualizations = extract_visualizations(response)
            visualizations = apply_requested_media_format(visualizations, question)
            answer_placeholder.markdown(response)
            render_visualizations(visualizations)
            st.error(f"模型服务调用失败：{exc}")
        feedback_slot = st.empty()
    detected_chapter = results[0][0].chapter if results else "未分类"
    approximate_input_tokens = max(
        1,
        (len(question) + len(context) + sum(len(item["content"]) for item in history)) // 4,
    )
    approximate_output_tokens = max(1, len(response) // 4)
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
    )
    if request_error:
        analytics_db.log_error(
            st.session_state.get("analytics_session_id", ""),
            question,
            "model_request",
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
        "interaction_id": interaction_id,
    }
    st.session_state.messages.append(assistant_message)
    if st.session_state.user_id is not None:
        save_message(st.session_state.user_id, assistant_message)
    with feedback_slot.container():
        render_answer_feedback(assistant_message, f"current_feedback_{interaction_id}")
