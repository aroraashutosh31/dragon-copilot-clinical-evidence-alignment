import json
from pathlib import Path

import pytest

from clinical_evidence import (
    DEFAULT_PUBLISH_URL,
    SEND_TO_EXTENSIONS_ACTION,
    ClinicalEvidenceExtension,
    PublishError,
    SendToExtensionsHandler,
    handle_send_to_extensions,
)

EVENT_FILE = Path(__file__).resolve().parents[1] / "examples" / "send_to_extensions_event.json"


class _RecordingPublisher:
    """Stand-in for :class:`EvidencePublisher` that records what was published."""

    calls: list[tuple[str, dict]] = []
    error: Exception | None = None

    def __init__(self, url):
        self.url = url

    def publish(self, summary):
        if _RecordingPublisher.error is not None:
            raise _RecordingPublisher.error
        _RecordingPublisher.calls.append((self.url, summary))
        return {"http_status": 202, "body": {"id": "vib-1"}}


@pytest.fixture(autouse=True)
def reset_publisher():
    _RecordingPublisher.calls = []
    _RecordingPublisher.error = None
    yield


@pytest.fixture()
def event() -> dict:
    return json.loads(EVENT_FILE.read_text(encoding="utf-8"))


@pytest.fixture()
def handler() -> SendToExtensionsHandler:
    return SendToExtensionsHandler(publisher_factory=_RecordingPublisher)


def test_event_publishes_summary_to_the_app(handler, event):
    response = handler.handle(event)

    url, published = _RecordingPublisher.calls[0]
    assert url == DEFAULT_PUBLISH_URL
    assert published["patient_id"] == "demo-1042"
    assert published["discrepancies"], "expected discrepancies in the published summary"

    assert response["action"] == SEND_TO_EXTENSIONS_ACTION
    assert response["published_to"] == DEFAULT_PUBLISH_URL
    assert response["http_status"] == 202
    assert response["request_id"] == "vibehub-7f3a"
    assert response["summary"] == published
    assert json.loads(json.dumps(response)) == response


def test_app_url_defaults_when_absent(handler, event):
    event.pop("app_url")
    assert handler.handle(event)["published_to"] == DEFAULT_PUBLISH_URL


def test_request_id_is_omitted_when_absent(handler, event):
    event.pop("request_id")
    assert "request_id" not in handler.handle(event)


def test_untrusted_app_url_is_refused(handler, event):
    event["app_url"] = "https://attacker.example/collect"
    with pytest.raises(ValueError, match="untrusted host"):
        handler.handle(event)
    assert _RecordingPublisher.calls == []


def test_non_string_app_url_is_refused(handler, event):
    event["app_url"] = {"url": DEFAULT_PUBLISH_URL}
    with pytest.raises(ValueError, match="must be a string"):
        handler.handle(event)


def test_unsupported_action_is_refused(handler, event):
    event["action"] = "delete_everything"
    with pytest.raises(ValueError, match="Unsupported action"):
        handler.handle(event)
    assert _RecordingPublisher.calls == []


def test_missing_patient_record_is_refused(handler):
    with pytest.raises(ValueError, match="patient_record"):
        handler.handle({"action": SEND_TO_EXTENSIONS_ACTION})


def test_publish_errors_propagate(handler, event):
    _RecordingPublisher.error = PublishError("service unavailable")
    with pytest.raises(PublishError):
        handler.handle(event)


def test_handler_honours_extension_limits(event):
    handler = SendToExtensionsHandler(
        ClinicalEvidenceExtension(max_evidence=1, max_discrepancies=1),
        publisher_factory=_RecordingPublisher,
    )
    summary = handler.handle(event)["summary"]
    assert len(summary["evidence"]) == 1
    assert len(summary["discrepancies"]) == 1


def test_module_level_helper_delegates_to_a_handler(event, handler):
    assert handle_send_to_extensions(event, handler=handler)["http_status"] == 202
    assert _RecordingPublisher.calls[0][0] == DEFAULT_PUBLISH_URL
