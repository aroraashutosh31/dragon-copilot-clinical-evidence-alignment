"""Data models for the patient data consumed by the extension.

Dragon Copilot receives patient data as JSON from the host application (EHR and
imaging archive connectors), so every model knows how to build itself from a
plain dictionary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping

__all__ = [
    "Allergy",
    "ClinicalContext",
    "ImagingStudy",
    "Medication",
    "Observation",
    "PatientRecord",
    "Problem",
]


def _parse_date(value: Any, field_name: str) -> date | None:
    """Parse an ISO-8601 date, tolerating ``None`` and ``date`` instances."""

    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError as exc:
            raise ValueError(f"Invalid date for {field_name!r}: {value!r}") from exc
    raise ValueError(f"Invalid date for {field_name!r}: {value!r}")


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (bytes, bytearray, Mapping)):
        raise ValueError(f"Expected a string or list of strings, got {value!r}")
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value)
    raise ValueError(f"Expected a string or list of strings, got {value!r}")


_LATERALITY_ALIASES = {
    "l": "left",
    "lt": "left",
    "left": "left",
    "r": "right",
    "rt": "right",
    "right": "right",
    "both": "bilateral",
    "bilateral": "bilateral",
}


def _normalise_laterality(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    return _LATERALITY_ALIASES.get(text, text)


@dataclass(frozen=True)
class ImagingStudy:
    """A prior imaging study together with its radiology report content."""

    study_id: str
    modality: str = ""
    body_site: str = ""
    performed_on: date | None = None
    impression: str = ""
    findings: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    laterality: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ImagingStudy":
        return cls(
            study_id=str(data.get("study_id") or data.get("id") or ""),
            modality=str(data.get("modality", "")),
            body_site=str(data.get("body_site", "")),
            performed_on=_parse_date(data.get("performed_on"), "performed_on"),
            impression=str(data.get("impression", "")),
            findings=_as_tuple(data.get("findings")),
            recommendations=_as_tuple(data.get("recommendations")),
            laterality=_normalise_laterality(data.get("laterality")),
        )

    @property
    def label(self) -> str:
        parts = [p for p in (self.modality, self.laterality, self.body_site) if p]
        return " ".join(parts) if parts else (self.study_id or "imaging study")

    @property
    def text(self) -> str:
        return " ".join((self.impression, *self.findings, *self.recommendations)).strip()


@dataclass(frozen=True)
class Problem:
    """An entry on the patient's problem list."""

    name: str
    status: str = "active"
    onset_date: date | None = None
    laterality: str | None = None
    code: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Problem":
        return cls(
            name=str(data.get("name", "")),
            status=str(data.get("status", "active")).strip().lower() or "active",
            onset_date=_parse_date(data.get("onset_date"), "onset_date"),
            laterality=_normalise_laterality(data.get("laterality")),
            code=(str(data["code"]) if data.get("code") else None),
        )

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True)
class Medication:
    """A medication order from the EHR."""

    name: str
    status: str = "active"
    started_on: date | None = None
    indication: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Medication":
        return cls(
            name=str(data.get("name", "")),
            status=str(data.get("status", "active")).strip().lower() or "active",
            started_on=_parse_date(data.get("started_on"), "started_on"),
            indication=(str(data["indication"]) if data.get("indication") else None),
        )

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True)
class Observation:
    """A lab result or vital sign."""

    name: str
    value: str = ""
    unit: str | None = None
    observed_on: date | None = None
    abnormal: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Observation":
        return cls(
            name=str(data.get("name", "")),
            value=str(data.get("value", "")),
            unit=(str(data["unit"]) if data.get("unit") else None),
            observed_on=_parse_date(data.get("observed_on"), "observed_on"),
            abnormal=bool(data.get("abnormal", False)),
        )

    @property
    def display_value(self) -> str:
        return f"{self.value} {self.unit}".strip() if self.unit else self.value


@dataclass(frozen=True)
class Allergy:
    """A documented allergy or intolerance."""

    substance: str
    reaction: str | None = None
    severity: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Allergy":
        return cls(
            substance=str(data.get("substance", "")),
            reaction=(str(data["reaction"]) if data.get("reaction") else None),
            severity=(str(data["severity"]) if data.get("severity") else None),
        )


@dataclass(frozen=True)
class PatientRecord:
    """Prior imaging plus the EHR data needed to align evidence."""

    patient_id: str = ""
    imaging_studies: tuple[ImagingStudy, ...] = ()
    problems: tuple[Problem, ...] = ()
    medications: tuple[Medication, ...] = ()
    observations: tuple[Observation, ...] = ()
    allergies: tuple[Allergy, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PatientRecord":
        def build(key: str, model: Any) -> tuple[Any, ...]:
            return tuple(model.from_dict(item) for item in data.get(key) or ())

        return cls(
            patient_id=str(data.get("patient_id", "")),
            imaging_studies=build("imaging_studies", ImagingStudy),
            problems=build("problems", Problem),
            medications=build("medications", Medication),
            observations=build("observations", Observation),
            allergies=build("allergies", Allergy),
        )

    def active_problems(self) -> tuple[Problem, ...]:
        return tuple(problem for problem in self.problems if problem.is_active)

    def active_medications(self) -> tuple[Medication, ...]:
        return tuple(med for med in self.medications if med.is_active)


@dataclass(frozen=True)
class ClinicalContext:
    """What the clinician is working on during the current encounter."""

    reason_for_visit: str = ""
    note_text: str = ""
    focus_terms: tuple[str, ...] = ()
    as_of: date | None = None
    specialty: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ClinicalContext":
        return cls(
            reason_for_visit=str(data.get("reason_for_visit", "")),
            note_text=str(data.get("note_text", "")),
            focus_terms=_as_tuple(data.get("focus_terms")),
            as_of=_parse_date(data.get("as_of"), "as_of"),
            specialty=(str(data["specialty"]) if data.get("specialty") else None),
        )

    @property
    def text(self) -> str:
        return " ".join(
            part
            for part in (self.reason_for_visit, self.note_text, *self.focus_terms)
            if part
        ).strip()
