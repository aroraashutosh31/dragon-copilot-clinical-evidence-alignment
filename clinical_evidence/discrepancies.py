"""Detect potential discrepancies between prior evidence and the current note.

Every detector is conservative and explainable: the extension flags items *for
clinician review* and never asserts a clinical conclusion on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .models import ClinicalContext, ImagingStudy, PatientRecord
from .textutils import (
    concepts,
    follow_up_interval_days,
    is_negated,
    keywords,
    mentions,
)

__all__ = ["Discrepancy", "detect_discrepancies"]

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_SENTENCE_SPLIT_RE = re.compile(r"[.;\n]|(?<!\d)\d+[.)]\s")

_LATERALITY_RE = re.compile(r"\b(left|right|bilateral)\b")

#: A candidate finding must share at least this fraction of its keywords with a
#: problem list entry to be considered already documented.
_MATCH_THRESHOLD = 0.6


@dataclass(frozen=True)
class Discrepancy:
    """A potential inconsistency surfaced for clinician review."""

    kind: str
    severity: str
    summary: str
    detail: str = ""
    references: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "summary": self.summary,
            "detail": self.detail,
            "references": list(self.references),
        }

    def render(self) -> str:
        detail = f" — {self.detail}" if self.detail else ""
        return f"[{self.severity}] {self.summary}{detail}"


def _phrases(study: ImagingStudy) -> tuple[str, ...]:
    raw = [study.impression, *study.findings]
    phrases: list[str] = []
    for chunk in raw:
        for part in _SENTENCE_SPLIT_RE.split(chunk or ""):
            phrase = " ".join(part.split())
            if not phrase:
                continue
            tokens = keywords(phrase)
            if not tokens or len(phrase.split()) > 14:
                continue
            phrases.append(phrase)
    return tuple(phrases)


def _problem_keyword_sets(record: PatientRecord) -> list[set[str]]:
    """Tokenise each problem name once per detection run."""

    return [terms for terms in (keywords(p.name) for p in record.problems) if terms]


def _documented_in_problem_list(phrase: str, problem_keyword_sets: list[set[str]]) -> bool:
    phrase_terms = keywords(phrase)
    if not phrase_terms:
        return True
    for problem_terms in problem_keyword_sets:
        shared = len(problem_terms & phrase_terms) / len(problem_terms)
        if shared >= _MATCH_THRESHOLD:
            return True
    return False


def _unaddressed_findings(record: PatientRecord, context: ClinicalContext) -> list[Discrepancy]:
    found: list[Discrepancy] = []
    problem_keyword_sets = _problem_keyword_sets(record)
    for study in record.imaging_studies:
        for phrase in _phrases(study):
            if is_negated(study.text, phrase):
                continue
            if follow_up_interval_days(phrase) is not None:
                continue
            if _documented_in_problem_list(phrase, problem_keyword_sets):
                continue
            found.append(
                Discrepancy(
                    kind="finding_not_on_problem_list",
                    severity="medium",
                    summary=f"Imaging finding not reflected on the problem list: {phrase}",
                    detail=f"Reported on {study.label} ({_when(study.performed_on)}).",
                    references=(study.study_id or study.label,),
                )
            )
    return found


def _note_contradictions(record: PatientRecord, context: ClinicalContext) -> list[Discrepancy]:
    note = context.text
    if not note:
        return []
    found: list[Discrepancy] = []
    for study in record.imaging_studies:
        for phrase in _phrases(study):
            if is_negated(study.text, phrase):
                continue
            concept = _contradicted_concept(note, study, phrase)
            if concept is None:
                continue
            found.append(
                Discrepancy(
                    kind="note_contradicts_imaging",
                    severity="high",
                    summary=f"Current documentation states absence of: {concept}",
                    detail=(
                        f"{study.label} ({_when(study.performed_on)}) reported: {phrase}."
                    ),
                    references=(study.study_id or study.label,),
                )
            )
    return found


def _contradicted_concept(note: str, study: ImagingStudy, phrase: str) -> str | None:
    """Return the concept of ``phrase`` that the note negates, if any."""

    for concept in concepts(phrase):
        if not mentions(note, concept):
            continue
        if is_negated(study.text, concept):
            continue
        if is_negated(note, concept):
            return concept
    return None


def _laterality_conflicts(record: PatientRecord, context: ClinicalContext) -> list[Discrepancy]:
    note_sides = set(_LATERALITY_RE.findall(context.text.lower()))
    note_sides.discard("bilateral")
    if len(note_sides) != 1:
        return []
    note_side = note_sides.pop()
    found: list[Discrepancy] = []
    for study in record.imaging_studies:
        if not study.laterality or study.laterality == "bilateral":
            continue
        if study.laterality == note_side:
            continue
        if not (study.body_site and mentions(context.text, study.body_site)):
            continue
        found.append(
            Discrepancy(
                kind="laterality_mismatch",
                severity="high",
                summary=(
                    f"Documentation references the {note_side} {study.body_site}, "
                    f"prior imaging documented the {study.laterality} side"
                ),
                detail=f"{study.label} ({_when(study.performed_on)}).",
                references=(study.study_id or study.label,),
            )
        )
    return found


def _overdue_follow_ups(record: PatientRecord, context: ClinicalContext) -> list[Discrepancy]:
    as_of = context.as_of or date.today()
    found: list[Discrepancy] = []
    for study in record.imaging_studies:
        if study.performed_on is None:
            continue
        for recommendation in study.recommendations:
            interval = follow_up_interval_days(recommendation)
            if interval is None:
                continue
            due_on = study.performed_on + timedelta(days=interval)
            if due_on > as_of:
                continue
            if _has_later_study(record, study):
                continue
            found.append(
                Discrepancy(
                    kind="overdue_follow_up",
                    severity="high",
                    summary=(
                        f"Recommended follow-up imaging appears overdue (due {due_on.isoformat()})"
                    ),
                    detail=f"{study.label} ({_when(study.performed_on)}): {recommendation}",
                    references=(study.study_id or study.label,),
                )
            )
    return found


def _has_later_study(record: PatientRecord, study: ImagingStudy) -> bool:
    """True when a later study plausibly satisfies ``study``'s recommendation.

    Body site drives the match because modality names vary between systems and a
    later study of the same site is what a clinician needs to review; modality is
    only used when the prior study has no body site recorded.
    """

    for other in record.imaging_studies:
        if other is study or other.performed_on is None:
            continue
        if other.performed_on <= study.performed_on:
            continue
        if study.body_site:
            if keywords(other.body_site) & keywords(study.body_site):
                return True
        elif other.modality.lower() == study.modality.lower():
            return True
    return False


def _allergy_conflicts(record: PatientRecord, context: ClinicalContext) -> list[Discrepancy]:
    found: list[Discrepancy] = []
    for allergy in record.allergies:
        substance = keywords(allergy.substance)
        if not substance:
            continue
        for medication in record.active_medications():
            if not substance <= keywords(medication.name):
                continue
            found.append(
                Discrepancy(
                    kind="allergy_conflict",
                    severity="high",
                    summary=(
                        f"Active medication {medication.name} conflicts with documented "
                        f"allergy to {allergy.substance}"
                    ),
                    detail=allergy.reaction or "reaction not documented",
                    references=(medication.name, allergy.substance),
                )
            )
    return found


def _resolved_problem_medications(
    record: PatientRecord, context: ClinicalContext
) -> list[Discrepancy]:
    found: list[Discrepancy] = []
    resolved = [problem for problem in record.problems if not problem.is_active]
    for medication in record.active_medications():
        if not medication.indication:
            continue
        for problem in resolved:
            if not mentions(medication.indication, problem.name):
                continue
            found.append(
                Discrepancy(
                    kind="medication_for_resolved_problem",
                    severity="medium",
                    summary=(
                        f"{medication.name} remains active for {problem.name}, which is "
                        f"documented as {problem.status}"
                    ),
                    detail="Confirm whether the medication should be continued.",
                    references=(medication.name, problem.code or problem.name),
                )
            )
    return found


def _when(value: date | None) -> str:
    return value.isoformat() if value else "date unknown"


_DETECTORS = (
    _note_contradictions,
    _laterality_conflicts,
    _overdue_follow_ups,
    _allergy_conflicts,
    _resolved_problem_medications,
    _unaddressed_findings,
)


def detect_discrepancies(
    record: PatientRecord, context: ClinicalContext, *, limit: int | None = None
) -> list[Discrepancy]:
    """Return potential discrepancies, most severe first."""

    results: list[Discrepancy] = []
    seen: set[tuple[str, str]] = set()
    for detector in _DETECTORS:
        for discrepancy in detector(record, context):
            key = (discrepancy.kind, discrepancy.summary)
            if key in seen:
                continue
            seen.add(key)
            results.append(discrepancy)

    results.sort(key=lambda item: (SEVERITY_ORDER.get(item.severity, 3), item.summary))
    if limit is not None:
        return results[:limit]
    return results
