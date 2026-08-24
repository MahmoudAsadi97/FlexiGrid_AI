"""Embedding backends for dense retrieval.

Three interchangeable backends, tried in this order under ``auto``:

1. ``ollama`` — an OpenAI-compatible ``/v1/embeddings`` endpoint (Ollama with
   ``nomic-embed-text`` by default). Preferred on the demo machine: one local
   runtime serves both the LLM and the embedder, fully offline.
2. ``sbert``  — sentence-transformers (``all-MiniLM-L6-v2``) when the optional
   dependency is installed and its weights are cached locally.
3. ``tfidf``  — a deterministic TF-IDF + truncated-SVD (LSA) vectorizer fitted
   on the corpus. No downloads, no network; used in CI and as the guaranteed
   fallback so retrieval never goes down.

Every backend reports its name and model so that traces, the API health
endpoint, and the evaluation report can state exactly which embedder produced
a given number.
"""

from __future__ import annotations

import math
import os
from typing import Protocol

import httpx


class EmbeddingBackend(Protocol):
    name: str
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class OllamaEmbeddings:
    """OpenAI-compatible /v1/embeddings client (Ollama, LM Studio, etc.)."""

    name = "ollama"

    def __init__(self, base_url: str | None = None, model: str | None = None,
                 timeout: float = 60.0) -> None:
        self.base_url = (base_url or os.getenv("FLEXIGRID_LLM_BASE_URL",
                                               "http://localhost:11434/v1")).rstrip("/")
        self.model = model or os.getenv("FLEXIGRID_EMBED_MODEL", "nomic-embed-text")
        self.timeout = timeout

    def available(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/models", timeout=3.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/embeddings",
            json={"model": self.model, "input": texts},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        ordered = sorted(payload["data"], key=lambda item: item["index"])
        return [_normalize(item["embedding"]) for item in ordered]


class SbertEmbeddings:
    """sentence-transformers backend (optional dependency)."""

    name = "sbert"

    def __init__(self, model: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer  # lazy import

        self.model = model or os.getenv("FLEXIGRID_SBERT_MODEL",
                                        "sentence-transformers/all-MiniLM-L6-v2")
        self._encoder = SentenceTransformer(self.model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._encoder.encode(texts, normalize_embeddings=True)
        return [vector.tolist() for vector in vectors]


class TfidfEmbeddings:
    """Deterministic TF-IDF + LSA fallback fitted on the corpus. No network."""

    name = "tfidf"
    model = "tfidf-svd-128"

    def __init__(self, corpus_texts: list[str], dimensions: int = 128) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(
            lowercase=True, sublinear_tf=True, ngram_range=(1, 2),
            min_df=1, stop_words="english",
        )
        matrix = self._vectorizer.fit_transform(corpus_texts)
        components = min(dimensions, matrix.shape[1] - 1, matrix.shape[0] - 1)
        self._svd = TruncatedSVD(n_components=max(2, components), random_state=13)
        self._svd.fit(matrix)

    def embed(self, texts: list[str]) -> list[list[float]]:
        matrix = self._svd.transform(self._vectorizer.transform(texts))
        return [_normalize(row.tolist()) for row in matrix]


def resolve_backend(corpus_texts: list[str],
                    preference: str | None = None) -> EmbeddingBackend:
    """Pick an embedding backend. ``preference``: auto|ollama|sbert|tfidf."""
    choice = (preference or os.getenv("FLEXIGRID_EMBEDDINGS", "auto")).lower()

    if choice in ("auto", "ollama"):
        ollama = OllamaEmbeddings()
        if ollama.available():
            try:  # verify the embedding model actually answers
                ollama.embed(["backend probe"])
                return ollama
            except httpx.HTTPError:
                pass
        if choice == "ollama":
            raise RuntimeError(
                "Ollama embeddings requested but unavailable. Run `ollama serve` "
                f"and `ollama pull {os.getenv('FLEXIGRID_EMBED_MODEL', 'nomic-embed-text')}`."
            )

    if choice in ("auto", "sbert"):
        try:
            return SbertEmbeddings()
        except Exception:
            if choice == "sbert":
                raise RuntimeError(
                    "sentence-transformers requested but not installed/cached. "
                    "pip install sentence-transformers"
                )

    return TfidfEmbeddings(corpus_texts)
