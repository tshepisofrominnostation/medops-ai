<<<<<<< HEAD
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.analytics import build_analytics
from generate_tickets import generate

# 10 tickets counted BY HAND. Expected numbers below come from my eyes, not from code.
def t(cat, pri, day):
    return {"category": cat, "priority": pri, "assigned_to": cat,
            "created_date": f"{day}T09:00:00"}

IT, HR, FIN, OPS = "IT & Medical Tech", "HR", "Finance", "Operations"

SAMPLE = [
    t(IT, "High", "2026-11-02"),
    t(IT, "Low", "2026-11-02"),
    t(HR, "Medium", "2026-11-03"),
    t(FIN, "High", "2026-11-03"),
    t(FIN, "Medium", "2026-11-03"),
    t(OPS, "Low", "2026-11-04"),
    t(IT, "High", "2026-11-04"),
    t(HR, "Low", "2026-11-05"),
    t(OPS, "Medium", "2026-11-05"),
    t(IT, "Medium", "2026-11-06"),
]


def test_hand_counted_sample():
    r = build_analytics(SAMPLE)
    assert r["total_tickets"] == 10
    assert r["by_category"] == {IT: 4, HR: 2, FIN: 2, OPS: 2}
    assert r["by_priority"] == {"High": 3, "Medium": 4, "Low": 3}
    assert r["by_day"] == [
        {"date": "2026-11-02", "count": 2},
        {"date": "2026-11-03", "count": 3},
        {"date": "2026-11-04", "count": 2},
        {"date": "2026-11-05", "count": 2},
        {"date": "2026-11-06", "count": 1},
    ]
    assert r["date_range"] == {"first": "2026-11-02", "last": "2026-11-06"}
    assert r["rates"]["high_priority_share"] == 0.3
    assert r["rates"]["tickets_per_day"] == 2.0


def test_date_window_is_inclusive():
    r = build_analytics(SAMPLE, start="2026-11-03", end="2026-11-04")
    assert r["total_tickets"] == 5


def test_200_synthetic_tickets_add_up():
    tickets = generate(200)
    r = build_analytics(tickets)
    assert r["total_tickets"] == 200
    assert sum(r["by_category"].values()) == 200
    assert sum(r["by_priority"].values()) == 200
    assert sum(d["count"] for d in r["by_day"]) == 200
    # independent recount of the same data
    assert r["by_category"] == dict(Counter(x["category"] for x in tickets))


def test_generator_is_repeatable():
    assert generate(200) == generate(200)
=======
"""S2-4: analytics test gate on a synthetic ticket history.

The gate asserts the invariants the dashboard and PDF depend on, so a change to
grouping, windows or rates cannot silently break both consumers.
"""
import random
from app.analytics import build_analytics, CATEGORIES, PRIORITIES

DEPTS = ["IT & Medical Tech Team", "HR Admin Team", "Finance Duty Officer", "Facilities Team"]


def synthetic_history(n=120, days=28, seed=7):
    rnd = random.Random(seed)
    recs = []
    for i in range(n):
        day = rnd.randint(1, days)
        recs.append({
            "ticket_id": f"MED-{i:03d}",
            "category": rnd.choice(CATEGORIES),
            "priority": rnd.choice(PRIORITIES),
            "assigned_to": rnd.choice(DEPTS),
            "timestamp": f"2026-10-{day:02d}T{rnd.randint(0,23):02d}:00:00+00:00",
        })
    return recs


def test_totals_are_conserved():
    recs = synthetic_history()
    d = build_analytics(recs)
    assert d["total_tickets"] == len(recs)
    assert sum(d["by_category"].values()) == len(recs)
    assert sum(d["by_priority"].values()) == len(recs)
    assert sum(d["by_department"].values()) == len(recs)
    assert sum(r["count"] for r in d["by_day"]) == len(recs)


def test_every_day_sum_matches_window():
    recs = synthetic_history()
    d = build_analytics(recs)
    assert d["date_range"]["first"] == min(r["date"] for r in d["by_day"])
    assert d["date_range"]["last"] == max(r["date"] for r in d["by_day"])


def test_window_is_inclusive_and_subset():
    recs = synthetic_history()
    full = build_analytics(recs)
    lo, hi = full["date_range"]["first"], full["date_range"]["last"]
    assert build_analytics(recs, start=lo, end=hi)["total_tickets"] == len(recs)
    mid = sorted(r["date"] for r in full["by_day"])[len(full["by_day"]) // 2]
    only = build_analytics(recs, start=mid, end=mid)
    expected = next(r["count"] for r in full["by_day"] if r["date"] == mid)
    assert only["total_tickets"] == expected
    assert only["total_tickets"] < len(recs)


def test_rates_stay_in_range():
    d = build_analytics(synthetic_history())
    assert 0.0 <= d["rates"]["high_priority_share"] <= 1.0
    assert d["rates"]["tickets_per_day"] > 0


def test_empty_history_is_zeroed_not_crashed():
    d = build_analytics([])
    assert d["total_tickets"] == 0
    assert d["rates"]["high_priority_share"] == 0.0
    assert d["by_day"] == []
>>>>>>> origin/main
