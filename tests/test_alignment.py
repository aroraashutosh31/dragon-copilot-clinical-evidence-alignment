from datetime import date

import pytest

from clinical_evidence import (
    Allergy,
    ClinicalContext,
    ImagingStudy,
    Medication,
    Observation,
    PatientRecord,
    Problem,
    align_evidence,
)


@pytest.fixture()
def record() -> PatientRecord:
    return PatientRecord(
        patient_id="p1",
        imaging_studies=(
            ImagingStudy(
                study_id="CT1",
                modality="CT",
                body_site="chest",
                performed_on=date(2024, 4, 13),
                impression="8 mm solid pulmonary nodule in the right upper lobe.",
            ),
            ImagingStudy(
                study_id="MR1",
                modality="MRI",
                body_site="knee",
                performed_on=date(2015, 1, 5),
                impression="Medial meniscus tear.",
            ),
        ),
        problems=(Problem(name="Hypertension", onset_date=date(2019, 6, 1)),),
        medications=(Medication(name="Lisinopril", indication="Hypertension"),),
        observations=(
            Observation(
                name="Hemoglobin",
                value="10.2",
                unit="g/dL",
                observed_on=date(2025, 1, 14),
                abnormal=True,
            ),
        ),
        allergies=(Allergy(substance="Penicillin", reaction="hives"),),
    )


def test_context_match_outranks_recency(record: PatientRecord):
    context = ClinicalContext(
        reason_for_visit="pulmonary nodule follow-up", as_of=date(2025, 2, 3)
    )
    items = align_evidence(record, context)
    assert items[0].reference == "CT1"
    assert items[0].source == "imaging"
    assert "pulmonary nodule" in items[0].detail


def test_stale_unrelated_evidence_is_not_surfaced(record: PatientRecord):
    context = ClinicalContext(reason_for_visit="pulmonary nodule", as_of=date(2025, 2, 3))
    references = [item.reference for item in align_evidence(record, context)]
    assert "CT1" in references
    assert "MR1" not in references


def test_limit_and_min_relevance_are_respected(record: PatientRecord):
    context = ClinicalContext(reason_for_visit="pulmonary nodule", as_of=date(2025, 2, 3))
    assert align_evidence(record, context, limit=1) == align_evidence(record, context)[:1]
    assert align_evidence(record, context, limit=0) == []
    assert align_evidence(record, context, min_relevance=1.1) == []


def test_evidence_item_serialisation(record: PatientRecord):
    context = ClinicalContext(reason_for_visit="pulmonary nodule", as_of=date(2025, 2, 3))
    item = align_evidence(record, context)[0]
    payload = item.to_dict()
    assert payload["reference"] == "CT1"
    assert payload["occurred_on"] == "2024-04-13"
    assert 0.0 <= payload["relevance"] <= 1.0
    assert "2024-04-13" in item.render()
