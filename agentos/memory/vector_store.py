"""
Retrieval-augmented long-term memory.

Stores past task outcomes and recalls the most relevant ones for a new goal.
Uses embeddings when the LLM endpoint serves them (cosine similarity, pure
Python), and transparently falls back to keyword (token-overlap) scoring when
embeddings are unavailable — so recall works even on free tiers without an
embedding model.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import math
import re

from agentos.llm.client import LLMClient, global_llm


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


class MemoryRecord:
    __slots__ = ("text", "metadata", "embedding")

    def __init__(self, text: str, metadata: Dict[str, Any], embedding: Optional[List[float]]):
        self.text = text
        self.metadata = metadata
        self.embedding = embedding


class VectorStore:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or global_llm
        self._records: List[MemoryRecord] = []
        # Whether the last add/search used real embeddings.
        self.embeddings_active: bool = False

    def add(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Store a memory. Uses an embedding when available, else keyword-only."""
        embedding = None
        vecs = self.llm.embed([text]) if self.llm else None
        if vecs:
            embedding = vecs[0]
            self.embeddings_active = True
        self._records.append(MemoryRecord(text=text, metadata=metadata or {}, embedding=embedding))

    def search(self, query: str, k: int = 3) -> List[Tuple[float, MemoryRecord]]:
        """Return the top-k (score, record) matches for a query."""
        if not self._records:
            return []

        query_vec = None
        vecs = self.llm.embed([query]) if self.llm else None
        if vecs:
            query_vec = vecs[0]

        scored: List[Tuple[float, MemoryRecord]] = []
        if query_vec is not None:
            for r in self._records:
                if r.embedding is not None:
                    scored.append((_cosine(query_vec, r.embedding), r))
                else:
                    scored.append((self._keyword_score(query, r.text), r))
        else:
            # Pure keyword fallback.
            for r in self._records:
                scored.append((self._keyword_score(query, r.text), r))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [s for s in scored[:k] if s[0] > 0.0]

    @staticmethod
    def _keyword_score(query: str, text: str) -> float:
        q, t = _tokens(query), _tokens(text)
        if not q or not t:
            return 0.0
        return len(q & t) / len(q | t)  # Jaccard overlap

    def recall_context(self, query: str, k: int = 3) -> str:
        """Format the top matches as a context block for prompt injection."""
        matches = self.search(query, k=k)
        if not matches:
            return ""
        lines = ["Relevant past task outcomes (for reference):"]
        for score, rec in matches:
            goal = rec.metadata.get("goal", "")
            lines.append(f"- (relevance {score:.2f}) {goal}: {rec.text[:200]}")
        return "\n".join(lines)

    def size(self) -> int:
        return len(self._records)


# Global long-term memory instance.
global_memory = VectorStore()
