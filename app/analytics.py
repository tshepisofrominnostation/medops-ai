"""Ticket analytics: aggregate the processed-ticket history into counts and rates.

The output shape is the fixed contract the dashboard (S2-2) and the PDF report
(S2-3) build against. Treat these keys as an interface: add fields freely,
never rename or remove one without telling both consumers.
"""
from collections import Counter
from typing import Optional

from . import lifecycle
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


def _mean(values: list) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def _median(values: list) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    mid = len(v) // 2
    return round(v[mid] if len(v) % 2 else (v[mid - 1] + v[mid]) / 2, 2)


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

    # ---- Week 3 additions (additive: no existing key is renamed or removed) ----
    by_status = Counter({s: 0 for s in lifecycle.STATUSES})
    resp_all, resp_by_prio, resp_by_cat = [], {p: [] for p in PRIORITIES}, {c: [] for c in CATEGORIES}
    resolution = []
    sla_by_prio = {p: {"met": 0, "measured": 0} for p in PRIORITIES}
    category_by_day: dict = {}
    for rec in rows:
        by_status[lifecycle.status_of(rec)] += 1
        rm = lifecycle.response_minutes(rec)
        if rm is not None:
            resp_all.append(rm)
            if rec.get("priority") in resp_by_prio:
                resp_by_prio[rec["priority"]].append(rm)
            if rec.get("category") in resp_by_cat:
                resp_by_cat[rec["category"]].append(rm)
        rs = lifecycle.resolution_minutes(rec)
        if rs is not None:
            resolution.append(rs)
        met = lifecycle.sla_met(rec)
        if met is not None and rec.get("priority") in sla_by_prio:
            sla_by_prio[rec["priority"]]["measured"] += 1
            sla_by_prio[rec["priority"]]["met"] += int(met)
        day = _record_date(rec)
        if day and rec.get("category") in by_category:
            category_by_day.setdefault(day, Counter())[rec["category"]] += 1

    undated = sum(1 for rec in rows if _record_date(rec) is None)
    measured = sum(v["measured"] for v in sla_by_prio.values())
    met_total = sum(v["met"] for v in sla_by_prio.values())

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
        # --- Week 3 additions -------------------------------------------------
        "undated_tickets": undated,
        "by_status": dict(by_status),
        "by_category_by_day": [
            {"date": d, **{c: category_by_day[d].get(c, 0) for c in CATEGORIES}}
            for d in sorted(category_by_day)],
        "response_time": {
            "measured_tickets": len(resp_all),
            "unmeasured_tickets": total - len(resp_all),
            "mean_minutes": _mean(resp_all),
            "median_minutes": _median(resp_all),
            "worst_minutes": max(resp_all) if resp_all else None,
            "by_priority": {p: _mean(v) for p, v in resp_by_prio.items()},
            "by_category": {c: _mean(v) for c, v in resp_by_cat.items()},
            "mean_resolution_minutes": _mean(resolution),
        },
        "sla": {
            "targets_minutes": dict(lifecycle.SLA_TARGET_MINUTES),
            "measured_tickets": measured,
            "attainment": round(met_total / measured, 4) if measured else None,
            "by_priority": {p: (round(v["met"] / v["measured"], 4) if v["measured"] else None)
                            for p, v in sla_by_prio.items()},
        },
    }


def current_analytics(start: Optional[str] = None, end: Optional[str] = None) -> dict:
    """Aggregate the live ticket history."""
    return build_analytics(load_all(), start=start, end=end)
