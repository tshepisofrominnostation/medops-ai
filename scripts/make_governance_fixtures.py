"""Fixtures the browser must reproduce: forecasts, method comparison, bias audit, log.

Written from the Python service, consumed by scripts/check_governance_parity.mjs. Every
value here comes out of the REAL functions in app/ - including app.analytics.build_analytics
for the demo series, so the browser is checked against the numbers the service would
actually publish, not against hand-typed expectations.

Covers, deliberately:
  * the demo history from data/demo_tickets.json (the series the page ships with)
  * synthetic series: a clean weekly cycle, pure noise, a flat/declining one, and short
    series below MIN_DAYS so the "not comparable" branch is exercised too
  * forecast horizons and history_days windows, including the empty one
  * every MATCHED_PAIRS entry, audited with the real prioritize() and with a
    keyword-biased classifier (so the audit has to report a direction, not all-zeros)
  * 16 messages for signals_for / language_hint / build_record, including isiZulu,
    Afrikaans, PHI, and English text with no signal at all

    python scripts/make_governance_fixtures.py [--out tests/data/governance_parity.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.analytics import build_analytics                       # noqa: E402
from app.bias_audit import MATCHED_PAIRS, run_audit             # noqa: E402
from app.decision_log import (build_record, language_hint,      # noqa: E402
                              signals_for, transparency_note)
from app.forecast import forecast_volume                        # noqa: E402
from app.forecast_compare import compare_methods                # noqa: E402
from app.prioritizer import prioritize                          # noqa: E402

SERIES_START = "2026-01-05"


def _days(values, start=SERIES_START):
    d0 = dt.date.fromisoformat(start)
    return [{"date": (d0 + dt.timedelta(days=i)).isoformat(), "count": v}
            for i, v in enumerate(values)]


def _synthetic_series():
    """Named series, each hitting a different branch of the two forecast modules."""
    week = [8, 9, 9, 8, 7, 1, 1]
    noise_rng = random.Random(7)
    flat_rng = random.Random(2026)
    return [
        # 12 weeks of a clean weekly cycle: the weekday method should win by a mile
        ("clean weekly cycle", _days(week * 12)),
        # no pattern at all: nothing should be crowned
        ("pure noise", _days([noise_rng.randint(2, 8) for _ in range(28)])),
        # a slow decline with weekend dips
        ("declining", _days([max(0, 12 - i // 3) - (3 if i % 7 in (5, 6) else 0)
                             for i in range(35)])),
        # rising trend: forecast slope must be positive and the forecast must climb
        ("rising", _days([2 + i for i in range(20)])),
        # flat and boring, with backtested error available
        ("flat", _days([5] * 30)),
        # too short to compare, and too short to trust a trend
        ("short", _days([5, 6, 4, 5])),
        # a spike, so the moving average has something to damp
        ("spike", _days([4, 4, 5, 4, 30, 4, 5, 4, 6, 4, 5, 4, 4, 5, 4, 6, 4, 5, 4, 4])),
        # counts that force rounding ties (halves at .5 boundaries)
        ("rounding ties", _days([flat_rng.randint(1, 3) for _ in range(21)])),
    ]


def _forecast_cases(series):
    """(label, by_day, horizon, history_days) - every one is run in both languages."""
    cases = []
    for name, rows in series:
        cases.append({"label": f"{name} h7", "by_day": rows, "horizon": 7, "history_days": None})
        cases.append({"label": f"{name} h3 last14", "by_day": rows,
                      "horizon": 3, "history_days": 14})
    # edge cases: empty history, single day, horizon 0, history_days wider than history
    cases.append({"label": "empty h4", "by_day": [], "horizon": 4, "history_days": None})
    cases.append({"label": "single day", "by_day": _days([7]), "horizon": 2, "history_days": None})
    cases.append({"label": "zero horizon", "by_day": _days([3, 4, 5, 6, 7, 8]),
                  "horizon": 0, "history_days": None})
    cases.append({"label": "history_days wider than history", "by_day": _days([3, 4, 5, 6, 7]),
                  "horizon": 2, "history_days": 99})
    cases.append({"label": "unsorted input", "by_day": list(reversed(_days([9, 1, 4, 2, 6, 3, 8]))),
                  "horizon": 3, "history_days": None})
    return cases


def _compare_cases(series):
    cases = []
    for name, rows in series:
        cases.append({"label": f"{name} seed1", "by_day": rows, "seed": 1})
    # a second seed, so the bootstrap is checked where it is not the default
    cases.append({"label": "clean weekly cycle seed5",
                  "by_day": dict(series)["clean weekly cycle"], "seed": 5})
    cases.append({"label": "pure noise seed12",
                  "by_day": dict(series)["pure noise"], "seed": 12})
    cases.append({"label": "rising seed0", "by_day": dict(series)["rising"], "seed": 0})
    # undated rows must be ignored, not crash (mirrors tests/test_forecast_compare.py)
    cases.append({"label": "undated rows ignored",
                  "by_day": _days([5] * 20) + [{"date": None, "count": 99}, {"count": 50}],
                  "seed": 3})
    # fewer than MIN_DAYS -> the not-comparable branch
    cases.append({"label": "too few days", "by_day": _days([3, 4, 5, 4, 3, 5]), "seed": 1})
    return cases


# Messages for signals_for / language_hint / build_record. Varied on purpose: the point of
# the log is the messages the English keyword lists cannot read.
RECORD_MESSAGES = [
    # (message, ticket dict) - the ticket is the thing the real build_record inspects
    ("Ventilator will not start in ICU, alarm screaming, patient on it now - Sr. Naidoo",
     {"ticket_id": "MED-101", "category": "IT & Medical Tech", "priority": "High",
      "assigned_to": "IT & Biomedical Engineering on-call"}),
    ("Umshini we-dialysis ya-4 awusebenzi, iziguli zilindile, siyadinga usizo ngokushesha",
     {"ticket_id": "MED-102", "category": "IT & Medical Tech", "priority": "Medium",
      "assigned_to": "Biomed"}),
    ("Umshini awusebenzi iziguli zilindile ngokushesha",
     {"ticket_id": "MED-103", "category": "IT & Medical Tech", "priority": "Low",
      "assigned_to": None}),
    ("Die lift is stukkend en pasiënte kan nie boontoe kom nie, dit is dringend",
     {"ticket_id": "MED-104", "category": "Operations", "priority": "Medium",
      "assigned_to": "Facilities"}),
    ("Die rekenaar in ontvangs werk nie, ons kan nie pasiente help nie",
     {"ticket_id": "MED-105", "category": "IT & Medical Tech", "priority": "Low",
      "assigned_to": "Helpdesk"}),
    ("Die water is nie warm nie en dit is 'n probleem in die kombuis",
     {"ticket_id": "MED-106", "category": "Operations", "priority": "Low",
      "assigned_to": "Facilities"}),
    ("Daar is 'n pyp gebars en die gang is vol water, dit moet nou reggemaak word",
     {"ticket_id": "MED-107", "category": "Operations", "priority": "High",
      "assigned_to": "Facilities"}),
    # PHI: the record must not carry any of this text anywhere
    ("Mr Dlamini ID 8001015800083 in bed 12 needs the ventilator urgent",
     {"ticket_id": "MED-108", "category": "IT & Medical Tech", "priority": "High",
      "assigned_to": "Biomed"}),
    ("Please can you check why my payslip shows no overtime for October",
     {"ticket_id": "MED-109", "category": "HR", "priority": "Low",
      "assigned_to": "HR Shared Services"}),
    ("Invoice from MedSupply is double what we agreed, R48 000 instead of R24 000",
     {"ticket_id": "MED-110", "category": "Finance", "priority": "Medium",
      "assigned_to": "Finance"}),
    ("Generator did not start during load shedding, theatre backup failed",
     {"ticket_id": "MED-111", "category": "Operations", "priority": "High",
      "assigned_to": "Facilities"}),
    ("Theatre 2 aircon is blowing hot air, surgeons complaining",
     {"ticket_id": "MED-112", "category": "Operations", "priority": "Medium",
      "assigned_to": "Facilities"}),
    # non-English AND an English urgency word: flagged only for language, not for review
    ("Umshini we-dialysis wont start now, iziguli zilindile, urgent",
     {"ticket_id": "MED-113", "category": "IT & Medical Tech", "priority": "High",
      "assigned_to": "Biomed"}),
    # English with no signal at all (the boring case must still work)
    ("hello", {"ticket_id": "MED-114", "category": "Operations", "priority": "Low",
               "assigned_to": ""}),
    ("asdfgh qwerty zxcv", {"ticket_id": "MED-115", "category": "HR",
                            "priority": "Low", "assigned_to": None}),
    # accents are enough on their own to hint Afrikaans
    ("Pasiënte kla dat die hysbak dikwels staan", {"ticket_id": "MED-116",
                                                   "category": "Operations",
                                                   "priority": "Medium",
                                                   "assigned_to": "Facilities"}),
    # emoji/fingerprint stability: a message with non-ASCII, non-Latin characters
    ("Ward 4 oxygen tank is almost empty, patients on it 😷 — act now",
     {"ticket_id": "MED-117", "category": "IT & Medical Tech", "priority": "High",
      "assigned_to": "Biomed"}),
]


def transparency_note_dicts(rows):
    """transparency_note() reads a file; the browser holds the rows in memory.

    This mirrors that function's arithmetic over an in-memory list so the fixture and
    the browser compute the same thing from the same input. Kept next to the fixture
    rather than in app/ because the service deliberately has no such entry point: it
    always summarises what is on disk.
    """
    from app.decision_log import transparency_note as _note
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        path = fh.name
    try:
        return _note(Path(path))
    finally:
        os.unlink(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "tests" / "data" / "governance_parity.json"))
    args = ap.parse_args()

    demo = json.loads((ROOT / "data" / "demo_tickets.json").read_text(encoding="utf-8"))
    demo_by_day = build_analytics(demo)["by_day"]

    series = [("demo history", demo_by_day)] + _synthetic_series()

    forecasts = []
    for case in _forecast_cases(series):
        forecasts.append({**case, "value": forecast_volume(
            case["by_day"], horizon=case["horizon"], history_days=case["history_days"])})

    comparisons = []
    for case in _compare_cases(series):
        comparisons.append({**case, "value": compare_methods(case["by_day"], seed=case["seed"])})

    # Two classifiers: the real rules, and a deliberately keyword-biased one so the audit
    # is checked on a case that must report a direction and a group breakdown.
    def keyword_biased(text):
        t = text.lower()
        hit = any(w in t for w in ("urgent", "emergency", "immediately",
                                   "critical", "now", "asap"))
        return {"priority": "High" if hit else "Low"}

    pairs = [{"need": n, "a_label": la, "a_text": ta, "b_label": lb, "b_text": tb}
             for n, la, ta, lb, tb in MATCHED_PAIRS]

    audits = [
        {"label": "real prioritizer",
         "value": run_audit(lambda text: {"priority": prioritize(text, "")})},
        {"label": "keyword-biased classifier",
         "value": run_audit(keyword_biased)},
        {"label": "always high (fair)", "value": run_audit(lambda text: {"priority": "High"})},
    ]

    records = []
    for message, ticket in RECORD_MESSAGES:
        ns = SimpleNamespace(**ticket)
        rec = build_record(message, ns)
        records.append({
            "message": message,
            "ticket": ticket,
            "signals": signals_for(message),
            "language_hint": language_hint(message),
            # `at` is a wall-clock stamp, so it cannot match: everything else must.
            "record": {k: v for k, v in rec.items() if k != "at"},
        })

    # transparency_note over an array of those records (the browser keeps them in
    # localStorage; the browser-side function takes the array directly).
    note_built = transparency_note_dicts([r["record"] for r in records])

    payload = {
        "generated_by": "scripts/make_governance_fixtures.py",
        "demo_ticket_count": len(demo),
        "demo_by_day": demo_by_day,
        "forecasts": forecasts,
        "comparisons": comparisons,
        "prioritizer": [
            {"message": m, "sender": s, "priority": prioritize(m, s)}
            for m, s in [(p["a_text"], "") for p in pairs] +
                         [(p["b_text"], "") for p in pairs] +
                         [(m, "") for m, _ in RECORD_MESSAGES] +
                         [("Ventilator down", "ICU"),
                          ("bed 3 monitor offline", "Emergency Ward"),
                          ("monthly invoice query", "Finance"),
                          ("rosters for December", "HR")]
        ],
        "bias_audit": {
            "pairs": pairs,
            "audits": audits,
        },
        "records": records,
        "transparency": {
            "empty": transparency_note_dicts([]),
            "all": note_built,
            "only_flagged": transparency_note_dicts(
                [r["record"] for r in records if r["record"]["needs_bias_review"]]),
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"wrote {out}: {len(forecasts)} forecast cases, {len(comparisons)} comparisons, "
          f"{len(pairs)} pairs, {len(records)} messages, "
          f"{len(payload['prioritizer'])} prioritizer cases")


if __name__ == "__main__":
    main()
