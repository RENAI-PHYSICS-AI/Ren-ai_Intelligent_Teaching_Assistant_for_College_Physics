from __future__ import annotations

import json
import base64
import math
import re
from collections.abc import Iterator

import requests

from config import setting


SYSTEM_PROMPT = """你是“大学物理智能助教”。课程依据祝之光《物理学》第5版。
要求：
1. 优先使用给定教材知识库，不凭空编造教材原文、页码或题号。
2. 结合最近对话理解代词、追问和学生当前思路，先承接上一轮再展开本轮；不要把每一轮写成彼此独立的百科条目。
3. 回答要形成一条清晰主线，用自然过渡连接概念、公式、推导和结论。仅在确有帮助时使用小标题，避免机械套用固定模板、重复自我介绍或重复总结。
4. 数学公式使用 Markdown LaTeX：行内公式只用 `$...$`，独立公式只用 `$$...$$`；禁止使用 `\\(...\\)`、`\\[...\\]`。明确符号含义、适用条件、矢量方向和 SI 单位。
5. 不向学生显示 `[资料N]`、页码、文件名或其他引用标记。资料不足时可说明依据有限，再给出可靠的通用物理解释。
6. 对作业题先说明各步骤之间的因果关系，再计算；不伪造实验数据。
7. 回答以给定的本地知识库为核心。若当前模型服务确实具备联网检索能力，可检索可靠网络资料补充背景、最新进展或知识库未覆盖的内容；教材课程口径与网络内容不一致时，以教材为准并自然说明差异。不得伪称已经联网、不得编造网页、链接或检索结果；无法联网时只使用本地知识库、最近对话和可靠的通用物理知识。
8. 网络资料只能作为补充，回答仍应围绕学生问题形成统一主线。除非学生明确要求来源，否则不要输出内部检索标记、来源编号或冗长链接列表。
9. 当学生明确要求绘图、曲线、轨迹或可视化，或图形明显有助于理解时，在回答末尾追加一个单行、合法 JSON 的隐藏注释，不要用代码块包裹：
   <!--PHYSICS_VIZ:{"kind":"function","title":"简谐振动","x_label":"t / s","y_label":"x / m","x_min":0,"x_max":6.28,"series":[{"name":"x(t)","expression":"cos(2*x)"}]}-->
   支持四种 kind：
   - function：自变量固定为 x；每条 series 使用 expression。
   - parametric：使用 parameter、min、max；每条 series 使用 x_expression、y_expression。
   - animation：使用 parameter、min、max；每条 series 使用 x_expression、y_expression，应用会生成带播放按钮的运动动画。可用 output_format 指定 interactive、gif、mp4 或 both。
   - data：每条 series 使用等长数值数组 x、y。
   表达式只允许数字、变量、pi、e、+ - * / ** 和 sin/cos/tan/exp/log/log10/sqrt/abs。最多生成3张图，每张最多6条曲线。不要在正文另写可视化代码，应用会自动生成并运行安全代码演示。
"""


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    """Read a bounded integer setting and tolerate missing/invalid values."""
    try:
        value = int(setting(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _estimate_text_tokens(text: str) -> int:
    """Conservative token estimate for mixed Chinese, English and LaTeX text."""
    if not text:
        return 0
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text))
    other = len(text) - cjk
    return cjk + math.ceil(other / 4)


def _estimate_content_tokens(content: str | list[dict]) -> int:
    if isinstance(content, str):
        return _estimate_text_tokens(content)
    total = 0
    for item in content:
        if item.get("type") == "text":
            total += _estimate_text_tokens(str(item.get("text", "")))
        elif item.get("type") == "image_url":
            # Vision token use depends on image dimensions; reserve a safe allowance.
            total += 1600
    return total


