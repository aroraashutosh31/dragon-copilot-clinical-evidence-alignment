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

__all__ = [
    "Allergy",
    "ClinicalContext",
    "ClinicalEvidenceExtension",
    "Discrepancy",
    "EvidenceItem",
    "EvidenceSummary",
    "ImagingStudy",
    "Medication",
    "Observation",
    "PatientRecord",
    "Problem",
    "align_evidence",
    "detect_discrepancies",
]

__version__ = "0.1.0"
