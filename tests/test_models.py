from datetime import date

import pytest

from clinical_evidence import ClinicalContext, PatientRecord
from clinical_evidence.models import ImagingStudy


def test_patient_record_from_dict_parses_nested_data():
    record = PatientRecord.from_dict(
        {
            "patient_id": "p1",
            "imaging_studies": [
                {
                    "id": "CT1",
                    "modality": "CT",
                    "body_site": "chest",
                    "laterality": "Rt",
                    "performed_on": "2024-04-13T09:00:00Z",
                    "impression": "Nodule",
                    "findings": "No effusion",
                    "recommendations": ["Follow-up in 6 months"],
                }
            ],
            "problems": [{"name": "Hypertension", "status": "Active", "code": "I10"}],
            "medications": [{"name": "Lisinopril", "status": "stopped"}],
            "observations": [{"name": "Hemoglobin", "value": 10.2, "unit": "g/dL", "abnormal": True}],
            "allergies": [{"substance": "Penicillin"}],
        }
    )

    study = record.imaging_studies[0]
    assert study.study_id == "CT1"
    assert study.laterality == "right"
    assert study.performed_on == date(2024, 4, 13)
    assert study.findings == ("No effusion",)
    assert study.label == "CT right chest"
    assert record.active_problems()[0].code == "I10"
    assert record.active_medications() == ()
    assert record.observations[0].display_value == "10.2 g/dL"
    assert record.allergies[0].reaction is None


def test_missing_sections_default_to_empty():
    record = PatientRecord.from_dict({"patient_id": "p2"})
    assert record.imaging_studies == ()
    assert record.problems == ()


def test_invalid_date_raises_value_error():
    with pytest.raises(ValueError):
        PatientRecord.from_dict({"imaging_studies": [{"id": "x", "performed_on": "13/04/2024"}]})


def test_imaging_study_label_falls_back_to_id():
    assert ImagingStudy(study_id="CT1").label == "CT1"


def test_clinical_context_text_combines_all_inputs():
    context = ClinicalContext.from_dict(
        {
            "reason_for_visit": "nodule follow-up",
            "note_text": "chest discomfort",
            "focus_terms": ["smoking history"],
            "as_of": "2025-02-03",
        }
    )
    assert context.as_of == date(2025, 2, 3)
    assert context.text == "nodule follow-up chest discomfort smoking history"