def _history_for_context(history: list[dict], current_content: str | list[dict]) -> list[dict]:
    """Keep as many recent complete turns as fit in the configured context window."""
    context_window = _int_setting("PHYSICS_CONTEXT_WINDOW", 32768, 4096, 262144)
    output_reserve = _int_setting(
        "PHYSICS_MAX_OUTPUT_TOKENS", 6144, 512, max(512, context_window // 2)
    )
    max_messages = _int_setting("PHYSICS_HISTORY_MAX_MESSAGES", 40, 2, 200)
    fixed_tokens = (
        _estimate_text_tokens(SYSTEM_PROMPT)
        + _estimate_content_tokens(current_content)
        + 256
    )
    available = max(0, context_window - output_reserve - fixed_tokens)

    # Group messages into user-led turns so trimming never leaves an orphaned answer.
    turns: list[list[dict]] = []
    for message in history[-max_messages:]:
        if message.get("role") == "user" or not turns:
            turns.append([message])
        else:
            turns[-1].append(message)

    selected: list[list[dict]] = []
    used = 0
    for turn in reversed(turns):
        turn_tokens = sum(
            _estimate_content_tokens(message.get("content", "")) + 8
            for message in turn
        )
        if used + turn_tokens > available:
            break
        selected.append(turn)
        used += turn_tokens

    return [message for turn in reversed(selected) for message in turn]


def _visible_text(chunks: Iterator[str]) -> Iterator[str]:
    """Hide model <think> blocks while keeping normal text genuinely streaming."""
    buffer = ""
    in_thinking = False
    emitted = False
    for piece in chunks:
        if not piece:
            continue
        buffer += piece
        while buffer:
            if in_thinking:
                end = buffer.find("</think>")
                if end < 0:
                    buffer = buffer[-16:]
                    break
                buffer = buffer[end + len("</think>"):]
                in_thinking = False
                continue
            start = buffer.find("<think>")
            if start >= 0:
                if start:
                    emitted = True
                    yield buffer[:start]
                buffer = buffer[start + len("<think>"):]
                in_thinking = True
                continue
            if len(buffer) > 16:
                emitted = True
                yield buffer[:-16]
                buffer = buffer[-16:]
            break
    if buffer and not in_thinking:
        emitted = True
        yield buffer
    if not emitted:
        yield "模型完成了推理，但没有返回可显示的回答。"


def _user_content(question: str, context: str,
                  images: list[dict] | None = None) -> str | list[dict]:
    text = f"知识库检索结果：\n{context}\n\n学生问题：{question}"
    if not images:
        return text
    content: list[dict] = [{"type": "text", "text": text}]
    for item in images:
        encoded = base64.b64encode(item["data"]).decode("ascii")
        mime = item.get("mime") or "image/png"
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{encoded}"},
        })
    return content


def stream_answer(question: str, context: str, history: list[dict],
                  images: list[dict] | None = None) -> Iterator[str]:
    api_key = setting("PHYSICS_API_KEY") or setting("DASHSCOPE_API_KEY")
    configured_base = setting("PHYSICS_BASE_URL")
    base_url = (configured_base or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = setting("PHYSICS_MODEL", "qwen-plus")
    # LAN OpenAI-compatible services may intentionally run without authentication.
    if not api_key and not configured_base:
        yield fallback_answer(question, context)
        return
    current_content = _user_content(question, context, images)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_history_for_context(history, current_content))
    messages.append({"role": "user", "content": current_content})
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": _int_setting("PHYSICS_MAX_OUTPUT_TOKENS", 6144, 512, 32768),
        "stream": True,
        "enable_search": True,
    }
    response = requests.post(
        f"{base_url}/chat/completions", headers=headers, json=payload,
        timeout=(15, 180), stream=True,
    )
    if response.status_code in {400, 404, 422}:
        response.close()
        payload.pop("enable_search", None)
        response = requests.post(
            f"{base_url}/chat/completions", headers=headers, json=payload,
            timeout=(15, 180), stream=True,
        )
    with response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/event-stream" not in content_type:
            data = response.json()
            yield from _visible_text(iter([data["choices"][0]["message"].get("content", "")]))
            return

        def raw_chunks() -> Iterator[str]:
            for raw_line in response.iter_lines(decode_unicode=False):
                if not raw_line:
                    continue
                line = raw_line.decode("utf-8", errors="replace")
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                try:
                    data = json.loads(line)
                    choices = data.get("choices") or []
                    if choices:
                        content = (choices[0].get("delta") or {}).get("content")
                        if content:
                            yield content
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue

        yield from _visible_text(raw_chunks())


