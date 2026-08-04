from __future__ import annotations

import random
import re
import time

import streamlit as st
import streamlit.components.v1 as components

from build_kb import build
from config import KB_FILE
from llm import stream_answer
from rag import KnowledgeBase, context_text

st.set_page_config(page_title="大学物理智能助教", page_icon="⚛️", layout="wide", initial_sidebar_state="expanded")

theme_mode = st.query_params.get("mode", "system")
if theme_mode not in {"light", "system", "dark"}:
    theme_mode = "system"
dark_rules = """
.stApp,[data-testid="stAppViewContainer"] {background:linear-gradient(145deg,#111923 0%,#182431 100%)!important;color:#e8eef5!important}
[data-testid="stHeader"],[data-testid="stBottomBlockContainer"] {background:#0d141d!important}
.welcome,.welcome *,.quick-head {color:#edf3f8!important}
.hero-subtitle,.quick-note,.tip {color:#c7d2de!important}
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
.stApp {background:linear-gradient(145deg,#f7f9fc 0%,#edf2f7 100%);color:#26384a}
[data-testid="stHeader"] {background:#f7f9fc}
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
#MainMenu,[data-testid="stToolbar"],[data-testid="stAppDeployButton"] {display:none!important}
.theme-switcher {position:fixed;right:1.15rem;top:.72rem;z-index:999999;display:flex;align-items:center;gap:.12rem;padding:.2rem;border-radius:1.4rem;background:rgba(128,145,163,.13);border:1px solid rgba(128,145,163,.2);backdrop-filter:blur(8px)}
.theme-option {text-decoration:none!important;width:1.9rem;height:1.9rem;border-radius:50%;display:flex;align-items:center;justify-content:center;color:inherit;font-size:.92rem;opacity:.58;transition:background .16s ease,opacity .16s ease,transform .16s ease}
.theme-option:hover {background:rgba(128,145,163,.18);opacity:1;transform:translateY(-1px)}
.theme-option.active {background:rgba(76,119,153,.24);box-shadow:0 1px 5px rgba(23,50,77,.14);opacity:1}
.block-container {max-width: 980px; padding-top: 4.25rem; padding-bottom: 1rem}
.stElementContainer:has(> .stMarkdown .hero),
[data-testid="stElementContainer"]:has(.hero) {position:sticky;top:.55rem;z-index:9900}
.hero {max-width:900px;padding:.9rem 2rem .85rem;border-radius:16px;background:linear-gradient(120deg,#17324d,#1d3f5d);color:white;margin:0 auto .8rem;text-align:center;box-shadow:0 10px 26px rgba(23,50,77,.11)}
.hero h1 {font-size:clamp(1.65rem,2.8vw,2.2rem);line-height:1.1;margin:0 0 .4rem;font-weight:800;letter-spacing:-.02em}
.hero-subtitle {font-size:.96rem;line-height:1.5;color:rgba(255,255,255,.84)}
.welcome {max-width:800px;margin:0 auto .6rem;color:#26384a;font-size:.91rem;line-height:1.42}
.welcome-line {display:flex;align-items:center;gap:.65rem;margin-bottom:.25rem}
.bot-icon {display:inline-flex;width:2rem;height:2rem;align-items:center;justify-content:center;border-radius:9px;background:#ff9f1c;color:white;flex:0 0 auto}
.welcome ul {margin:.15rem 0 .35rem 2.75rem;padding-left:1rem}
.course-map {margin:.2rem 0 0 2.75rem;color:#40556a}
.course-map b {color:#17324d}
.tip {margin:.4rem 0 0 2.75rem;color:#66788a}
.quick-head {text-align:center;margin:.65rem 0 .1rem;color:#17324d;font-size:1.2rem;font-weight:750}
.quick-note {text-align:center;color:#66788a;margin-bottom:.45rem;font-size:.9rem}
.stButton>button {min-height:2.55rem;border:1px solid #d7e0e8;border-radius:12px;background:rgba(255,255,255,.94);color:#17324d;font-weight:650;text-align:left;padding:.35rem .85rem;box-shadow:0 4px 14px rgba(23,50,77,.05);transition:all .16s ease}
.stButton>button:hover {border-color:#3d739d;color:#0f3555;transform:translateY(-1px);box-shadow:0 8px 20px rgba(23,50,77,.1)}
.source {border-left:4px solid #c8923a;padding:.55rem .8rem;background:white;border-radius:6px;margin:.35rem 0}
.thinking-state {display:flex;align-items:center;gap:.8rem;padding:.6rem .1rem;color:inherit;font-weight:650}
.thinking-orb {width:1.15rem;height:1.15rem;border-radius:50%;border:3px solid rgba(80,126,163,.28);border-top-color:#5f9ccc;animation:thinking-spin .85s linear infinite;flex:0 0 auto}
.thinking-dots span {display:inline-block;animation:thinking-bounce 1.2s infinite;opacity:.28}
.thinking-dots span:nth-child(2){animation-delay:.16s}.thinking-dots span:nth-child(3){animation-delay:.32s}
[data-testid="stSidebar"] .stButton>button {min-height:2.7rem;font-size:.86rem;text-align:left;margin-bottom:.12rem}
[data-testid="stSidebar"] .sidebar-quick-note {font-size:.8rem;opacity:.7;margin:-.3rem 0 .55rem}
@keyframes thinking-spin {to{transform:rotate(360deg)}}
@keyframes thinking-bounce {0%,60%,100%{transform:translateY(0);opacity:.28}30%{transform:translateY(-3px);opacity:1}}
</style>
<div class="theme-switcher" role="group" aria-label="亮度模式">__THEME_LINKS__</div>
<div class="hero"><h1>⚛️ 大学物理智能助教</h1><div class="hero-subtitle">以祝之光《物理学》第5版为课程基准 · 本地RAG检索 · 图片识题 · 智能讲解 · 习题辅导</div></div>
"""
st.markdown(page_markup.replace("__THEME_CSS__", theme_css)
                       .replace("__THEME_LINKS__", theme_links), unsafe_allow_html=True)

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
    text = text.replace(r"\[", "\n$$\n").replace(r"\]", "\n$$\n")
    text = text.replace(r"\(", "$").replace(r"\)", "$")
    # Keep display delimiters on their own lines so Markdown cannot treat them as text.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text

