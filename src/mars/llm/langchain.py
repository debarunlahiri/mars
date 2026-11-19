"""Provider-agnostic LLM wrapper (Anthropic / OpenAI / Gemini via LangChain)."""

from __future__ import annotations

import asyncio
import base64
from typing import Any, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from ..core.errors import StructuredOutputError
from ..core.logging import get_logger
from ..core.resilience import retry
from ..core.usage import track

T = TypeVar("T", bound=BaseModel)
IMAGE_PROMPT = (
    "Read this image for a research archive. First transcribe every piece of visible text verbatim. "
    "Then describe what it shows factually: for charts, tables and diagrams give the title, axes, "
    "labels and the actual values or relationships. Do not speculate beyond what is visible."
)
log = get_logger("llm")


def _track_usage(message: Any) -> None:
    meta = getattr(message, "usage_metadata", None) or {}
    track(
        llm_calls=1,
        input_tokens=int(meta.get("input_tokens", 0)),
        output_tokens=int(meta.get("output_tokens", 0)),
    )


class LangChainLLM:
    def __init__(
        self,
        model: str,
        provider: str,
        temperature: float,
        max_tokens: int,
        timeout: float = 90.0,
        attempts: int = 3,
    ):
        self.name = model
        self._timeout = timeout
        self._attempts = attempts
        self._model = init_chat_model(
            model,
            model_provider=provider,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=2,  # SDK-level retries for 429/5xx; ours below cover malformed output
        )

    @staticmethod
    def _messages(system: str, user: str):
        return [SystemMessage(content=system), HumanMessage(content=user)]

    async def structured(self, schema: type[T], system: str, user: str) -> T:
        runnable = self._model.with_structured_output(schema, include_raw=True)

        async def call() -> T:
            out = await asyncio.wait_for(runnable.ainvoke(self._messages(system, user)), self._timeout + 5)
            _track_usage(out.get("raw"))
            parsed = out.get("parsed")
            if out.get("parsing_error") or parsed is None:
                raise StructuredOutputError(
                    f"{self.name} returned invalid {schema.__name__}: {out.get('parsing_error')}"
                )
            return parsed if isinstance(parsed, schema) else schema.model_validate(parsed)

        return await retry(call, attempts=self._attempts, name=f"{self.name}:{schema.__name__}")

    async def describe_image(self, image: bytes, mime: str) -> str:
        """Transcribe and describe an image (multimodal chat models only)."""
        data = base64.b64encode(image).decode()
        message = HumanMessage(
            content=[
                {"type": "text", "text": IMAGE_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}},
            ]
        )

        async def call() -> str:
            resp = await asyncio.wait_for(self._model.ainvoke([message]), self._timeout + 5)
            _track_usage(resp)
            content = resp.content
            if isinstance(content, list):
                content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
            return str(content).strip()

        return await retry(call, attempts=self._attempts, name=f"{self.name}:vision")

    async def text(self, system: str, user: str) -> str:
        async def call() -> str:
            resp = await asyncio.wait_for(
                self._model.ainvoke(self._messages(system, user)), self._timeout + 5
            )
            _track_usage(resp)
            content = resp.content
            if isinstance(content, list):  # content blocks (Anthropic, Gemini)
                content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
            text = str(content).strip()
            if not text:
                raise StructuredOutputError(f"{self.name} returned an empty response")
            return text

        return await retry(call, attempts=self._attempts, name=f"{self.name}:text")
