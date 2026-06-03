"""Embedding provider abstraction.

Two providers:
  * LocalEmbeddingProvider  - deterministic, dependency-free, no API key. Hashes
                              token n-grams into a fixed-dim vector. Good enough
                              for demoing semantic-ish retrieval and for tests.
  * OpenAIEmbeddingProvider - real embeddings when OPENAI_API_KEY is configured.

Switching providers is a one-line config change (EMBEDDING_PROVIDER).
"""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.utils.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class LocalEmbeddingProvider(EmbeddingProvider):
    """Deterministic hashing embedder. Same text -> same vector, always."""

    def __init__(self, dim: int | None = None):
        self.dim = dim or settings.embedding_dim

    def _tokens(self, text: str) -> list[str]:
        return _TOKEN_RE.findall((text or "").lower())

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = self._tokens(text)
        if not tokens:
            return vec
        # Unigrams + bigrams hashed into buckets (a tiny "hashing trick" model).
        grams = list(tokens)
        grams += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        for gram in grams:
            h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 7) & 1 else -1.0
            vec[idx] += sign
        # L2 normalize so cosine similarity is just a dot product.
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self):
        from openai import OpenAI  # imported lazily

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_embedding_model
        self.dim = settings.embedding_dim

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        logger.info("Using OpenAI embedding provider (%s).", settings.openai_embedding_model)
        return OpenAIEmbeddingProvider()
    if settings.embedding_provider == "openai":
        logger.warning("EMBEDDING_PROVIDER=openai but no OPENAI_API_KEY; using local fallback.")
    return LocalEmbeddingProvider()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
