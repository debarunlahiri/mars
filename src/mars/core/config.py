"""Runtime configuration (env vars prefixed ``MARS_``; ``.env`` is loaded automatically)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

Provider = Literal["auto", "anthropic", "openai", "google_genai", "mock"]

# (fast/cheap model, strong model) per provider.
DEFAULT_MODELS: dict[str, tuple[str, str]] = {
    "anthropic": ("claude-haiku-5-5", "claude-sonnet-5-5"),
    "openai": ("gpt-4o-mini", "gpt-4o"),
    "google_genai": ("gemini-3.5-flash-lite", "gemini-3.8-flash"),
    "mock": ("mock", "mock"),
}

_KEY_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
}


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MARS_", extra="ignore")

    # --- LLM ---
    provider: Provider = "auto"
    fast_model: str | None = None  # planner + researchers (cheap, high volume)
    strong_model: str | None = None  # analyst + writer + critic (quality matters)
    temperature: float = 0.2
    max_tokens: int = 4096
    llm_timeout: float = 90.0  # seconds per LLM call
    llm_attempts: int = 3  # per call, incl. malformed structured output

    # --- search & page fetching ---
    search_provider: Literal["auto", "tavily", "ddg", "mock"] = "auto"
    search_attempts: int = 3
    search_cache_ttl: float = 900.0  # seconds; 0 disables
    blocked_domains: str = "pinterest.com,facebook.com,instagram.com,tiktok.com,x.com"
    fetch_pages: bool = True  # read full pages, not just search snippets
    fetch_top_k: int = 3  # pages fetched per research task
    fetch_timeout: float = 10.0
    max_page_bytes: int = 1_500_000
    max_page_chars: int = 6000  # extracted text kept per page
    max_evidence_chars: int = 14000  # total evidence shown to one researcher
    respect_robots: bool = True
    user_agent: str = "MARS-Research-Bot/0.2 (+https://github.com/; research assistant)"

    # --- budgets: the knobs that bound cost and latency ---
    max_tasks: int = 4  # sub-tasks the planner may create
    max_results: int = 5  # search results per task
    max_rounds: int = 2  # research rounds (1 = no follow-up round)
    max_revisions: int = 2  # writer rewrites after critic feedback
    max_concurrency: int = 4  # parallel researchers in flight
    run_timeout: float = 300.0  # seconds per run leg

    # --- API ---
    api_keys: str = ""  # comma-separated; empty = auth disabled (local dev only)
    rate_limit_per_min: int = 20  # per API key / client IP; 0 disables
    max_concurrent_runs: int = 4  # beyond this the API answers 503
    cors_origins: str = ""  # comma-separated
    checkpoint_db: str = ""  # SQLite path; empty = in-memory (lost on restart)

    # --- storage & memory ---
    database_url: str = ""  # postgresql://... -> reports, vectors AND checkpoints in Postgres (pgvector)
    storage_db: str = ""  # SQLite file for reports + vectors when no database_url
    embedding_provider: Literal["auto", "hash", "openai", "google", "fastembed", "local"] = "auto"
    embedding_model: str = ""
    embedding_dim: int = 0  # 0 = provider default
    use_memory: bool = False  # let researchers reuse quotes from earlier research
    memory_top_k: int = 3
    memory_min_score: float = 0.4

    # --- hardware (local embedding models, OCR) ---
    device: Literal["auto", "cuda", "mps", "cpu"] = "auto"  # auto: NVIDIA GPU > Apple GPU > CPU

    # --- internal documents (PDF, Word, PowerPoint, Excel, text, images) ---
    docs_db: str = ""  # SQLite file for the document index; empty = documents disabled
    docs_dir: str = ""  # folder kept in sync with the index (add / update / remove automatically)
    docs_sync_interval: float = 30.0  # seconds between scans; 0 = scan only at startup and on request
    use_documents: bool = True  # researchers search the indexed documents
    web_search: bool = True  # False = answer from internal documents only
    docs_top_k: int = 4  # documents (each with its best passages) given to a researcher
    docs_min_score: float = 0.15
    chunk_chars: int = 1200
    chunk_overlap: int = 150
    max_upload_mb: int = 25
    vision_images: bool = True  # describe/transcribe images with the LLM (needs a real provider)

    # --- logging ---
    log_level: str = "INFO"
    log_json: bool = False

    @property
    def api_key_list(self) -> list[str]:
        return _split(self.api_keys)

    @property
    def blocked_domain_list(self) -> list[str]:
        return [d.lower() for d in _split(self.blocked_domains)]

    @property
    def cors_origin_list(self) -> list[str]:
        return _split(self.cors_origins)

    def resolved_provider(self) -> str:
        if self.provider != "auto":
            return self.provider
        for name, var in _KEY_VARS.items():
            if os.environ.get(var):
                return name
        return "mock"

    def resolved_search(self) -> str:
        if self.search_provider != "auto":
            return self.search_provider
        if self.resolved_provider() == "mock":
            return "mock"  # keep the offline demo fully offline
        return "tavily" if os.environ.get("TAVILY_API_KEY") else "ddg"

    def models(self) -> tuple[str, str]:
        fast, strong = DEFAULT_MODELS[self.resolved_provider()]
        return self.fast_model or fast, self.strong_model or strong


@lru_cache
def get_settings() -> Settings:
    return Settings()
