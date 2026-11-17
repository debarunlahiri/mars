"""Text cleaning and quote verification."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁠﻿]")
_SPACE = re.compile(r"[ \t\r\f\v]+")
_NONWORD = re.compile(r"[^\w]+", re.UNICODE)


def clean_text(text: str, limit: int | None = None) -> str:
    """Strip control/invisible characters and collapse whitespace; optionally truncate."""
    text = _CTRL.sub("", text or "")
    text = "\n".join(_SPACE.sub(" ", line).strip() for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if limit is not None and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def tokens(text: str) -> list[str]:
    return _NONWORD.sub(" ", text.casefold()).split()


def quote_supported(quote: str, evidence: str, threshold: float = 0.85, min_tokens: int = 4) -> bool:
    """True if ``quote`` (near-)verbatim appears in ``evidence``.

    The LLM must back each claim with a quote; this check is what keeps the quote honest.
    Tolerates punctuation/case/whitespace differences and small wording drift.
    """
    q, e = tokens(quote), tokens(evidence)
    if len(q) < min_tokens or not e:
        return False
    qs, es = " ".join(q), " ".join(e)
    if qs in es:
        return True
    n = len(q)
    qset = set(q)
    for i in range(max(1, len(e) - n + 1)):
        window = e[i : i + n]
        if len(qset.intersection(window)) / len(qset) < threshold * 0.8:  # cheap prefilter
            continue
        if SequenceMatcher(None, q, window, autojunk=False).ratio() >= threshold:
            return True
    return False
