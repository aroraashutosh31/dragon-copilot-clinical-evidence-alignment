"""Align prior imaging and EHR data with the current clinical context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .models import ClinicalContext, PatientRecord
from .textutils import keywords, overlap_score

__all__ = ["EvidenceItem", "align_evidence"]

#: Evidence older than this contributes no recency bonus.
RECENCY_HORIZON_DAYS = 5 * 365

_SOURCE_WEIGHT = {
    "imaging": 1.0,
    "problem": 0.9,
    "observation": 0.85,
    "medication": 0.8,
    "allergy": 0.8,
}

#: Abnormal results are worth surfacing even when they match the context weakly.
ABNORMAL_OBSERVATION_BOOST = 0.1


@dataclass(frozen=True)
class EvidenceItem:
    """A single, citable piece of patient-specific evidence."""

    source: str
    title: str
    detail: str
    reference: str
    occurred_on: date | None = None
    relevance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "title": self.title,
            "detail": self.detail,
            "reference": self.reference,
            "occurred_on": self.occurred_on.isoformat() if self.occurred_on else None,
            "relevance": round(self.relevance, 3),
        }

    def render(self) -> str:
        when = self.occurred_on.isoformat() if self.occurred_on else "date unknown"
        detail = f" — {self.detail}" if self.detail else ""
        return f"{self.title} ({when}){detail}"


def _recency_score(occurred_on: date | None, as_of: date) -> float:
    if occurred_on is None:
        return 0.0
    age_days = (as_of - occurred_on).days
    if age_days < 0:
        return 1.0
    return max(0.0, 1.0 - age_days / RECENCY_HORIZON_DAYS)


def _score(source: str, text: str, occurred_on: date | None, context_terms: set[str], as_of: date) -> float:
    match = overlap_score(context_terms, text)
    recency = _recency_score(occurred_on, as_of)
    weight = _SOURCE_WEIGHT.get(source, 0.7)
    return weight * (0.7 * match + 0.3 * recency)


def _summarise(text: str, limit: int = 180) -> str:
    condensed = " ".join(text.split())
    if len(condensed) <= limit:
        return condensed
    return condensed[: limit - 1].rstrip() + "…"


def align_evidence(
    record: PatientRecord,
    context: ClinicalContext,
    *,
    limit: int = 6,
    min_relevance: float = 0.05,
) -> list[EvidenceItem]:
    """Return the most relevant evidence for ``context``, highest score first.

    Items are ranked on how well they match the clinician's current context and
    how recent they are; ties are broken by recency so the freshest evidence is
    presented first.
    """

    if limit <= 0:
        return []

    as_of = context.as_of or date.today()
    context_terms = keywords(context.text)
    items: list[EvidenceItem] = []

    for study in record.imaging_studies:
        detail = _summarise(study.impression or " ".join(study.findings))
        items.append(
            EvidenceItem(
                source="imaging",
                title=f"Prior {study.label}".strip(),
                detail=detail,
                reference=study.study_id or study.label,
                occurred_on=study.performed_on,
                relevance=_score("imaging", f"{study.label} {study.text}", study.performed_on, context_terms, as_of),
            )
        )

    for problem in record.problems:
        status = "active" if problem.is_active else problem.status
        items.append(
            EvidenceItem(
                source="problem",
                title=f"Problem list: {problem.name}",
                detail=f"{status}",
                reference=problem.code or problem.name,
                occurred_on=problem.onset_date,
                relevance=_score(
                    "problem",
                    f"{problem.name} {problem.laterality or ''}",
                    problem.onset_date,
                    context_terms,
                    as_of,
                ),
            )
        )

    for medication in record.medications:
        indication = f" for {medication.indication}" if medication.indication else ""
        items.append(
            EvidenceItem(
                source="medication",
                title=f"Medication: {medication.name}",
                detail=f"{medication.status}{indication}",
                reference=medication.name,
                occurred_on=medication.started_on,
                relevance=_score(
                    "medication",
                    f"{medication.name} {medication.indication or ''}",
                    medication.started_on,
                    context_terms,
                    as_of,
                ),
            )
        )

    for observation in record.observations:
        flag = " (abnormal)" if observation.abnormal else ""
        base = _score(
            "observation",
            observation.name,
            observation.observed_on,
            context_terms,
            as_of,
        )
        items.append(
            EvidenceItem(
                source="observation",
                title=f"{observation.name}: {observation.display_value}{flag}",
                detail="abnormal result" if observation.abnormal else "within expected range",
                reference=observation.name,
                occurred_on=observation.observed_on,
                relevance=min(
                    1.0, base + (ABNORMAL_OBSERVATION_BOOST if observation.abnormal else 0.0)
                ),
            )
        )

    for allergy in record.allergies:
        detail = allergy.reaction or "reaction not documented"
        items.append(
            EvidenceItem(
                source="allergy",
                title=f"Allergy: {allergy.substance}",
                detail=detail,
                reference=allergy.substance,
                occurred_on=None,
                relevance=_score(
                    "allergy",
                    f"{allergy.substance} {allergy.reaction or ''}",
                    None,
                    context_terms,
                    as_of,
                ),
            )
        )

    ranked = sorted(
        (item for item in items if item.relevance >= min_relevance),
        key=lambda item: (-item.relevance, -(item.occurred_on or date.min).toordinal(), item.title),
    )
    return ranked[:limit]
