"""Ticket analytics: aggregate the processed-ticket history into counts and rates.

The output shape is the fixed contract the dashboard (S2-2) and the PDF report
(S2-3) build against. Treat these keys as an interface: add fields freely,
never rename or remove one without telling both consumers.
"""
from collections import Counter
from typing import Optional

from .persistence import load_all

CATEGORIES = ("IT & Medical Tech", "HR", "Finance", "Operations")
PRIORITIES = ("High", "Medium", "Low")


DATE_KEYS = ("created_date", "date", "timestamp")


def _record_date(rec: dict) -> Optional[str]:
    """Best-effort day for a record.

    Persisted tickets carry `timestamp` (ISO-8601, e.g. 2026-11-05T09:03:10+00:00),
    while callers building analytics by hand tend to pass `created_date` or `date`.
    All three are accepted, in that order of preference.
    """
    for key in DATE_KEYS:
        stamp = rec.get(key)
        if isinstance(stamp, str) and len(stamp) >= 10:
            return stamp[:10]
    return None


def build_analytics(records: list[dict], start: Optional[str] = None,
                    end: Optional[str] = None) -> dict:
    """Aggregate records into the analytics contract.

    start/end are inclusive ISO dates (YYYY-MM-DD); records with no usable date
    are kept when no window is requested, and excluded from a dated window.
    """
    rows = records
    if start or end:
        kept = []
        for rec in records:
            day = _record_date(rec)
            if day is None:
                continue
            if start and day < start:
                continue
            if end and day > end:
                continue
            kept.append(rec)
        rows = kept

    by_category = Counter({c: 0 for c in CATEGORIES})
    by_priority = Counter({p: 0 for p in PRIORITIES})
    by_department = Counter()
    by_day = Counter()

    for rec in rows:
        if rec.get("category") in by_category:
            by_category[rec["category"]] += 1
        if rec.get("priority") in by_priority:
            by_priority[rec["priority"]] += 1
        if rec.get("assigned_to"):
            by_department[rec["assigned_to"]] += 1
        day = _record_date(rec)
        if day:
            by_day[day] += 1

    total = len(rows)
    high = by_priority.get("High", 0)
    days = sorted(by_day)

    return {
        "total_tickets": total,
        "date_range": {"first": days[0] if days else None,
                       "last": days[-1] if days else None},
        "window": {"start": start, "end": end},
        "by_category": dict(by_category),
        "by_priority": dict(by_priority),
        "by_department": dict(by_department.most_common()),
        "by_day": [{"date": d, "count": by_day[d]} for d in days],
        "rates": {
            "high_priority_share": round(high / total, 4) if total else 0.0,
            "tickets_per_day": round(total / len(days), 2) if days else 0.0,
        },
    }


def current_analytics(start: Optional[str] = None, end: Optional[str] = None) -> dict:
    """Aggregate the live ticket history."""
    return build_analytics(load_all(), start=start, end=end)
