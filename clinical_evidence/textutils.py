"""Small, dependency-free text helpers used to align free-text evidence.

The helpers deliberately stay simple and explainable: clinicians reviewing the
extension output must be able to trace why a piece of evidence was surfaced.
"""

from __future__ import annotations

import re
from typing import Iterable

__all__ = [
    "concepts",
    "follow_up_interval_days",
    "is_negated",
    "keywords",
    "mentions",
    "overlap_score",
    "tokenize",
]

_TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    """
    a about an and any are as at be been being but by can cm compared did do does
    evidence for from had has have her his in into is it its mm no not of on or
    patient patients prior present rule ruled she seen show showed shows since so
    that the their then there these this to unchanged was we were which with
    without year years month months week weeks day days left right bilateral
    """.split()
)

_NEGATION_CUES = (
    "no evidence of",
    "no signs of",
    "no acute",
    "no",
    "not",
    "without",
    "negative for",
    "denies",
    "denied",
    "absent",
    "ruled out",
    "free of",
)

_NEGATION_WINDOW = 6

_INTERVAL_UNITS = {
    "day": 1,
    "days": 1,
    "week": 7,
    "weeks": 7,
    "month": 30,
    "months": 30,
    "year": 365,
    "years": 365,
}

_INTERVAL_RE = re.compile(
    r"(\d+)\s*[-\s]?\s*(day|days|week|weeks|month|months|year|years)", re.IGNORECASE
)


def tokenize(text: str) -> list[str]:
    """Split ``text`` into lower-case alphanumeric tokens."""

    return _TOKEN_RE.findall(text.lower())


def keywords(text: str) -> set[str]:
    """Return the meaningful tokens of ``text`` (stop words removed)."""

    return {
        token
        for token in tokenize(text)
        if len(token) > 2 and token not in STOPWORDS
    }


def overlap_score(query_terms: Iterable[str], candidate_text: str) -> float:
    """Fraction of ``query_terms`` that appear in ``candidate_text`` (0.0-1.0)."""

    query = {term for term in query_terms if term}
    if not query:
        return 0.0
    candidate = keywords(candidate_text)
    if not candidate:
        return 0.0
    return len(query & candidate) / len(query)


def mentions(text: str, term: str) -> bool:
    """True when every meaningful token of ``term`` occurs in ``text``."""

    term_tokens = keywords(term)
    if not term_tokens:
        return False
    return term_tokens <= keywords(text)


def is_negated(text: str, term: str) -> bool:
    """True when ``term`` appears in ``text`` preceded by a negation cue.

    Only the few tokens before the mention are inspected, which keeps the rule
    conservative: "no evidence of pulmonary nodule" is negated, while "nodule,
    no change in size" is not.
    """

    term_tokens = [token for token in tokenize(term) if token not in STOPWORDS]
    if not term_tokens:
        return False
    tokens = tokenize(text)
    head = term_tokens[0]
    for index, token in enumerate(tokens):
        if token != head:
            continue
        if not set(term_tokens) <= set(tokens[index : index + len(term_tokens) + 3]):
            continue
        window = " ".join(tokens[max(0, index - _NEGATION_WINDOW) : index])
        if any(_cue_in_window(window, cue) for cue in _NEGATION_CUES):
            return True
    return False


def _cue_in_window(window: str, cue: str) -> bool:
    return re.search(rf"(?:^|\s){re.escape(cue)}(?:\s|$)", window) is not None


#: Single-word concepts shorter than this are too generic to act on.
_MIN_UNIGRAM_LENGTH = 6


def concepts(phrase: str) -> list[str]:
    """Return candidate clinical concepts contained in ``phrase``.

    Contiguous two-word concepts (for example "pulmonary nodule") are returned
    before single words so that callers can prefer the most specific match.
    """

    tokens = [token for token in tokenize(phrase) if token not in STOPWORDS and len(token) > 2]
    bigrams = [f"{first} {second}" for first, second in zip(tokens, tokens[1:])]
    unigrams = [token for token in tokens if len(token) >= _MIN_UNIGRAM_LENGTH]
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in (*bigrams, *unigrams):
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def follow_up_interval_days(text: str) -> int | None:
    """Extract a follow-up interval such as "repeat CT in 6 months" in days."""

    lowered = text.lower()
    if not any(
        cue in lowered
        for cue in ("follow-up", "follow up", "followup", "repeat", "surveillance", "recheck")
    ):
        return None
    match = _INTERVAL_RE.search(lowered)
    if not match:
        return None
    amount = int(match.group(1))
    return amount * _INTERVAL_UNITS[match.group(2).lower()]
