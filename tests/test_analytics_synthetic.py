import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.analytics import build_analytics
from generate_tickets import generate

IT, HR, FIN, OPS = "IT & Medical Tech", "HR", "Finance", "Operations"


def t(cat, pri, day):
    return {"category": cat, "priority": pri, "assigned_to": cat,
            "created_date": f"{day}T09:00:00"}


# Counted by hand, not by code.
SAMPLE = [
    t(IT, "High", "2026-11-02"), t(IT, "Low", "2026-11-02"),
    t(HR, "Medium", "2026-11-03"), t(FIN, "High", "2026-11-03"),
    t(FIN, "Medium", "2026-11-03"), t(OPS, "Low", "2026-11-04"),
    t(IT, "High", "2026-11-04"), t(HR, "Low", "2026-11-05"),
    t(OPS, "Medium", "2026-11-05"), t(IT, "Medium", "2026-11-06"),
]


def test_hand_counted_sample():
    r = build_analytics(SAMPLE)
    assert r["total_tickets"] == 10
    assert r["by_category"] == {IT: 4, HR: 2, FIN: 2, OPS: 2}
    assert r["by_priority"] == {"High": 3, "Medium": 4, "Low": 3}
    assert [d["count"] for d in r["by_day"]] == [2, 3, 2, 2, 1]
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
    assert r["by_category"] == dict(Counter(x["category"] for x in tickets))


def test_generator_is_repeatable():
    assert generate(200) == generate(200)