"""Publish evidence summaries to the Vibehub review application.

The publisher posts the JSON produced by ``ClinicalEvidenceExtension`` to an
HTTPS endpoint so the surfaced evidence and discrepancies can be reviewed
outside the dictation session.

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

#: Sentinel distinguishing "read the environment" from an explicit ``token=None``.
_UNSET = object()


class PublishError(RuntimeError):
    """Raised when an evidence summary could not be published."""


class EvidencePublisher:
    """Post evidence summaries to the configured review application."""

    def __init__(
        self,
        url: str = DEFAULT_PUBLISH_URL,
        *,
        token: str | None | Any = _UNSET,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Pass ``token=None`` to send no ``Authorization`` header at all."""

        scheme = urllib.parse.urlparse(url).scheme.lower()
        if scheme != "https":
            raise ValueError(
                f"Evidence may only be published over HTTPS, got {scheme or 'no'} scheme: {url}"
            )
        self.url = url
        self.token = os.environ.get(TOKEN_ENV_VAR) if token is _UNSET else token
        self.timeout = timeout

    def publish(self, summary: EvidenceSummary | Mapping[str, Any]) -> dict[str, Any]:
        """Publish ``summary`` and return the transport status and response body.

        The result is ``{"http_status": int, "body": ...}``; ``body`` is the parsed
        JSON response when the application returns JSON, the raw text otherwise,
        and is never merged with the transport status.
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
            body_value: Any = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body_value = raw
        return {"http_status": status, "body": body_value}
