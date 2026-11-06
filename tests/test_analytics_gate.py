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
