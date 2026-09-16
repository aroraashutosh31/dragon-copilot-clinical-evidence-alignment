import json
from pathlib import Path

import pytest

from clinical_evidence import ClinicalEvidenceExtension, PatientRecord
from clinical_evidence.cli import main

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_encounter.json"


@pytest.fixture()
def payload() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_handle_request_returns_serialisable_summary(payload):
    result = ClinicalEvidenceExtension().handle_request(payload)

    assert result["patient_id"] == "demo-1042"
    assert json.loads(json.dumps(result)) == result
    assert result["evidence"], "expected relevant prior evidence"
    assert any(item["source"] == "imaging" for item in result["evidence"])

    kinds = {item["kind"] for item in result["discrepancies"]}
    assert "note_contradicts_imaging" in kinds
    assert "overdue_follow_up" in kinds


def test_limits_are_applied(payload):
    extension = ClinicalEvidenceExtension(max_evidence=2, max_discrepancies=1)
    result = extension.handle_request(payload)
    assert len(result["evidence"]) == 2
    assert len(result["discrepancies"]) == 1
    assert result["discrepancies"][0]["severity"] == "high"


def test_handle_request_validates_payload():
    with pytest.raises(ValueError):
        ClinicalEvidenceExtension().handle_request({})
    with pytest.raises(ValueError):
        ClinicalEvidenceExtension().handle_request({"patient_record": {}, "context": "chest"})


def test_summarize_without_context_still_works(payload):
    record = PatientRecord.from_dict(payload["patient_record"])
    summary = ClinicalEvidenceExtension().summarize(record)
    assert summary.patient_id == "demo-1042"
    assert "the current encounter" in summary.headline


def test_render_text_includes_both_sections(payload):
    summary = ClinicalEvidenceExtension().summarize(
        PatientRecord.from_dict(payload["patient_record"])
    )
    rendered = summary.render_text()
    assert "Relevant prior evidence:" in rendered
    assert "Potential discrepancies to review:" in rendered


def test_empty_record_renders_placeholders():
    summary = ClinicalEvidenceExtension().summarize(PatientRecord(patient_id="p0"))
    rendered = summary.render_text()
    assert "No prior evidence matched the current context." in rendered
    assert "None detected." in rendered


def test_cli_text_output(capsys):
    assert main([str(SAMPLE)]) == 0
    out = capsys.readouterr().out
    assert "Potential discrepancies to review:" in out
    assert "pulmonary nodule" in out


def test_cli_json_output_with_overrides(capsys):
    exit_code = main(
        [
            str(SAMPLE),
            "--json",
            "--reason",
            "knee pain",
            "--as-of",
            "2025-02-03",
            "--max-evidence",
            "3",
        ]
    )
    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["evidence"]) <= 3
    assert "knee pain" in result["headline"]