if not KB_FILE.exists():
    with st.spinner("首次运行：正在生成本地知识库……"):
        build()

@st.cache_resource
def load_kb(stamp: float):
    return KnowledgeBase(KB_FILE)

kb = load_kb(KB_FILE.stat().st_mtime)
if "messages" not in st.session_state:
    st.session_state.messages = []
if "quick_questions" not in st.session_state:
    st.session_state.quick_questions = new_quick_questions()

quick_question = None
chapter = "全部"
top_k = 6
with st.sidebar:
    st.subheader("⚡ 快速提问")
    st.markdown('<div class="sidebar-quick-note">点击问题即可直接开始，也可随时换一组</div>', unsafe_allow_html=True)
    if st.button("↻ 换一换", key="sidebar_refresh_quick", use_container_width=True):
        st.session_state.quick_questions = new_quick_questions()
        st.rerun()
    for index, quick in enumerate(st.session_state.quick_questions):
        if st.button(quick, key=f"sidebar_quick_{index}", use_container_width=True):
            quick_question = quick

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        for image in message.get("images", []):
            st.image(image["data"], caption=image.get("name"), width=360)
        st.markdown(normalize_latex(message["content"]))

if not st.session_state.messages:
    st.markdown("""
    <div class="welcome">
      <div class="welcome-line"><span class="bot-icon">🤖</span><span>你好！我是你的<b>大学物理智能助教</b>，可以陪你理解概念、推导公式和分析习题。</span></div>
      <ul>
        <li><b>教材增强：</b>回答前检索祝之光教材、习题解答和课程资料</li>
        <li><b>分步讲解：</b>给出思路、公式条件、计算过程与易错点</li>
        <li><b>来源可查：</b>标注PDF页码、课件页码和原始文件位置</li>
      </ul>
      <div class="course-map"><b>力学与热学：</b>运动、动力学、刚体、振动与波、气体动理论、热力学</div>
      <div class="course-map"><b>电磁与近代物理：</b>静电场、磁场、电磁感应、波动光学、量子物理</div>
      <div class="tip">💡 支持LaTeX公式、教材题号和你的完整解题过程。</div>
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
    message_images = [] if quick_question else uploaded_images
    st.session_state.messages.append({"role": "user", "content": question, "images": message_images})
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
        <span>正在查阅教材并组织讲解<span class="thinking-dots"><span>·</span><span>·</span><span>·</span></span></span></div>
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
            answer_placeholder.markdown(response)
        except Exception as exc:
            thinking.empty()
            response = normalize_latex("".join(streamed_parts))
            answer_placeholder.markdown(response)
            st.error(f"模型服务调用失败：{exc}")
    st.session_state.messages.append({"role": "assistant", "content": response})
