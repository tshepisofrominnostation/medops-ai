"""The semantic layer: a second opinion, measured honestly."""
from app.nlp.semantic import (cross_check, cross_validate, get_model, load_corpus,
                              SemanticClassifier, tokenize, lexicon_priors)


def test_tokenizer_stems_and_drops_stopwords():
    toks = tokenize("The monitors are disconnecting from the network")
    assert "the" not in toks
    assert any(t.startswith("monitor") for t in toks)
    assert any(t.startswith("disconnect") for t in toks)


def test_lexicon_priors_carry_the_rule_engine_knowledge():
    priors = lexicon_priors()
    assert len(priors) > 50
    assert {"IT & Medical Tech", "HR", "Finance", "Operations"} == {p["category"] for p in priors}


def test_priors_improve_the_model_on_held_out_sentences():
    """The measured claim in the docstring must stay true."""
    rows = load_corpus()
    with_p = cross_validate(rows, with_priors=True)["accuracy"]
    without = cross_validate(rows, with_priors=False)["accuracy"]
    assert with_p > without, f"priors did not help: {with_p} vs {without}"
    assert with_p >= 0.65, f"cross-validated accuracy below the documented floor: {with_p}"


def test_unknown_vocabulary_is_refused_not_guessed():
    pred = get_model().predict("zzqq xxvv qqzz")
    assert pred["category"] is None
    assert pred["confident"] is False


def test_disagreement_flags_for_review_only_when_confident():
    agree = cross_check("The lift is stuck between floors", "Operations")
    assert agree["agree"] is True and agree["needs_review"] is False
    contra = cross_check("Supplier invoice has not been settled", "Operations")
    assert contra["agree"] is False


def test_cross_check_reports_both_answers():
    out = cross_check("The ventilator is not working", "Operations")
    assert out["rule_category"] == "Operations"
    assert "semantic_category" in out and "semantic_similarity" in out


def test_model_is_cached():
    assert get_model() is get_model()


def test_it_never_raises_on_odd_input():
    for text in ("", "   ", "!!!", "a" * 5000, "السلام عليكم"):
        out = get_model().predict(text)
        assert set(out) == {"category", "similarity", "margin", "confident", "scores"}
