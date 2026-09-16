"""Dragon Copilot clinical evidence alignment extension."""

from .alignment import EvidenceItem, align_evidence
from .discrepancies import Discrepancy, detect_discrepancies
from .extension import ClinicalEvidenceExtension, EvidenceSummary
from .models import (
    Allergy,
    ClinicalContext,
    ImagingStudy,
    Medication,
    Observation,
    PatientRecord,
    Problem,
)
from .publisher import DEFAULT_PUBLISH_URL, EvidencePublisher, PublishError

__all__ = [
    "DEFAULT_PUBLISH_URL",
    "Allergy",
    "ClinicalContext",
    "ClinicalEvidenceExtension",
    "Discrepancy",
    "EvidenceItem",
    "EvidencePublisher",
    "EvidenceSummary",
    "ImagingStudy",
    "Medication",
    "Observation",
    "PatientRecord",
    "Problem",
    "PublishError",
    "align_evidence",
    "detect_discrepancies",
]

__version__ = "0.1.0"
