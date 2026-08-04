from __future__ import annotations

import json
import base64
from collections.abc import Iterator

import requests

from config import setting


SYSTEM_PROMPT = """你是“大学物理智能助教”。课程依据祝之光《物理学》第5版。
要求：
1. 优先使用给定教材知识库，不凭空编造教材原文、页码或题号。
2. 回答按“概念定位—核心公式—推导/求解—物理直觉—易错点—自检问题”组织；简单问题可适当精简。
3. 数学公式使用 Markdown LaTeX：行内公式只用 `$...$`，独立公式只用 `$$...$$`；禁止使用 `\\(...\\)`、`\\[...\\]`。明确符号含义、适用条件、矢量方向和 SI 单位。
4. 每个关键结论用 [资料N] 标注依据。资料不足时明确说“知识库证据不足”，再给出通用物理学解释。
5. 对作业题先分析思路，再计算；不伪造实验数据。
"""


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
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": _user_content(question, context, images)})
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model, "messages": messages, "temperature": 0.2, "stream": True}
    with requests.post(f"{base_url}/chat/completions", headers=headers, json=payload,
                       timeout=(15, 180), stream=True) as response:
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


def fallback_answer(question: str, context: str) -> str:
    if not context:
        return "当前知识库没有检索到足够相关的教材内容。请换用更具体的概念、公式或题号提问。"
    return ("当前未配置大模型 API，以下是从祝之光教材知识库检索到的相关内容。\n\n"
            + context[:7000] + "\n\n配置兼容模型服务后，可获得带推导和讲解的智能回答。")
