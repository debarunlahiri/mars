"""Text embedders. ``hash`` works offline; ``openai`` / ``fastembed`` give real semantic quality."""

from __future__ import annotations

import asyncio
import hashlib
import os
from typing import Protocol

import numpy as np

from ..core.config import Settings
from ..core.logging import get_logger
from ..core.text import tokens

log = get_logger("embeddings")


class Embedder(Protocol):
    name: str
    dim: int

    async def embed(self, texts: list[str]) -> np.ndarray: ...


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return (m / np.where(norms == 0, 1, norms)).astype(np.float32)


class HashEmbedder:
    """Feature-hashed bag of unigrams + bigrams. Lexical, not semantic: it finds texts that share
    words, not paraphrases. Deterministic, dependency-free, ideal for tests and offline use."""

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.name = f"hash-{dim}"

    async def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            toks = tokens(text)
            for feat in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]:
                h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
                out[row, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        return _normalize(out)


class LangChainEmbedder:
    def __init__(self, spec: str, dim: int, **kwargs):
        from langchain.embeddings import init_embeddings

        self._model = init_embeddings(spec, **kwargs)
        self.name, self.dim = spec, dim

    async def embed(self, texts: list[str]) -> np.ndarray:
        vecs = await self._model.aembed_documents(texts)
        return _normalize(np.array(vecs, dtype=np.float32))


class FastEmbedder:
    """Local ONNX model (no API key, no network after the first download)."""

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model)
        self.name = f"fastembed:{model}"
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    async def embed(self, texts: list[str]) -> np.ndarray:
        vecs = await asyncio.to_thread(lambda: list(self._model.embed(texts)))
        return _normalize(np.array(vecs, dtype=np.float32))


def build_embedder(s: Settings) -> Embedder:
    choice = s.embedding_provider
    if choice == "auto":
        provider = s.resolved_provider()
        if provider == "mock":
            choice = "hash"
        elif provider == "google_genai":
            choice = "google"
        elif provider == "openai" or os.environ.get("OPENAI_API_KEY"):
            choice = "openai"
        else:
            try:
                import fastembed  # noqa: F401

                choice = "fastembed"
            except ImportError:
                choice = "hash"
    if choice == "openai":
        model = s.embedding_model or "text-embedding-3-small"
        return LangChainEmbedder(f"openai:{model}", s.embedding_dim or 1536)
    if choice == "google":
        # 768 dims: good quality, and within pgvector's 2000-dim HNSW index limit.
        dim = s.embedding_dim or 768
        model = s.embedding_model or "gemini-embedding-001"
        return LangChainEmbedder(f"google_genai:{model}", dim, output_dimensionality=dim)
    if choice == "fastembed":
        return FastEmbedder(s.embedding_model or "BAAI/bge-small-en-v1.5")
    if choice == "hash":
        log.info("using the offline hash embedder (lexical matching only)")
        return HashEmbedder(s.embedding_dim or 256)
    raise ValueError(f"unknown embedding provider {choice!r}")
