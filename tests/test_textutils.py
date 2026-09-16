from clinical_evidence.textutils import (
    concepts,
    follow_up_interval_days,
    is_negated,
    keywords,
    mentions,
    overlap_score,
)


def test_keywords_drop_stopwords_and_short_tokens():
    assert keywords("No evidence of a pulmonary nodule") == {"pulmonary", "nodule"}


def test_overlap_score_counts_matching_terms():
    assert overlap_score({"pulmonary", "nodule"}, "right upper lobe pulmonary nodule") == 1.0
    assert overlap_score({"pulmonary", "nodule"}, "coronary calcification") == 0.0
    assert overlap_score(set(), "anything") == 0.0


def test_mentions_requires_all_meaningful_tokens():
    assert mentions("8 mm pulmonary nodule right upper lobe", "pulmonary nodule")
    assert not mentions("pleural effusion", "pulmonary nodule")


def test_is_negated_detects_preceding_cue_only():
    assert is_negated("No evidence of pulmonary nodule.", "pulmonary nodule")
    assert is_negated("Patient denies chest pain", "chest pain")
    assert not is_negated("Pulmonary nodule, no change in size", "pulmonary nodule")


def test_concepts_prefers_two_word_phrases():
    assert concepts("8 mm solid pulmonary nodule")[0] == "solid pulmonary"
    assert "pulmonary nodule" in concepts("8 mm solid pulmonary nodule")
    assert "nodule" in concepts("8 mm solid pulmonary nodule")


def test_follow_up_interval_days():
    assert follow_up_interval_days("Recommend follow-up CT chest in 6 months") == 180
    assert follow_up_interval_days("Repeat ultrasound in 2 weeks") == 14
    assert follow_up_interval_days("Mild coronary artery calcification") is None
    assert follow_up_interval_days("Follow-up as clinically indicated") is None


def test_laterality_is_not_treated_as_a_stop_word():
    assert keywords("left knee") == {"left", "knee"}
    assert not mentions("left knee pain", "right knee")
