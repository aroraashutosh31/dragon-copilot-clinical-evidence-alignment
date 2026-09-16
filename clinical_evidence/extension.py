"""The Dragon Copilot extension entry point.

`ClinicalEvidenceExtension` turns a patient record plus the clinician's current
context into a concise, citable evidence summary and a list of potential
discrepancies to review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .alignment import EvidenceItem, align_evidence
from .discrepancies import Discrepancy, detect_discrepancies
from .models import ClinicalContext, PatientRecord

__all__ = ["ClinicalEvidenceExtension", "EvidenceSummary"]

DEFAULT_MAX_EVIDENCE = 5
DEFAULT_MAX_DISCREPANCIES = 5


@dataclass(frozen=True)
class EvidenceSummary:
    """The result surfaced to the clinician inside Dragon Copilot."""

    patient_id: str
    headline: str
    evidence: tuple[EvidenceItem, ...] = ()
    discrepancies: tuple[Discrepancy, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "patient_id": self.patient_id,
            "headline": self.headline,
            "evidence": [item.to_dict() for item in self.evidence],
            "discrepancies": [item.to_dict() for item in self.discrepancies],
        }

    def render_text(self) -> str:
        """Render the summary as the compact text shown in the side panel."""

        lines = [self.headline, "", "Relevant prior evidence:"]
        if self.evidence:
            lines.extend(f"  • {item.render()}" for item in self.evidence)
        else:
            lines.append("  • No prior evidence matched the current context.")

        lines.extend(["", "Potential discrepancies to review:"])
        if self.discrepancies:
            lines.extend(f"  • {item.render()}" for item in self.discrepancies)
        else:
            lines.append("  • None detected.")
        return "\n".join(lines)


class ClinicalEvidenceExtension:
    """Surface patient-specific evidence from prior imaging and EHR data."""

    def __init__(
        self,
        *,
        max_evidence: int = DEFAULT_MAX_EVIDENCE,
        max_discrepancies: int = DEFAULT_MAX_DISCREPANCIES,
    ) -> None:
        self.max_evidence = max_evidence
        self.max_discrepancies = max_discrepancies

    def summarize(
        self, record: PatientRecord, context: ClinicalContext | None = None
    ) -> EvidenceSummary:
        context = context or ClinicalContext()
        evidence = align_evidence(record, context, limit=self.max_evidence)
        discrepancies = detect_discrepancies(record, context, limit=self.max_discrepancies)
        return EvidenceSummary(
            patient_id=record.patient_id,
            headline=self._headline(context, len(evidence), len(discrepancies)),
            evidence=tuple(evidence),
            discrepancies=tuple(discrepancies),
        )

    def handle_request(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Handle a JSON request from the Dragon Copilot host application."""

        record_data = payload.get("patient_record")
        if not isinstance(record_data, Mapping):
            raise ValueError("payload must contain a 'patient_record' object")
        context_data = payload.get("context") or {}
        if not isinstance(context_data, Mapping):
            raise ValueError("'context' must be an object when provided")

        record = PatientRecord.from_dict(record_data)
        context = ClinicalContext.from_dict(context_data)
        return self.summarize(record, context).to_dict()

    @staticmethod
    def _headline(context: ClinicalContext, evidence_count: int, discrepancy_count: int) -> str:
        focus = context.reason_for_visit.strip() or "the current encounter"
        return (
            f"{evidence_count} prior finding(s) relevant to {focus}; "
            f"{discrepancy_count} potential discrepancy(ies) to review."
        )
