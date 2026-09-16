"""Publish evidence summaries to the Vibehub review application.

The publisher posts the JSON produced by :class:`~clinical_evidence.extension.
ClinicalEvidenceExtension` to an HTTPS endpoint so the surfaced evidence and
discrepancies can be reviewed outside the dictation session.

Credentials are never stored in code: the bearer token is read from the
``CLINICAL_EVIDENCE_PUBLISH_TOKEN`` environment variable (or passed explicitly by
the host application).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping

from .extension import EvidenceSummary

__all__ = ["DEFAULT_PUBLISH_URL", "EvidencePublisher", "PublishError", "TOKEN_ENV_VAR"]

#: Default Vibehub application that receives published evidence summaries.
DEFAULT_PUBLISH_URL = "https://vibehub.microsoft.com/app/asharora-hathct"

TOKEN_ENV_VAR = "CLINICAL_EVIDENCE_PUBLISH_TOKEN"

DEFAULT_TIMEOUT_SECONDS = 15.0


class PublishError(RuntimeError):
    """Raised when an evidence summary could not be published."""


class EvidencePublisher:
    """Post evidence summaries to the configured review application."""

    def __init__(
        self,
        url: str = DEFAULT_PUBLISH_URL,
        *,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme != "https":
            raise ValueError("Evidence may only be published over HTTPS")
        self.url = url
        self.token = token if token is not None else os.environ.get(TOKEN_ENV_VAR)
        self.timeout = timeout

    def publish(self, summary: EvidenceSummary | Mapping[str, Any]) -> dict[str, Any]:
        """Publish ``summary`` and return the parsed response body.

        The response is returned as a dictionary; a non-JSON response body is
        reported under the ``"response"`` key and the transport status is always
        available under ``"http_status"``.
        """

        payload = summary.to_dict() if isinstance(summary, EvidenceSummary) else dict(summary)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        if self.token:
            request.add_header("Authorization", "Bearer " + self.token)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            raise PublishError(
                f"Publishing to {self.url} failed with HTTP {exc.code}"
            ) from exc
        except urllib.error.URLError as exc:
            raise PublishError(f"Publishing to {self.url} failed: {exc.reason}") from exc

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"response": raw}
        if not isinstance(parsed, dict):
            parsed = {"response": parsed}
        parsed["http_status"] = status
        return parsed
