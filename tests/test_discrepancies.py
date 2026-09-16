from datetime import date

from clinical_evidence import (
    Allergy,
    ClinicalContext,
    ImagingStudy,
    Medication,
    PatientRecord,
    Problem,
    detect_discrepancies,
)


def kinds(discrepancies):
    return {item.kind for item in discrepancies}


def test_note_contradicting_prior_imaging_is_flagged():
    record = PatientRecord(
        imaging_studies=(
            ImagingStudy(
                study_id="CT1",
                modality="CT",
                body_site="chest",
                performed_on=date(2024, 4, 13),
                impression="8 mm solid pulmonary nodule in the right upper lobe.",
            ),
        ),
        problems=(Problem(name="Pulmonary nodule"),),
    )
    context = ClinicalContext(
        note_text="No pulmonary nodule on prior imaging.", as_of=date(2025, 2, 3)
    )
    results = detect_discrepancies(record, context)
    assert "note_contradicts_imaging" in kinds(results)
    flagged = next(item for item in results if item.kind == "note_contradicts_imaging")
    assert flagged.severity == "high"
    assert flagged.references == ("CT1",)


def test_negated_imaging_finding_is_not_treated_as_contradiction():
    record = PatientRecord(
        imaging_studies=(
            ImagingStudy(
                study_id="CT1",
                modality="CT",
                body_site="chest",
                performed_on=date(2024, 4, 13),
                impression="No pulmonary nodule identified.",
            ),
        ),
    )
    context = ClinicalContext(note_text="No pulmonary nodule.", as_of=date(2025, 2, 3))
    assert "note_contradicts_imaging" not in kinds(detect_discrepancies(record, context))


def test_finding_missing_from_problem_list_is_flagged():
    record = PatientRecord(
        imaging_studies=(
            ImagingStudy(
                study_id="CT1",
                modality="CT",
                body_site="chest",
                performed_on=date(2024, 4, 13),
                impression="Mild coronary artery calcification.",
            ),
        ),
        problems=(Problem(name="Hypertension"),),
    )
    results = detect_discrepancies(record, ClinicalContext(as_of=date(2025, 2, 3)))
    assert "finding_not_on_problem_list" in kinds(results)


def test_finding_present_on_problem_list_is_not_flagged():
    record = PatientRecord(
        imaging_studies=(
            ImagingStudy(
                study_id="CT1",
                modality="CT",
                body_site="chest",
                performed_on=date(2024, 4, 13),
                impression="Coronary artery calcification.",
            ),
        ),
        problems=(Problem(name="Coronary artery calcification"),),
    )
    results = detect_discrepancies(record, ClinicalContext(as_of=date(2025, 2, 3)))
    assert "finding_not_on_problem_list" not in kinds(results)


def test_laterality_mismatch_is_flagged():
    record = PatientRecord(
        imaging_studies=(
            ImagingStudy(
                study_id="MR1",
                modality="MRI",
                body_site="knee",
                laterality="left",
                performed_on=date(2024, 8, 1),
                impression="Medial meniscus tear.",
            ),
        ),
    )
    context = ClinicalContext(note_text="Right knee pain since last year.", as_of=date(2025, 2, 3))
    results = detect_discrepancies(record, context)
    assert "laterality_mismatch" in kinds(results)

    matching = ClinicalContext(note_text="Left knee pain.", as_of=date(2025, 2, 3))
    assert "laterality_mismatch" not in kinds(detect_discrepancies(record, matching))


def test_overdue_follow_up_is_flagged_until_a_later_study_exists():
    prior = ImagingStudy(
        study_id="CT1",
        modality="CT",
        body_site="chest",
        performed_on=date(2024, 4, 13),
        impression="8 mm pulmonary nodule.",
        recommendations=("Recommend follow-up CT chest in 6 months",),
    )
    context = ClinicalContext(as_of=date(2025, 2, 3))
    overdue = detect_discrepancies(PatientRecord(imaging_studies=(prior,)), context)
    flagged = next(item for item in overdue if item.kind == "overdue_follow_up")
    assert "2024-10-10" in flagged.summary

    follow_up = ImagingStudy(
        study_id="CT2",
        modality="CT",
        body_site="chest",
        performed_on=date(2024, 11, 1),
        impression="Stable 8 mm pulmonary nodule.",
    )
    completed = detect_discrepancies(
        PatientRecord(imaging_studies=(prior, follow_up)), context
    )
    assert "overdue_follow_up" not in kinds(completed)


def test_follow_up_not_yet_due_is_not_flagged():
    record = PatientRecord(
        imaging_studies=(
            ImagingStudy(
                study_id="CT1",
                modality="CT",
                body_site="chest",
                performed_on=date(2024, 12, 1),
                impression="8 mm pulmonary nodule.",
                recommendations=("Recommend follow-up CT chest in 6 months",),
            ),
        ),
    )
    results = detect_discrepancies(record, ClinicalContext(as_of=date(2025, 2, 3)))
    assert "overdue_follow_up" not in kinds(results)


def test_allergy_and_resolved_problem_conflicts():
    record = PatientRecord(
        problems=(Problem(name="Community acquired pneumonia", status="resolved"),),
        medications=(
            Medication(name="Amoxicillin", indication="Community acquired pneumonia"),
            Medication(name="Ibuprofen", status="stopped"),
        ),
        allergies=(Allergy(substance="Amoxicillin", reaction="hives"),),
    )
    results = detect_discrepancies(record, ClinicalContext(as_of=date(2025, 2, 3)))
    assert kinds(results) >= {"allergy_conflict", "medication_for_resolved_problem"}


def test_results_are_sorted_by_severity_and_limited():
    record = PatientRecord(
        problems=(Problem(name="Community acquired pneumonia", status="resolved"),),
        medications=(Medication(name="Amoxicillin", indication="Community acquired pneumonia"),),
        allergies=(Allergy(substance="Amoxicillin"),),
    )
    results = detect_discrepancies(record, ClinicalContext(as_of=date(2025, 2, 3)))
    assert [item.severity for item in results] == ["high", "medium"]
    assert len(detect_discrepancies(record, ClinicalContext(), limit=1)) == 1


def test_later_study_of_a_different_body_site_does_not_clear_follow_up():
    prior = ImagingStudy(
        study_id="CT1",
        modality="CT",
        body_site="chest",
        performed_on=date(2024, 4, 13),
        impression="8 mm pulmonary nodule.",
        recommendations=("Recommend follow-up CT chest in 6 months",),
    )
    unrelated = ImagingStudy(
        study_id="CT2",
        modality="CT",
        body_site="abdomen",
        performed_on=date(2024, 11, 1),
        impression="Normal abdomen.",
    )
    results = detect_discrepancies(
        PatientRecord(imaging_studies=(prior, unrelated)), ClinicalContext(as_of=date(2025, 2, 3))
    )
    assert "overdue_follow_up" in kinds(results)
