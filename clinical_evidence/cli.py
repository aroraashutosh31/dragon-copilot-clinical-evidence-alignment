"""Command line interface for the clinical evidence alignment extension."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from .extension import (
    DEFAULT_MAX_DISCREPANCIES,
    DEFAULT_MAX_EVIDENCE,
    ClinicalEvidenceExtension,
)
from .models import ClinicalContext, PatientRecord
from .publisher import DEFAULT_PUBLISH_URL, EvidencePublisher, PublishError


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if number < 0:
        raise argparse.ArgumentTypeError("value must be zero or greater")
    return number


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clinical-evidence",
        description=(
            "Surface concise, patient-specific evidence from prior imaging and EHR "
            "data, highlighting relevant context and potential discrepancies."
        ),
    )
    parser.add_argument("record", help="Path to a patient record JSON file ('-' for stdin)")
    parser.add_argument("--reason", default="", help="Reason for the current visit")
    parser.add_argument("--note", default="", help="Text of the note being dictated")
    parser.add_argument(
        "--focus",
        action="append",
        default=[],
        metavar="TERM",
        help="Additional focus term (repeatable)",
    )
    parser.add_argument("--as-of", default=None, help="Encounter date (YYYY-MM-DD)")
    parser.add_argument(
        "--max-evidence",
        type=_non_negative_int,
        default=DEFAULT_MAX_EVIDENCE,
        help="Maximum evidence items",
    )
    parser.add_argument(
        "--max-discrepancies",
        type=_non_negative_int,
        default=DEFAULT_MAX_DISCREPANCIES,
        help="Maximum discrepancies",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish the evidence summary to the review application",
    )
    parser.add_argument(
        "--publish-url",
        default=DEFAULT_PUBLISH_URL,
        help=f"HTTPS endpoint to publish to (default: {DEFAULT_PUBLISH_URL})",
    )
    return parser


def _load_record(path: str) -> dict[str, Any]:
    """Load the encounter JSON, raising ``ValueError`` for unusable input."""

    try:
        if path == "-":
            data = json.load(sys.stdin)
        else:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
    except OSError as exc:
        raise ValueError(f"{path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object, got {type(data).__name__}")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        data = _load_record(args.record)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    context_data: dict[str, Any] = dict(data.get("context") or {})
    if args.reason:
        context_data["reason_for_visit"] = args.reason
    if args.note:
        context_data["note_text"] = args.note
    if args.focus:
        context_data["focus_terms"] = args.focus
    if args.as_of:
        context_data["as_of"] = args.as_of

    try:
        record = PatientRecord.from_dict(data.get("patient_record", data))
        context = ClinicalContext.from_dict(context_data)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    extension = ClinicalEvidenceExtension(
        max_evidence=args.max_evidence, max_discrepancies=args.max_discrepancies
    )
    summary = extension.summarize(record, context)

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print(summary.render_text())

    if args.publish:
        try:
            EvidencePublisher(args.publish_url).publish(summary)
        except (PublishError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Published evidence summary to {args.publish_url}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
