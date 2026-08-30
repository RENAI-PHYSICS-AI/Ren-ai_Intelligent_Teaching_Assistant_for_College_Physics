"""Optional, fail-open web search for time-sensitive physics questions."""
from __future__ import annotations

import re
import threading
import time
from urllib.parse import urlparse

import requests

from config import setting


_CACHE: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()
_SEARCH_MARKERS = re.compile(
    r"联网|上网|网页|网上(?:信息|资料|内容|来源|参考)?|网络搜索|"
    r"网络(?:上|中|的)?(?:信息|资料|内容|来源|参考)|搜索一下|查一下|查阅网络|"
    r"最新|近期|目前|当前|现状|"
    r"进展|新闻|实时|今天|本月|今年|现行(?:标准|规范|政策)|20\d{2}年",
    re.IGNORECASE,
)
_RECENCY_MARKERS = re.compile(r"最新|近期|新闻|实时|今天|本月|今年|20\d{2}年")


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(setting(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def web_search_enabled() -> bool:
    return (
        setting("PHYSICS_WEB_SEARCH_PROVIDER", "").strip().lower() == "tavily"
        and bool(setting("TAVILY_API_KEY", "").strip())
    )


def should_search_web(question: str) -> bool:
    """Search only when the question explicitly needs current external information."""
    return web_search_enabled() and bool(_SEARCH_MARKERS.search(question or ""))


def _clean_result(item: dict) -> dict | None:
    url = str(item.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    title = re.sub(r"\s+", " ", str(item.get("title") or parsed.netloc)).strip()[:180]
    content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()[:600]
    if not content:
        return None
    return {"title": title, "url": url, "content": content}


def search_web(question: str) -> list[dict]:
    """Return sanitized Tavily results; any network/API failure becomes no results."""
    if not should_search_web(question):
        return []
    max_results = _bounded_int("PHYSICS_WEB_SEARCH_MAX_RESULTS", 5, 1, 8)
    cache_minutes = _bounded_int("PHYSICS_WEB_SEARCH_CACHE_MINUTES", 30, 1, 1440)
    cache_key = (re.sub(r"\s+", " ", question.strip()), max_results)
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < cache_minutes * 60:
            return [dict(item) for item in cached[1]]

    payload = {
        "query": question,
        "search_depth": "basic",
        "chunks_per_source": 1,
        "max_results": max_results,
        "topic": "general",
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "auto_parameters": False,
    }
    if _RECENCY_MARKERS.search(question):
        payload["time_range"] = "year"
    timeout = _bounded_int("PHYSICS_WEB_SEARCH_TIMEOUT_SECONDS", 8, 3, 30)
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {setting('TAVILY_API_KEY').strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(5, timeout),
        )
        with response:
            response.raise_for_status()
            raw_results = response.json().get("results") or []
    except (requests.RequestException, ValueError, TypeError):
        return []

    results = []
    seen_urls = set()
    for raw in raw_results:
        cleaned = _clean_result(raw) if isinstance(raw, dict) else None
        if not cleaned or cleaned["url"] in seen_urls:
            continue
        seen_urls.add(cleaned["url"])
        results.append(cleaned)
        if len(results) >= max_results:
            break
    with _CACHE_LOCK:
        _CACHE[cache_key] = (now, results)
    return [dict(item) for item in results]


def web_context_text(results: list[dict], max_chars: int = 3000) -> str:
    """Build a bounded, clearly untrusted context section for the answer model."""
    sections = []
    used = 0
    for index, item in enumerate(results, start=1):
        block = (
            f"[联网{index}] {item['title']}\n"
            f"网址：{item['url']}\n"
            f"摘要：{item['content']}"
        )
        remaining = max_chars - used
        if remaining <= 0:
            break
        sections.append(block[:remaining])
        used += len(sections[-1]) + 2
    return "\n\n".join(sections)


def append_web_sources(answer: str, results: list[dict]) -> str:
    """Attach deterministic source links so web-assisted answers stay auditable."""
    if not results:
        return answer
    links = "\n".join(f"- [{item['title']}]({item['url']})" for item in results)
    return f"{answer.rstrip()}\n\n---\n**联网参考来源**\n{links}"
