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
from .trigger import (
    ALLOWED_PUBLISH_HOSTS,
    SEND_TO_EXTENSIONS_ACTION,
    SendToExtensionsHandler,
    handle_send_to_extensions,
)

__all__ = [
    "ALLOWED_PUBLISH_HOSTS",
    "DEFAULT_PUBLISH_URL",
    "SEND_TO_EXTENSIONS_ACTION",
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
    "SendToExtensionsHandler",
    "align_evidence",
    "detect_discrepancies",
    "handle_send_to_extensions",
]

__version__ = "0.1.0"
