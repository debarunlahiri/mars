"""Writer: synthesize insights into a cited Markdown report."""

from __future__ import annotations

from ..prompts import WRITER_SYSTEM, stamped, writer_user
from ..schemas import Analysis, Source
from ..workflow.deps import Deps


async def write(
    deps: Deps,
    question: str,
    analysis: Analysis,
    sources: list[Source],
    previous_draft: str = "",
    issues: list[str] | None = None,
    guidance: str = "",
) -> str:
    return await deps.strong.text(
        stamped(WRITER_SYSTEM),
        writer_user(question, analysis, sources, previous_draft, issues, guidance),
    )


def render_sources(sources: list[Source], cited_ids: list[int]) -> str:
    """The reference list is generated from the registry, never written by the LLM."""
    by_id = {s.id: s for s in sources}
    lines = []
    for i in cited_ids:
        if i in by_id:
            s = by_id[i]
            title = s.title.replace("[", "(").replace("]", ")")
            lines.append(f"[{i}] [{title}]({s.url})" + (f" — {s.published}" if s.published else ""))
    return "\n\n## Sources\n\n" + "\n".join(lines) if lines else ""
