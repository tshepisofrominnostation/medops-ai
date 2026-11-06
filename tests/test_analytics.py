"""S2-1 analytics service: contract, counts, windowing, and edge cases."""
from app.analytics import build_analytics

def rec(cat, pri, dept, day, tid):
    return {"category": cat, "priority": pri, "assigned_to": dept,
            "created_date": f"{day}T09:00:00", "ticket_id": tid}

ROWS = [
    rec("IT & Medical Tech", "High", "IT & Biomedical Engineering on-call", "2026-11-02", "MED-001"),
    rec("IT & Medical Tech", "Medium", "IT Service Desk", "2026-11-02", "MED-002"),
    rec("HR", "Low", "HR Admin Team", "2026-11-03", "MED-003"),
    rec("Finance", "High", "Finance Duty Officer", "2026-11-04", "MED-004"),
    rec("Operations", "Medium", "Operations & Maintenance Team", "2026-11-04", "MED-005"),
]

def test_contract_keys_are_stable():
    d = build_analytics(ROWS)
    for key in ("total_tickets", "date_range", "window", "by_category",
                "by_priority", "by_department", "by_day", "rates"):
        assert key in d, f"contract key missing: {key}"

def test_counts_and_total():
    d = build_analytics(ROWS)
    assert d["total_tickets"] == 5
    assert d["by_priority"] == {"High": 2, "Medium": 2, "Low": 1}
    assert d["by_category"]["IT & Medical Tech"] == 2

def test_all_categories_present_even_when_zero():
    d = build_analytics(ROWS[2:])   # only HR/Finance/Operations
    assert d["by_category"]["IT & Medical Tech"] == 0

def test_date_window_is_inclusive():
    d = build_analytics(ROWS, start="2026-11-02", end="2026-11-03")
    assert d["total_tickets"] == 3
    assert d["date_range"] == {"first": "2026-11-02", "last": "2026-11-03"}
    assert d["window"] == {"start": "2026-11-02", "end": "2026-11-03"}

def test_by_day_sorted_and_counted():
    d = build_analytics(ROWS)
    assert [x["date"] for x in d["by_day"]] == ["2026-11-02", "2026-11-03", "2026-11-04"]
    assert d["by_day"][-1]["count"] == 2

def test_rates():
    d = build_analytics(ROWS)
    assert d["rates"]["high_priority_share"] == 0.4
    assert d["rates"]["tickets_per_day"] == round(5 / 3, 2)

def test_empty_history_does_not_crash():
    d = build_analytics([])
    assert d["total_tickets"] == 0
    assert d["date_range"] == {"first": None, "last": None}
    assert d["rates"]["high_priority_share"] == 0.0
    assert d["rates"]["tickets_per_day"] == 0.0

def test_window_excludes_undated_records():
    rows = ROWS + [{"category": "HR", "priority": "Low", "assigned_to": "HR Admin Team"}]
    d = build_analytics(rows, start="2026-11-01", end="2026-11-30")
    assert d["total_tickets"] == 5
    d_all = build_analytics(rows)
    assert d_all["total_tickets"] == 6


def test_by_day_supports_timestamp_field():
    rows = [
        {
            "ticket_id": "MED-101",
            "category": "HR",
            "priority": "Low",
            "assigned_to": "HR Admin Team",
            "timestamp": "2026-10-28T11:26:16+02:00",
        },
        {
            "ticket_id": "MED-102",
            "category": "Finance",
            "priority": "High",
            "assigned_to": "Finance Duty Officer",
            "timestamp": "2026-10-28T14:30:00+02:00",
        },
    ]

    d = build_analytics(rows)

    assert d["total_tickets"] == 2
    assert d["by_day"] == [
        {"date": "2026-10-28", "count": 2}
    ]
    assert d["date_range"] == {
        "first": "2026-10-28",
        "last": "2026-10-28",
    }


# --- regression: persisted tickets use the `timestamp` key ---

def _persisted(tid, cat, pri, day_iso, dept="Ops"):
    return {"ticket_id": tid, "category": cat, "priority": pri,
            "assigned_to": dept, "timestamp": day_iso}


def test_timestamp_records_are_grouped_by_day():
    recs = [_persisted("MED-1", "IT & Medical Tech", "High", "2026-11-04T09:00:00+00:00"),
            _persisted("MED-2", "HR", "Low", "2026-11-04T15:30:00+00:00"),
            _persisted("MED-3", "Finance", "Medium", "2026-11-05T08:10:00+00:00")]
    out = build_analytics(recs)
    days = {d["date"]: d["count"] for d in out["by_day"]}
    assert days == {"2026-11-04": 2, "2026-11-05": 1}
    assert out["date_range"]["first"] == "2026-11-04"
    assert out["rates"]["tickets_per_day"] > 0


def test_date_window_keeps_timestamp_records_inside_it():
    recs = [_persisted("MED-1", "IT & Medical Tech", "High", "2026-11-03T09:00:00+00:00"),
            _persisted("MED-2", "HR", "Low", "2026-11-05T09:00:00+00:00")]
    inside = build_analytics(recs, start="2026-11-04", end="2026-11-06")
    assert inside["total_tickets"] == 1
    assert inside["by_day"] == [{"date": "2026-11-05", "count": 1}]
    outside = build_analytics(recs, start="2026-01-01", end="2026-01-31")
    assert outside["total_tickets"] == 0
