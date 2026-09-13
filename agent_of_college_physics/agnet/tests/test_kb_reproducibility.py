from __future__ import annotations

import hashlib
import inspect
import json
import sys
from array import array
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import build_kb
from rag import KnowledgeBase


def test_public_record_ids_are_stable_sha256_values() -> None:
    payload = "\0".join(("chunk", "教材/第1章.md", "7", "2"))
    expected = "chunk-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    assert build_kb._stable_record_id("chunk", "教材/第1章.md", 7, 2) == expected
    assert build_kb._stable_record_id("chunk", "教材/第1章.md", 7, 2) == expected
    assert build_kb._stable_record_id("catalog", "教材/第1章.md", 0, 0) != expected
    assert "abs(hash(" not in inspect.getsource(build_kb)


def test_rag_discards_token_copies_and_keeps_bm25_order(tmp_path: Path) -> None:
    corpus = tmp_path / "chunks.jsonl"
    rows = (
        {"id": "strong", "source": "a", "source_type": "test", "page": 1,
         "chapter": "力学", "text": "动量守恒 动量守恒 碰撞", "priority": 1.0},
        {"id": "weak", "source": "b", "source_type": "test", "page": 1,
         "chapter": "力学", "text": "动量与力学基础", "priority": 1.0},
        {"id": "other", "source": "c", "source_type": "test", "page": 1,
         "chapter": "光学", "text": "干涉与衍射", "priority": 1.0},
    )
    corpus.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    kb = KnowledgeBase(corpus)

    assert not hasattr(kb, "tokens")
    assert kb.doc_lengths == [sum(counts.values()) for counts in kb.term_counts]
    assert all(isinstance(posting, array) and posting.typecode == "I"
               for posting in kb.postings.values())
    assert [chunk.id for chunk, _score in kb.search("动量守恒", top_k=3)] == ["strong", "weak"]
