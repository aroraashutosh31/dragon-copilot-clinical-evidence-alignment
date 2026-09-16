import json
from pathlib import Path

import pytest

from clinical_evidence import (
    DEFAULT_PUBLISH_URL,
    ClinicalEvidenceExtension,
    PatientRecord,
    PublishError,
)
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


def test_cli_rejects_negative_limits():
    with pytest.raises(SystemExit):
        main([str(SAMPLE), "--max-evidence", "-1"])


def test_cli_publishes_summary(monkeypatch, capsys):
    published = {}

    class FakePublisher:
        def __init__(self, url):
            published["url"] = url

        def publish(self, summary):
            published["patient_id"] = summary.patient_id
            return {"http_status": 202, "body": {}}

    monkeypatch.setattr("clinical_evidence.cli.EvidencePublisher", FakePublisher)
    assert main([str(SAMPLE), "--publish"]) == 0
    assert published["url"] == DEFAULT_PUBLISH_URL
    assert published["patient_id"] == "demo-1042"
    err = capsys.readouterr().err
    assert "Published evidence summary" in err
    assert "HTTP 202" in err


def test_cli_reports_publish_failures(monkeypatch, capsys):
    class FailingPublisher:
        def __init__(self, url):
            pass

        def publish(self, summary):
            raise PublishError("boom")

    monkeypatch.setattr("clinical_evidence.cli.EvidencePublisher", FailingPublisher)
    assert main([str(SAMPLE), "--publish"]) == 1
    assert "error: boom" in capsys.readouterr().err


def test_cli_rejects_non_object_json(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    assert main([str(bad)]) == 1
    assert "expected a JSON object" in capsys.readouterr().err


def test_cli_reports_unreadable_and_invalid_json(tmp_path, capsys):
    assert main([str(tmp_path / "missing.json")]) == 1
    assert "error:" in capsys.readouterr().err

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert main([str(broken)]) == 1
    assert "invalid JSON" in capsys.readouterr().err


def test_cli_reports_malformed_dates(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"patient_record": {"problems": [{"name": "x", "onset_date": "13/04/2024"}]}}),
        encoding="utf-8",
    )
    assert main([str(bad)]) == 1
    assert "error:" in capsys.readouterr().err


EVENT = Path(__file__).resolve().parents[1] / "examples" / "send_to_extensions_event.json"


def test_cli_publishes_automatically_for_send_to_extensions_events(monkeypatch, capsys):
    published = {}

    class FakePublisher:
        def __init__(self, url):
            published["url"] = url

        def publish(self, summary):
            published["patient_id"] = summary.patient_id
            return {"http_status": 202, "body": {}}

    monkeypatch.setattr("clinical_evidence.cli.EvidencePublisher", FakePublisher)
    assert main([str(EVENT)]) == 0
    assert published["url"] == DEFAULT_PUBLISH_URL
    assert published["patient_id"] == "demo-1042"
    assert "HTTP 202" in capsys.readouterr().err


def test_cli_refuses_untrusted_app_url(tmp_path, capsys):
    event = json.loads(EVENT.read_text(encoding="utf-8"))
    event["app_url"] = "https://attacker.example/collect"
    path = tmp_path / "event.json"
    path.write_text(json.dumps(event), encoding="utf-8")

    assert main([str(path)]) == 1
    assert "untrusted host" in capsys.readouterr().err
