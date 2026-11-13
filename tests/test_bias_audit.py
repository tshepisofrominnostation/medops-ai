"""Week 6: the bias audit must find real bias, report its direction, and not cry wolf."""
from types import SimpleNamespace

from app.bias_audit import MATCHED_PAIRS, run_audit, ORDER


def _classifier(rule):
    return lambda text: SimpleNamespace(priority=rule(text))


def test_a_fair_classifier_scores_perfectly():
    # Same priority regardless of wording: the audit must not invent bias.
    out = run_audit(_classifier(lambda t: "High"))
    assert out["inconsistent"] == 0
    assert out["consistency_rate"] == 100.0
    assert "No wording bias was detected" in out["verdict"]


def test_keyword_dependent_classifier_is_caught_and_direction_is_right():
    # Biased on purpose: only English urgency keywords raise the priority.
    def rule(text):
        t = text.lower()
        return "High" if any(w in t for w in ("urgent", "emergency", "immediately", "critical", "now", "asap")) else "Low"
    out = run_audit(_classifier(rule))
    assert out["inconsistent"] > 0
    # the harm lands on the non-keyword wording, never on the keyword-rich one
    for row in out["rows"]:
        if not row["consistent"]:
            assert row["under_served"] == row["variant_a"]
            assert ORDER[row["priority_a"]] < ORDER[row["priority_b"]]


def test_direction_flips_when_the_other_variant_is_under_served():
    # If variant B were the one losing, the audit must say so, not always blame A.
    out = run_audit(_classifier(lambda t: "Low" if t.startswith(("URGENT", "Emergency", "Critical", "The", "A pipe", "Dialysis")) else "High"))
    losers = {r["under_served"] for r in out["rows"] if not r["consistent"]}
    assert losers, "expected some inconsistency"
    assert any(l in {"English", "keyword-rich English"} for l in losers)


def test_group_breakdown_counts_add_up():
    out = run_audit(_classifier(lambda t: "High" if "urgent" in t.lower() else "Low"))
    assert sum(g["pairs"] for g in out["by_group"].values()) == out["pairs_tested"]
    for g in out["by_group"].values():
        assert 0 <= g["under_served"] <= g["pairs"]


def test_audit_accepts_dict_results_too():
    out = run_audit(lambda t: {"priority": "Medium"})
    assert out["inconsistent"] == 0


def test_limits_are_always_stated():
    out = run_audit(_classifier(lambda t: "High"))
    assert "cannot measure how large" in out["limits"]


def test_pair_set_covers_the_three_risk_groups():
    labels = {p[1] for p in MATCHED_PAIRS}
    assert {"isiZulu", "Afrikaans", "plain English"} <= labels


def test_real_pipeline_bias_is_on_record():
    # Regression marker: this documents the CURRENT measured behaviour of the real
    # classifier. When the bias is fixed this test should be updated deliberately,
    # not silently - a fix is a decision worth noticing.
    from app.pipeline import process_ticket
    out = run_audit(lambda t: process_ticket(t))
    assert out["pairs_tested"] == 6
    assert out["inconsistent"] >= 1
    assert out["consistency_rate"] < 100
