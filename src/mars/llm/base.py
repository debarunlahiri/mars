from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    async def structured(self, schema: type[T], system: str, user: str) -> T: ...

    async def text(self, system: str, user: str) -> str: ...
