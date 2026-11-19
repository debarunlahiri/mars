"""Critic: LLM review + deterministic citation checks."""

from __future__ import annotations

import re

from ..core.logging import get_logger
from ..prompts import CRITIC_SYSTEM, critic_user, stamped
from ..schemas import Analysis, CitationCheck, Critique, Source
from ..workflow.deps import Deps

log = get_logger("critic")

_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
MIN_CLAIM_CHARS = 120  # shorter paragraphs are treated as transitions, not claims


def check_citations(markdown: str, sources: list[Source]) -> CitationCheck:
    valid = {s.id for s in sources}
    cited: set[int] = set()
    uncited = 0
    # Code blocks and display math are not prose claims (and may contain "[1]"-like indexing).
    markdown = re.sub(r"```.*?```|\$\$.*?\$\$", "", markdown, flags=re.S)
    for para in re.split(r"\n\s*\n", markdown):
        para = para.strip()
        if not para or para.startswith(("#", "```")):
            continue
        ids = {int(n) for m in _CITE.findall(para) for n in re.split(r"\s*,\s*", m)}
        cited |= ids
        if not ids and len(para) >= MIN_CLAIM_CHARS:
            uncited += 1
    return CitationCheck(
        cited_ids=sorted(cited & valid),
        invalid_ids=sorted(cited - valid),
        uncited_paragraphs=uncited,
        coverage=round(len(cited & valid) / len(valid), 3) if valid else 0.0,
    )


async def critique(
    deps: Deps, question: str, draft: str, analysis: Analysis, sources: list[Source]
) -> tuple[Critique, CitationCheck]:
    check = check_citations(draft, sources)

    # Deterministic issues first: cheap, reliable, and they cannot be talked out of by the LLM.
    issues: list[str] = []
    if not check.cited_ids:
        issues.append("The report contains no valid citations. Cite sources inline as [n].")
    if check.invalid_ids:
        issues.append(f"Remove or fix citations to non-existent sources: {check.invalid_ids}.")
    if check.uncited_paragraphs:
        issues.append(f"{check.uncited_paragraphs} paragraph(s) make claims without citations.")

    # The LLM review is best effort: if it keeps failing, the deterministic checks still decide.
    llm_ok = True
    try:
        review = await deps.strong.structured(
            Critique, stamped(CRITIC_SYSTEM), critic_user(question, draft, analysis, sources)
        )
        issues += review.issues
        llm_ok = review.approved
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM critic unavailable, using deterministic checks only: %r", exc)
    return Critique(approved=llm_ok and not issues, issues=issues), check
