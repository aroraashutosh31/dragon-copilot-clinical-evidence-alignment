import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from clinical_evidence import (
    ClinicalEvidenceExtension,
    EvidencePublisher,
    PatientRecord,
    PublishError,
)
from clinical_evidence import publisher as publisher_module
from clinical_evidence.publisher import DEFAULT_PUBLISH_URL, TOKEN_ENV_VAR


class _FakeResponse:
    def __init__(self, body: bytes = b"{}", status: int = 200) -> None:
        self._body = BytesIO(body)
        self.status = status

    def read(self) -> bytes:
        return self._body.read()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


@pytest.fixture()
def summary():
    return ClinicalEvidenceExtension().summarize(PatientRecord(patient_id="p1"))


def _capture(monkeypatch, response: _FakeResponse | Exception):
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["request"] = request
        sent["timeout"] = timeout
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(publisher_module.urllib.request, "urlopen", fake_urlopen)
    return sent


def test_default_url_targets_the_review_application():
    assert DEFAULT_PUBLISH_URL == "https://vibehub.microsoft.com/app/asharora-hathct"
    assert EvidencePublisher().url == DEFAULT_PUBLISH_URL


def test_publish_posts_summary_json(monkeypatch, summary):
    monkeypatch.delenv(TOKEN_ENV_VAR, raising=False)
    sent = _capture(monkeypatch, _FakeResponse(b'{"id": "abc"}', 201))

    result = EvidencePublisher().publish(summary)

    request = sent["request"]
    assert request.full_url == DEFAULT_PUBLISH_URL
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data.decode("utf-8")) == summary.to_dict()
    assert request.get_header("Authorization") is None
    assert result == {"http_status": 201, "body": {"id": "abc"}}


def test_token_from_environment_is_sent_as_bearer(monkeypatch, summary):
    monkeypatch.setenv(TOKEN_ENV_VAR, "s3cret")
    sent = _capture(monkeypatch, _FakeResponse())

    EvidencePublisher().publish(summary)

    assert sent["request"].get_header("Authorization") == "Bearer " + "s3cret"


def test_mapping_payloads_are_accepted(monkeypatch):
    sent = _capture(monkeypatch, _FakeResponse())
    EvidencePublisher(token=None).publish({"patient_id": "p9"})
    assert json.loads(sent["request"].data.decode("utf-8")) == {"patient_id": "p9"}


def test_server_http_status_field_is_not_shadowed(monkeypatch, summary):
    _capture(monkeypatch, _FakeResponse(b'{"http_status": "queued"}', 202))
    result = EvidencePublisher(token=None).publish(summary)
    assert result["http_status"] == 202
    assert result["body"] == {"http_status": "queued"}


def test_non_json_response_is_returned_verbatim(monkeypatch, summary):
    _capture(monkeypatch, _FakeResponse(b"accepted"))
    assert EvidencePublisher(token=None).publish(summary) == {
        "http_status": 200,
        "body": "accepted",
    }


def test_non_https_urls_are_rejected():
    with pytest.raises(ValueError):
        EvidencePublisher("http://vibehub.microsoft.com/app/asharora-hathct")


def test_http_and_network_errors_raise_publish_error(monkeypatch, summary):
    _capture(
        monkeypatch,
        HTTPError(DEFAULT_PUBLISH_URL, 503, "Service Unavailable", {}, None),
    )
    with pytest.raises(PublishError, match="HTTP 503"):
        EvidencePublisher(token=None).publish(summary)

    _capture(monkeypatch, URLError("connection refused"))
    with pytest.raises(PublishError, match="connection refused"):
        EvidencePublisher(token=None).publish(summary)
