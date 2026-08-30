from __future__ import annotations

import json
import heapq
import math
import re
from collections import Counter, OrderedDict
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

    def __init__(self, path: Path | Iterable[Path]):
        if isinstance(path, (str, Path)):
            self.paths = (Path(path),)
        else:
            self.paths = tuple(Path(item) for item in path)
        # Preserve the original public attribute for existing single-index callers.
        self.path = self.paths[0] if len(self.paths) == 1 else self.paths
        self.chunks: list[Chunk] = []
        self.tokens: list[list[str]] = []
        self.term_counts: list[Counter[str]] = []
        self.postings: dict[str, list[int]] = {}
        self.df: Counter[str] = Counter()
        self.idf: dict[str, float] = {}
        self.avg_len = 1.0
        self.chapters_index: dict[str, set[int]] = {}
        self._search_cache: OrderedDict[tuple[str, tuple[str, ...], int], list[tuple[int, float]]] = OrderedDict()
        self._search_cache_size = 200
        self.reload()

    def reload(self) -> None:
        self.chunks = []
        for path in self.paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        self.chunks.append(Chunk.from_dict(json.loads(line)))
        self.tokens = [_terms(c.text + c.chapter) for c in self.chunks]
        self.term_counts = [Counter(terms) for terms in self.tokens]
        self.df = Counter()
        self.postings = {}
        self.chapters_index = {}
        for index, counts in enumerate(self.term_counts):
            chunk = self.chunks[index]
            self.chapters_index.setdefault(chunk.chapter or "全部", set()).add(index)
            for term in counts:
                self.df[term] += 1
                self.postings.setdefault(term, []).append(index)
        self.avg_len = sum(map(len, self.tokens)) / max(1, len(self.tokens))
        n = max(1, len(self.chunks))
        self.idf = {
            term: math.log(1 + (n - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in self.df.items()
        }
        self._search_cache.clear()

    @property
    def chapters(self) -> list[str]:
        return sorted({c.chapter for c in self.chunks if c.chapter})

    def search(self, query: str, *, chapter: str = "全部", top_k: int = 6) -> list[tuple[Chunk, float]]:
        qterms = _terms(query)
        if not qterms:
            return []

        try:
            top_k_int = int(top_k)
        except (TypeError, ValueError):
            top_k_int = 6
        top_k_int = max(1, min(top_k_int, 50))

        qterms_unique = tuple(sorted(set(qterms)))
        cache_key = (chapter, qterms_unique, top_k_int)
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            self._search_cache.move_to_end(cache_key)
            return [(self.chunks[idx], score) for idx, score in cached]

        k1 = 1.5
        b = 0.75
        candidate_ids: set[int] = set()

        if chapter == "全部":
            for term in qterms_unique:
                candidate_ids.update(self.postings.get(term, ()))
        else:
            chapter_ids = self.chapters_index.get(chapter, set())
            if not chapter_ids:
                return []
            chapter_ids = set(chapter_ids)
            for term in qterms_unique:
                for idx in self.postings.get(term, ()):  # filter by chapter during gather
                    if idx in chapter_ids:
                        candidate_ids.add(idx)

        if not candidate_ids:
            return []

        results: list[tuple[float, int]] = []
        for index in candidate_ids:
            counts = self.term_counts[index]
            chunk = self.chunks[index]
            length = max(1, len(self.tokens[index]))
            score = 0.0
            for term in qterms_unique:
                tf = counts[term]
                if not tf:
                    continue
                idf = self.idf.get(term, 0.0)
                score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / self.avg_len))
            score *= float(chunk.priority or 1.0)
            if score:
                results.append((score, index))

        best = heapq.nlargest(top_k_int, results, key=lambda item: item[0])
        scored = [(idx, score) for score, idx in best]
        self._search_cache[cache_key] = scored
        if len(self._search_cache) > self._search_cache_size:
            self._search_cache.popitem(last=False)

        return [(self.chunks[idx], score) for idx, score in scored]


def context_text(results: Iterable[tuple[Chunk, float]], max_chars: int = 10000) -> str:
    blocks = []
    used = 0
    for i, (chunk, _) in enumerate(results, 1):
        location = chunk.locator or (f"PDF第{chunk.page}页" if chunk.page else "文件索引")
        block = f"[资料{i}] {chunk.source}｜{chunk.chapter}｜{location}\n{chunk.text}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)
