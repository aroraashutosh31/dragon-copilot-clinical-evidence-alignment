# dragon-copilot-clinical-evidence-alignment

Dragon Copilot extension that surfaces concise, patient-specific evidence from prior
imaging and EHR data, highlighting relevant context and potential discrepancies for
clinician review.

The extension is intentionally explainable and dependency-free: every surfaced item
carries its source, date and reference so a clinician can trace why it was shown. It
flags items **for review** and never asserts a clinical conclusion on its own.

## How it works

1. **Ingest** – `PatientRecord` and `ClinicalContext` are built from the JSON the host
   application provides (prior imaging studies, problem list, medications, observations,
   allergies plus the reason for visit / note being dictated).
2. **Align** – `align_evidence()` ranks each piece of prior evidence by how well it
   matches the current context and how recent it is, returning only the top items.
3. **Compare** – `detect_discrepancies()` compares the note and the EHR against the prior
   imaging reports and returns potential inconsistencies, most severe first:

   | Kind | Example |
   | --- | --- |
   | `note_contradicts_imaging` | note documents "no pulmonary nodule" while a prior CT reported one |
   | `laterality_mismatch` | note references the right knee, prior MRI documented the left |
   | `overdue_follow_up` | "follow-up CT in 6 months" with no subsequent study |
   | `allergy_conflict` | active medication matching a documented allergy |
   | `medication_for_resolved_problem` | antibiotic still active for a resolved infection |
   | `finding_not_on_problem_list` | imaging finding never added to the problem list |

4. **Summarise** – `ClinicalEvidenceExtension.summarize()` returns an `EvidenceSummary`
   that renders as the compact side-panel text or as JSON.
5. **Publish** – `EvidencePublisher` posts the summary to the review application so the
   surfaced evidence can be followed up outside the dictation session.

See [`docs/design.md`](docs/design.md) for the full design.

## Usage

```python
from clinical_evidence import ClinicalEvidenceExtension

extension = ClinicalEvidenceExtension(max_evidence=5, max_discrepancies=5)
response = extension.handle_request({
    "patient_record": {...},
    "context": {"reason_for_visit": "pulmonary nodule follow-up", "note_text": "..."},
})
```

Command line, using the bundled example:

```console
$ python -m clinical_evidence examples/sample_encounter.json
5 prior finding(s) relevant to Follow-up of pulmonary nodule, shortness of breath; 5 potential discrepancy(ies) to review.

Relevant prior evidence:
  • Prior CT right chest (2024-04-13) — 8 mm solid pulmonary nodule in the right upper lobe. ...

Potential discrepancies to review:
  • [high] Current documentation states absence of: pulmonary nodule — CT right chest (2024-04-13) reported: ...
  • [high] Recommended follow-up imaging appears overdue (due 2024-10-10) — ...
```

Add `--json` for machine-readable output, or `--reason`, `--note`, `--focus` and
`--as-of` to override the encounter context.

## Publishing

Summaries can be published to the Vibehub review application
(`https://vibehub.microsoft.com/app/asharora-hathct` by default):

```console
$ export CLINICAL_EVIDENCE_PUBLISH_TOKEN="<token>"
$ python -m clinical_evidence examples/sample_encounter.json --publish
```

```python
from clinical_evidence import EvidencePublisher

EvidencePublisher().publish(summary)          # default endpoint
EvidencePublisher("https://example/app").publish(summary)
```

Publishing is opt-in, requires HTTPS, and reads the bearer token from the
`CLINICAL_EVIDENCE_PUBLISH_TOKEN` environment variable — no credentials are stored in the
repository or in record files.

### "Send to extensions"

When **Send to extensions** is clicked in the review application, it posts a
`send_to_extensions` event to this extension. `SendToExtensionsHandler` aligns the
evidence and publishes the summary straight back to the app:

```python
from clinical_evidence import handle_send_to_extensions

response = handle_send_to_extensions({
    "action": "send_to_extensions",
    "app_url": "https://vibehub.microsoft.com/app/asharora-hathct",
    "request_id": "vibehub-7f3a",
    "patient_record": {...},
    "context": {...},
})
# {"action": ..., "published_to": ..., "http_status": 202, "request_id": ..., "summary": {...}}
```

The event's `app_url` is only honoured when it is an `https` URL pointing at a trusted host
(`clinical_evidence.ALLOWED_PUBLISH_HOSTS`), so a crafted event cannot redirect patient
data elsewhere.

Such an event can be replayed locally — publishing is implied, no `--publish` needed:

```console
$ python -m clinical_evidence examples/send_to_extensions_event.json
```

## Development

```console
pip install -e ".[test]"
python -m pytest
```
