"""Report evaluation: deterministic structure/citation/grounding checks + optional LLM judge."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from ..core.text import tokens
from ..prompts import JUDGE_SYSTEM
from ..schemas import JudgeScore, Report
from ..workflow.deps import Deps

_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_STOP = frozenset(
    "the a an and or of to in on for with is are was were be been by as at from that this it its "
    "their than then also can may more most such which while into over under not no but if".split()
)


@dataclass
class EvalResult:
    has_citations: bool
    citations_valid: bool  # every [n] points at a real source
    well_cited: bool  # no substantive uncited paragraphs
    source_coverage: float  # share of retrieved sources the report actually used
    lexical_support: float  # share of cited sentences whose words appear in the cited quotes
    topic_coverage: float | None  # share of expected topics mentioned (None if none given)
    has_structure: bool  # at least 2 headings
    min_length: bool
    coherence: int | None  # 1-5 from the LLM judge, None if not run
    passed: bool

    def to_dict(self) -> dict:
        return asdict(self)


def lexical_support(report: Report, threshold: float = 0.35) -> float:
    """Cheap faithfulness proxy: for each cited sentence, the fraction of its content words that
    occur in the verified quotes of the sources it cites. Paraphrase lowers it, so treat it as a
    trend metric rather than ground truth."""
    quotes = {s.id: " ".join(s.quotes + [s.snippet]) for s in report.sources}
    body = report.markdown.split("\n## Sources")[0]
    supported = total = 0
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", body):
        ids = {int(n) for m in _CITE.findall(sentence) for n in re.split(r"\s*,\s*", m)}
        ids &= quotes.keys()
        if not ids:
            continue
        words = {w for w in tokens(_CITE.sub(" ", sentence)) if w not in _STOP and len(w) > 2}
        if not words:
            continue
        evidence = set(tokens(" ".join(quotes[i] for i in ids)))
        total += 1
        supported += len(words & evidence) / len(words) >= threshold
    return round(supported / total, 3) if total else 0.0


async def evaluate(
    report: Report,
    deps: Deps | None = None,
    expected_topics: list[str] | None = None,
    min_words: int = 80,
) -> EvalResult:
    cc = report.citation_check
    has_citations = bool(cc.cited_ids)
    valid = not cc.invalid_ids
    well_cited = cc.uncited_paragraphs == 0
    structure = len(re.findall(r"^#{1,3} ", report.markdown, re.MULTILINE)) >= 2
    long_enough = len(report.markdown.split()) >= min_words
    support = lexical_support(report)

    topic_cov = None
    if expected_topics:
        text = report.markdown.casefold()
        topic_cov = round(sum(t.casefold() in text for t in expected_topics) / len(expected_topics), 3)

    coherence = None
    if deps is not None:
        score = await deps.strong.structured(
            JudgeScore, JUDGE_SYSTEM, f"Question: {report.question}\n\nReport:\n{report.markdown}"
        )
        coherence = score.coherence

    passed = (
        report.status == "complete"
        and has_citations
        and valid
        and well_cited
        and structure
        and (topic_cov is None or topic_cov >= 0.5)
        and (coherence is None or coherence >= 3)
    )
    return EvalResult(
        has_citations,
        valid,
        well_cited,
        cc.coverage,
        support,
        topic_cov,
        structure,
        long_enough,
        coherence,
        passed,
    )
