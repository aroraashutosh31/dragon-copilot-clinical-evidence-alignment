"""Handle the Vibehub "Send to extensions" action.

When a clinician clicks **Send to extensions** in the review application, the
application posts an event to this extension. The event carries the patient data
and the encounter context; the extension aligns the evidence and publishes the
resulting summary back to the application.

Event shape::

    {
      "action": "send_to_extensions",
      "app_url": "https://vibehub.microsoft.com/app/asharora-hathct",
      "request_id": "optional correlation id",
      "patient_record": {...},
      "context": {...}
    }

The ``app_url`` is optional; it defaults to
:data:`~clinical_evidence.publisher.DEFAULT_PUBLISH_URL`. Because the event
originates outside this process, a supplied ``app_url`` is only honoured when it
points at a trusted host — otherwise a crafted event could redirect patient data
to an arbitrary endpoint.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Callable, Mapping, Protocol

from .extension import ClinicalEvidenceExtension
from .publisher import DEFAULT_PUBLISH_URL, EvidencePublisher, PublishError

__all__ = [
    "ALLOWED_PUBLISH_HOSTS",
    "PublisherLike",
    "SEND_TO_EXTENSIONS_ACTION",
    "SendToExtensionsHandler",
    "handle_send_to_extensions",
]

#: The action name the review application sends when the button is clicked.
SEND_TO_EXTENSIONS_ACTION = "send_to_extensions"

#: Hosts an event is allowed to nominate as the publish target.
ALLOWED_PUBLISH_HOSTS = frozenset({urllib.parse.urlparse(DEFAULT_PUBLISH_URL).hostname or ""})


class PublisherLike(Protocol):
    """The publishing contract required by :class:`SendToExtensionsHandler`."""

    def publish(self, summary: Any) -> Mapping[str, Any]:
        ...  # pragma: no cover - structural type


class SendToExtensionsHandler:
    """Turn a "Send to extensions" event into a published evidence summary."""

    def __init__(
        self,
        extension: ClinicalEvidenceExtension | None = None,
        *,
        default_url: str = DEFAULT_PUBLISH_URL,
        publisher_factory: Callable[[str], PublisherLike] | None = None,
        allowed_hosts: frozenset[str] = ALLOWED_PUBLISH_HOSTS,
    ) -> None:
        """Configure the handler.

        ``publisher_factory`` defaults to :class:`EvidencePublisher`, resolved when
        an event is handled so hosts can substitute their own transport.
        ``default_url`` is checked against ``allowed_hosts`` just like an
        event-supplied URL, so no configuration path can send patient data to an
        unexpected destination.
        """

        self.extension = extension or ClinicalEvidenceExtension()
        self.publisher_factory = publisher_factory
        self.allowed_hosts = allowed_hosts
        self.default_url = self._check_host(default_url)

    def handle(
        self, event: Mapping[str, Any], *, summary: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Validate ``event``, publish the summary and return the outcome.

        Pass ``summary`` to reuse a summary already computed for this event and
        avoid aligning the same record twice.

        The event must declare its ``action`` explicitly; patient data is never
        transmitted on the basis of an assumed action.

        Raises ``ValueError`` for a malformed event or an untrusted ``app_url``
        and ``PublishError`` when the review application cannot be reached.
        """

        if "action" not in event:
            raise ValueError(f"Event must declare 'action': {SEND_TO_EXTENSIONS_ACTION!r}")
        action = event["action"]
        if action != SEND_TO_EXTENSIONS_ACTION:
            raise ValueError(
                f"Unsupported action {action!r}, expected {SEND_TO_EXTENSIONS_ACTION!r}"
            )

        url = self.resolve_url(event.get("app_url"))
        payload = dict(summary) if summary is not None else self.extension.handle_request(event)
        factory = self.publisher_factory or EvidencePublisher
        result = factory(url).publish(payload)
        if "http_status" not in result:
            raise PublishError(f"Publisher returned no 'http_status' for {url}")

        response: dict[str, Any] = {
            "action": SEND_TO_EXTENSIONS_ACTION,
            "published_to": url,
            "http_status": result["http_status"],
            "summary": payload,
        }
        request_id = event.get("request_id")
        if request_id is not None:
            response["request_id"] = request_id
        return response

    def resolve_url(self, app_url: Any = None) -> str:
        """Return the publish target, rejecting untrusted event-supplied URLs."""

        if app_url is None or app_url == "":
            return self.default_url
        if not isinstance(app_url, str):
            raise ValueError("'app_url' must be a string when provided")
        return self._check_host(app_url)

    def _check_host(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise ValueError(
                "Refusing to publish patient evidence over "
                f"{parsed.scheme or 'an unspecified'} scheme, https is required: {url}"
            )
        host = parsed.hostname
        if not host:
            raise ValueError(f"Publish URL has no host: {url!r}")
        if host not in self.allowed_hosts:
            raise ValueError(
                f"Refusing to publish patient evidence to untrusted host {host!r}: {url}"
            )
        return url


def handle_send_to_extensions(
    event: Mapping[str, Any], *, handler: SendToExtensionsHandler | None = None
) -> dict[str, Any]:
    """Convenience wrapper around :class:`SendToExtensionsHandler`."""

    return (handler or SendToExtensionsHandler()).handle(event)