def answer(question: str, context: str, history: list[dict],
           images: list[dict] | None = None) -> str:
    return "".join(stream_answer(question, context, history, images))


VISUALIZATION_TOOL = {
    "type": "function",
    "function": {
        "name": "create_physics_visualization",
        "description": "生成可由本项目安全执行的物理可视化规范。",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["function", "parametric", "animation", "data"]},
                "title": {"type": "string"},
                "x_label": {"type": "string"},
                "y_label": {"type": "string"},
                "x_min": {"type": "number"}, "x_max": {"type": "number"},
                "parameter": {"type": "string"},
                "min": {"type": "number"}, "max": {"type": "number"},
                "output_format": {"type": "string", "enum": ["interactive", "gif", "mp4", "both"]},
                "series": {
                    "type": "array", "minItems": 1, "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "expression": {"type": "string"},
                            "x_expression": {"type": "string"},
                            "y_expression": {"type": "string"},
                            "x": {"type": "array", "items": {"type": "number"}},
                            "y": {"type": "array", "items": {"type": "number"}},
                            "markers": {"type": "boolean"},
                        },
                        "required": ["name"],
                    },
                },
            },
            "required": ["kind", "title", "x_label", "y_label", "series"],
        },
    },
}


def visualization_requested(question: str) -> bool:
    compact = question.lower().replace(" ", "")
    return any(word in compact for word in (
        "绘图", "画图", "绘制", "画出", "可视化", "曲线", "轨迹", "图像", "plot",
        "动画", "动图", "gif", "mp4", "视频", "运行代码", "运行演示", "动态演示",
    ))


def plan_visualization(question: str, answer_text: str) -> list[dict]:
    """Force a structured chart tool call when the main answer omitted its spec."""
    api_key = setting("PHYSICS_API_KEY") or setting("DASHSCOPE_API_KEY")
    configured_base = setting("PHYSICS_BASE_URL")
    if not configured_base and not api_key:
        return []
    base_url = (configured_base or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = setting("PHYSICS_MODEL", "qwen-plus")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "只调用 create_physics_visualization，生成一张最有帮助的图。function 的自变量必须写作 x；"
                    "parametric 使用指定 parameter；若学生要求动画、动图、GIF、MP4、视频或动态演示，必须使用 animation，"
                    "用 x_expression、y_expression 表示运动点随 parameter 的轨迹；要求GIF时 output_format=gif，"
                    "要求MP4或视频时 output_format=mp4，两者都要求时 output_format=both，否则为interactive；"
                    "表达式只允许数字、变量、pi、e、+ - * / ** 以及 "
                    "sin cos tan exp log log10 sqrt abs。不要输出正文。"
                ),
            },
            {"role": "user", "content": f"学生问题：{question}\n\n已有回答：{answer_text[:3500]}"},
        ],
        "temperature": 0,
        "max_tokens": 900,
        "stream": False,
        "tools": [VISUALIZATION_TOOL],
        "tool_choice": "auto",
    }
    response = requests.post(
        f"{base_url}/chat/completions", headers=headers, json=payload, timeout=(15, 90)
    )
    response.raise_for_status()
    message = response.json()["choices"][0]["message"]
    calls = message.get("tool_calls") or []
    if calls:
        arguments = calls[0].get("function", {}).get("arguments", "{}")
        spec = json.loads(arguments) if isinstance(arguments, str) else arguments
    else:
        # Some local OpenAI-compatible servers return the requested JSON as
        # normal content even when tools are supplied. Accept that fallback.
        content = str(message.get("content") or "").strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end < start:
            return []
        spec = json.loads(content[start:end + 1])
    if isinstance(spec, dict) and spec.get("kind") in {"function", "parametric", "animation", "data"}:
        return [spec]
    return []


def fallback_answer(question: str, context: str) -> str:
    if not context:
        return "当前知识库没有检索到足够相关的教材内容。请换用更具体的概念、公式或题号提问。"
    return ("当前未配置大模型 API，以下是从祝之光教材知识库检索到的相关内容。\n\n"
            + context[:7000] + "\n\n配置兼容模型服务后，可获得带推导和讲解的智能回答。")
