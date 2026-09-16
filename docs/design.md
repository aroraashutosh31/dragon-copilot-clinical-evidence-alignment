# Design: clinical evidence alignment extension

## 1. Purpose

Dragon Copilot ambiently captures the clinical encounter. This extension adds a second
signal: while the clinician documents, it surfaces **concise, patient-specific evidence
from prior imaging and EHR data**, highlights the context that is relevant right now, and
flags **potential discrepancies** between what is being documented and what the record
already contains.

The extension is an assistive review aid. It never asserts a clinical conclusion, never
auto-edits the note, and always shows the source, date and reference of every item so the
clinician can verify it.

## 2. Scope

In scope:

* Ranking prior imaging studies, problems, medications, observations and allergies against
  the current encounter context.
* Detecting a small set of high-value, explainable discrepancies.
* Rendering a compact side-panel summary and an equivalent JSON payload.
* Publishing the summary to a review application for downstream follow-up.

Out of scope (deliberately):

* Diagnosis, triage or any autonomous clinical decision.
* Terminology servers, ML models or external NLP services — the first iteration must be
  dependency-free, deterministic and reviewable.
* Persisting patient data; the extension is stateless.

## 3. Architecture

```
host application (EHR / imaging connectors)
          │  JSON payload
          ▼
  models.PatientRecord + models.ClinicalContext
          │
          ├── alignment.align_evidence()      → ranked EvidenceItem list
          └── discrepancies.detect_discrepancies() → severity-ordered Discrepancy list
          │
          ▼
  extension.ClinicalEvidenceExtension.summarize() → EvidenceSummary
          │
          ├── EvidenceSummary.render_text()  → side panel / CLI text
          ├── EvidenceSummary.to_dict()      → JSON response to the host
          └── publisher.EvidencePublisher    → HTTPS POST to the review app
```

| Module | Responsibility |
| --- | --- |
| `models.py` | Frozen dataclasses plus tolerant `from_dict` parsing of host JSON |
| `textutils.py` | Tokenisation, keyword extraction, negation detection, follow-up interval parsing |
| `alignment.py` | Relevance scoring and ranking of prior evidence |
| `discrepancies.py` | Independent detectors, de-duplication and severity ordering |
| `extension.py` | Public entry points: `summarize()` and `handle_request()` |
| `publisher.py` | Publishing summaries to the review application |
| `cli.py` | Local/offline operation and manual verification |

## 4. Data model

`PatientRecord` aggregates `ImagingStudy`, `Problem`, `Medication`, `Observation` and
`Allergy`. `ClinicalContext` carries what the clinician is working on: reason for visit,
note text, optional focus terms and the encounter date (`as_of`).

Parsing is deliberately tolerant of host variation — ISO timestamps are truncated to a
date, laterality aliases (`Rt`, `L`, `both`) are normalised, and single strings are
accepted where lists are expected — but invalid dates and mapping values for list fields
raise `ValueError` rather than being silently coerced.

All models are frozen so a summary can be safely shared across the request lifecycle.

## 5. Evidence alignment

For every candidate item a relevance score is computed:

```
relevance = source_weight × (0.7 × context_match + 0.3 × recency)
```

* `context_match` — the fraction of the clinician's context keywords found in the item's
  text. Stop words (including generic radiology filler) are removed first.
* `recency` — linear decay over a five-year horizon (`RECENCY_HORIZON_DAYS`).
* `source_weight` — imaging outranks problems, then observations, medications, allergies.
* Abnormal observations receive a small additive boost (`ABNORMAL_OBSERVATION_BOOST`), and
  the result is clamped to 1.0 so the reported score stays in the documented 0.0–1.0 range.

Items scoring below `min_relevance` are dropped entirely — showing nothing is better than
showing noise — and the top `limit` items are returned, ties broken by recency.

A linear, inspectable formula is used instead of an embedding model because clinicians (and
reviewers of this repository) must be able to explain exactly why an item appeared.

## 6. Discrepancy detection

Each detector is an independent function over `(record, context)`; results are merged,
de-duplicated on `(kind, summary)` and sorted by severity.

| Kind | Severity | Signal |
| --- | --- | --- |
| `note_contradicts_imaging` | high | A concept reported (non-negated) on prior imaging is negated in the current note |
| `laterality_mismatch` | high | The note references one side, prior imaging of the same body site documented the other |
| `overdue_follow_up` | high | A recommendation with a parsable interval is past due and no later study of the same body site exists |
| `allergy_conflict` | high | An active medication matches a documented allergy substance |
| `medication_for_resolved_problem` | medium | An active medication's indication is a resolved problem |
| `finding_not_on_problem_list` | medium | A reported imaging finding has no matching problem list entry |

Precision is favoured over recall:

* Negation is decided from a short window of tokens *preceding* a mention, so
  "no evidence of pulmonary nodule" is negated while "nodule, no change in size" is not.
* Contradictions are evaluated at concept level (two-word phrases first, then sufficiently
  specific single words), because notes rarely repeat a radiology sentence verbatim.
* Follow-up completion is matched on body site; modality names vary between systems, so
  modality is only used when the prior study has no body site.
* A finding counts as documented when a problem list entry shares at least 60 % of its
  keywords with the finding.

## 7. Publishing

`EvidencePublisher` POSTs `EvidenceSummary.to_dict()` as JSON to a review application,
defaulting to `https://vibehub.microsoft.com/app/asharora-hathct`.

Security and privacy decisions:

* HTTPS is enforced at construction time; any other scheme raises `ValueError`, so patient
  data can never be sent over plaintext.
* The bearer token is read from the `CLINICAL_EVIDENCE_PUBLISH_TOKEN` environment variable
  (or injected by the host). No credential is ever stored in the repository or in a record
  file, and the token is only added as an `Authorization` header.
* Transport failures raise `PublishError` with the endpoint and status, never the payload,
  so patient data cannot leak into error text or logs.
* Publishing is opt-in: the library and CLI produce summaries without any network access
  unless `--publish` is passed.
* `publish()` returns `{"http_status": int, "body": ...}` so the transport status can never
  be shadowed by a field of the application's own response.

## 8. Interfaces

* Library: `ClinicalEvidenceExtension().summarize(record, context) -> EvidenceSummary`.
* Host RPC: `handle_request({"patient_record": ..., "context": ...}) -> dict`, validating
  that both members are objects.
* CLI: `python -m clinical_evidence RECORD [--reason ...] [--note ...] [--focus ...]
  [--as-of ...] [--json] [--publish [--publish-url URL]]`.

## 9. Testing strategy

`tests/` mirrors the modules and asserts behaviour, not implementation: text helpers
(including negation edge cases), ranking order and filtering, one positive **and** one
negative case per detector, JSON serialisability of the response, CLI argument handling,
and a fully mocked publisher (no network calls in the suite).

## 10. Future work

* Map findings to coded concepts (SNOMED CT / RadLex) instead of keyword overlap.
* Weight evidence by specialty using `ClinicalContext.specialty`.
* Capture clinician accept/dismiss feedback to tune detector thresholds.
* Batch or retry publishing when the review application is unavailable.
