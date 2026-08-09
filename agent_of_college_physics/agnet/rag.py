from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    source_type: str
    page: int
    chapter: str
    text: str
    relative_path: str = ""
    locator: str = ""
    priority: float = 1.0

    @classmethod
    def from_dict(cls, data: dict) -> "Chunk":
        return cls(**{k: data.get(k, "") for k in cls.__annotations__})


def _terms(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    chinese = [normalized[i : i + 2] for i in range(max(0, len(normalized) - 1))
               if "\u4e00" <= normalized[i] <= "\u9fff"]
    latin = re.findall(r"[a-z][a-z0-9_]{1,}|\d+(?:\.\d+)?", text.lower())
    return chinese + latin


class KnowledgeBase:
    """Small, dependency-free BM25 retriever suitable for a local teaching app."""

    def __init__(self, path: Path):
        self.path = path
        self.chunks: list[Chunk] = []
        self.tokens: list[list[str]] = []
        self.df: Counter[str] = Counter()
        self.avg_len = 1.0
        self.reload()

    def reload(self) -> None:
        self.chunks = []
        if self.path.exists():
            with self.path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        self.chunks.append(Chunk.from_dict(json.loads(line)))
        self.tokens = [_terms(c.text + c.chapter) for c in self.chunks]
        self.df = Counter()
        for terms in self.tokens:
            self.df.update(set(terms))
        self.avg_len = sum(map(len, self.tokens)) / max(1, len(self.tokens))

    @property
    def chapters(self) -> list[str]:
        return sorted({c.chapter for c in self.chunks if c.chapter})

    def search(self, query: str, *, chapter: str = "全部", top_k: int = 6) -> list[tuple[Chunk, float]]:
        qterms = _terms(query)
        if not qterms:
            return []
        n = max(1, len(self.chunks)); k1 = 1.5; b = 0.75
        results: list[tuple[Chunk, float]] = []
        for chunk, terms in zip(self.chunks, self.tokens):
            if chapter != "全部" and chunk.chapter != chapter:
                continue
            counts = Counter(terms); length = max(1, len(terms)); score = 0.0
            for term in qterms:
                tf = counts[term]
                if not tf:
                    continue
                idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / self.avg_len))
            score *= float(chunk.priority or 1.0)
            if score:
                results.append((chunk, score))
        return sorted(results, key=lambda item: item[1], reverse=True)[:top_k]


def context_text(results: Iterable[tuple[Chunk, float]], max_chars: int = 10000) -> str:
    blocks = []
    used = 0
    for i, (chunk, _) in enumerate(results, 1):
        location = chunk.locator or (f"PDF第{chunk.page}页" if chunk.page else "文件索引")
        block = f"[资料{i}] {chunk.source}｜{chunk.chapter}｜{location}\n{chunk.text}"
        if used + len(block) > max_chars:
            break
        blocks.append(block); used += len(block)
    return "\n\n".join(blocks)
