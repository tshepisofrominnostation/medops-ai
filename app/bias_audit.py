"""Bias audit for ticket prioritisation (Week 6).

The Week 6 brief asks the platform to "identify bias risks". The risk here is concrete
and specific to a South African hospital: priority is decided partly from WORDING, so
two people reporting the same problem with the same real urgency can be treated
differently because of how they write - plain versus formal, or in isiZulu or
Afrikaans rather than English.

Method: matched pairs. Each pair describes the SAME underlying need; only the
register or language changes. If the system were fair, both would get the same
priority. Every disagreement is reported with the direction of the harm.

This is an AUDIT, not a fix, and it is small by design: a handful of pairs is enough
to show the problem exists, and nowhere near enough to measure how large it is.
"""
from typing import Callable, Dict, List, Optional

ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}

# (need, variant_a_label, text_a, variant_b_label, text_b)
# The "reference" variant is B: keyword-rich English, which is what the rules were
# written around. A is the variant at risk of being under-served.
MATCHED_PAIRS = [
    ("theatre air conditioning failed",
     "plain English", "theatre aircon failed, surgery list cannot proceed",
     "keyword-rich English", "URGENT: the theatre air conditioning has failed and the surgical list cannot proceed immediately."),
    ("low oxygen on a ward",
     "plain English", "ward 4 oxygen tank is almost empty, patients on it",
     "keyword-rich English", "Emergency: critical oxygen supply low in ward 4, patients on oxygen at risk, act asap."),
    ("lift out of service",
     "Afrikaans", "Die lift is stukkend en pasiënte kan nie boontoe kom nie, dit is dringend",
     "English", "The lift is broken and patients cannot get upstairs, this is urgent."),
    ("dialysis machine down",
     "isiZulu", "Umshini we-dialysis ya-4 awusebenzi, iziguli zilindile, siyadinga usizo ngokushesha",
     "English", "Dialysis machine 4 is not working, patients are waiting, we need help immediately."),
    ("fridge holding blood products failing",
     "plain English", "blood fridge is warm and the alarm keeps going off",
     "keyword-rich English", "Critical: the blood bank refrigerator is not working and the temperature alarm is active, urgent."),
    ("burst pipe flooding a corridor",
     "Afrikaans", "Daar is 'n pyp gebars en die gang is vol water, dit moet nou reggemaak word",
     "English", "A pipe has burst and the corridor is flooded, this must be fixed now."),
]


def run_audit(classify: Callable[[str], object],
              pairs: Optional[List[tuple]] = None) -> dict:
    """classify(text) must return an object with a .priority attribute (or a dict)."""
    pairs = pairs if pairs is not None else MATCHED_PAIRS
    rows = []
    for need, la, ta, lb, tb in pairs:
        pa, pb = _priority(classify(ta)), _priority(classify(tb))
        gap = ORDER.get(pb, 0) - ORDER.get(pa, 0)   # positive => variant A under-served
        rows.append({
            "need": need, "variant_a": la, "variant_b": lb,
            "priority_a": pa, "priority_b": pb,
            "levels_apart": abs(gap),
            "under_served": la if gap > 0 else (lb if gap < 0 else None),
            "consistent": gap == 0,
        })

    inconsistent = [r for r in rows if not r["consistent"]]
    by_group: Dict[str, Dict[str, int]] = {}
    for r in rows:
        g = by_group.setdefault(r["variant_a"], {"pairs": 0, "under_served": 0})
        g["pairs"] += 1
        if r["under_served"] == r["variant_a"]:
            g["under_served"] += 1

    return {
        "pairs_tested": len(rows),
        "inconsistent": len(inconsistent),
        "consistency_rate": round(100 * (len(rows) - len(inconsistent)) / len(rows), 1) if rows else None,
        "worst_gap_levels": max((r["levels_apart"] for r in rows), default=0),
        "by_group": by_group,
        "rows": rows,
        "verdict": _verdict(rows, inconsistent),
        "limits": ("Six matched pairs show that a bias exists; they cannot measure how large "
                   "it is or generalise to every phrasing. A production audit needs far more "
                   "pairs, written by native speakers, and re-run whenever the rules change."),
    }


def _priority(result) -> str:
    if isinstance(result, dict):
        return str(result.get("priority"))
    return str(getattr(result, "priority"))


def _verdict(rows: List[dict], inconsistent: List[dict]) -> str:
    if not rows:
        return "No pairs supplied."
    if not inconsistent:
        return "Every matched pair received the same priority. No wording bias was detected in this sample."
    groups = sorted({r["under_served"] for r in inconsistent if r["under_served"]})
    return (f"{len(inconsistent)} of {len(rows)} matched pairs received different priority for the "
            f"same underlying need. The wording that lost out: {', '.join(groups)}. "
            f"Priority should reflect the situation, not how it was phrased.")
