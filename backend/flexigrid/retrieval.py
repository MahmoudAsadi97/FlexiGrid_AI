"""Hybrid retrieval over the FlexiGrid corpus.

Three modes, all returning the same result shape so they can be swapped and
ablated:

- ``bm25``   — Okapi BM25 over lowercase tokens (the lexical baseline).
- ``dense``  — cosine similarity over embeddings from ``embeddings.py``.
- ``hybrid`` — reciprocal-rank fusion (RRF) of the two rankings (default).

The retriever is deterministic for a given corpus + backend: ties break on
``chunk_id``. Scores from every mode are attached to the results so the UI and
the evaluation harness can show *why* a chunk ranked where it did.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter

from .embeddings import EmbeddingBackend, resolve_backend
from .ingest import Chunk, corpus_fingerprint, load_corpus

_TOKEN = re.compile(r"[a-z0-9][a-z0-9.\-]*")

_BM25_K1 = 1.5
_BM25_B = 0.75
_RRF_K = 60  # standard reciprocal-rank-fusion constant


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class RetrievalIndex:
    """BM25 + dense index over the corpus, built once per process."""

    def __init__(self, chunks: list[Chunk] | None = None,
                 embedding_preference: str | None = None) -> None:
        self.chunks = chunks or load_corpus()
        self.fingerprint = corpus_fingerprint(self.chunks)

        # --- lexical (BM25) index ---------------------------------------
        self._docs_tokens: list[list[str]] = []
        self._doc_freq: Counter[str] = Counter()
        for chunk in self.chunks:
            tokens = tokenize(f"{chunk.title} {chunk.section} {chunk.text} "
                              + " ".join(chunk.tags))
            self._docs_tokens.append(tokens)
            self._doc_freq.update(set(tokens))
        self._avg_len = (sum(len(tokens) for tokens in self._docs_tokens)
                         / len(self._docs_tokens))
        self._tf: list[Counter[str]] = [Counter(tokens) for tokens in self._docs_tokens]

        # --- dense index (lazy) ------------------------------------------
        self._embedding_preference = embedding_preference
        self._backend: EmbeddingBackend | None = None
        self._vectors: list[list[float]] | None = None
        self._dense_lock = threading.Lock()

    # -- dense helpers ----------------------------------------------------
    @property
    def backend(self) -> EmbeddingBackend:
        with self._dense_lock:
            if self._backend is None:
                corpus_texts = [f"{c.title}. {c.section}. {c.text}" for c in self.chunks]
                self._backend = resolve_backend(corpus_texts, self._embedding_preference)
            return self._backend

    def _ensure_vectors(self) -> list[list[float]]:
        backend = self.backend
        with self._dense_lock:
            if self._vectors is None:
                corpus_texts = [f"{c.title}. {c.section}. {c.text}" for c in self.chunks]
                self._vectors = backend.embed(corpus_texts)
            return self._vectors

    # -- scoring ----------------------------------------------------------
    def _bm25_scores(self, query: str) -> list[float]:
        query_tokens = tokenize(query)
        n_docs = len(self.chunks)
        scores = [0.0] * n_docs
        for token in query_tokens:
            df = self._doc_freq.get(token)
            if not df:
                continue
            idf = math.log(1 + (n_docs - df + 0.5) / (df + 0.5))
            for index in range(n_docs):
                tf = self._tf[index].get(token, 0)
                if not tf:
                    continue
                length_norm = 1 - _BM25_B + _BM25_B * len(self._docs_tokens[index]) / self._avg_len
                scores[index] += idf * (tf * (_BM25_K1 + 1)) / (tf + _BM25_K1 * length_norm)
        return scores

    def _dense_scores(self, query: str) -> list[float]:
        vectors = self._ensure_vectors()
        query_vector = self.backend.embed([query])[0]
        return [sum(a * b for a, b in zip(query_vector, vector)) for vector in vectors]

    @staticmethod
    def _ranks(scores: list[float], chunk_ids: list[str]) -> dict[int, int]:
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], chunk_ids[i]))
        return {index: rank for rank, index in enumerate(order)}

    # -- public API -------------------------------------------------------
    def retrieve(self, query: str, top_k: int = 4,
                 mode: str = "hybrid") -> list[dict[str, object]]:
        if mode not in ("bm25", "dense", "hybrid"):
            raise ValueError(f"Unknown retrieval mode: {mode}")
        top_k = min(max(top_k, 1), 8)
        chunk_ids = [chunk.chunk_id for chunk in self.chunks]

        bm25 = self._bm25_scores(query) if mode in ("bm25", "hybrid") else None
        dense = self._dense_scores(query) if mode in ("dense", "hybrid") else None

        if mode == "bm25":
            fused = bm25
        elif mode == "dense":
            fused = dense
        else:
            bm25_rank = self._ranks(bm25, chunk_ids)
            dense_rank = self._ranks(dense, chunk_ids)
            fused = [
                1.0 / (_RRF_K + bm25_rank[i]) + 1.0 / (_RRF_K + dense_rank[i])
                for i in range(len(self.chunks))
            ]

        order = sorted(range(len(self.chunks)),
                       key=lambda i: (-fused[i], chunk_ids[i]))[:top_k]
        results = []
        for rank, index in enumerate(order):
            chunk = self.chunks[index]
            results.append({
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "section": chunk.section,
                "text": chunk.text,
                "source_type": chunk.source_type,
                "rank": rank + 1,
                "score": round(fused[index], 5),
                "scores": {
                    "bm25": round(bm25[index], 4) if bm25 is not None else None,
                    "dense": round(dense[index], 4) if dense is not None else None,
                },
                "mode": mode,
            })
        return results


_default_index: RetrievalIndex | None = None
_default_lock = threading.Lock()


def get_index() -> RetrievalIndex:
    global _default_index
    with _default_lock:
        if _default_index is None:
            _default_index = RetrievalIndex()
        return _default_index


def retrieve(query: str, top_k: int = 4, mode: str = "hybrid") -> list[dict[str, object]]:
    """Module-level convenience used by tools, the API, and the MCP server."""
    return get_index().retrieve(query, top_k=top_k, mode=mode)
