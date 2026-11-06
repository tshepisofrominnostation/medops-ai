"""Ticket lifecycle (Week 3): status, first response and resolution timestamps.

Week 3 asks the platform to analyse *response time*. That is impossible unless the
moment a ticket is first answered and the moment it is resolved are recorded.
This module owns those fields and nothing else.

Design rules
- Backward compatible: tickets written before this module existed have no
  lifecycle fields. They read as status "Open" with no response time, and are
  never given an invented one.
- Time is stored as ISO-8601 with timezone, the same format as `timestamp`.
- The persistence file is rewritten under the same lock `append` uses.
"""
from datetime import datetime, timezone
from typing import Optional

from . import persistence

STATUSES = ("Open", "In Progress", "Resolved")

# Response-time targets in minutes, by priority. These are *proposed* targets,
# stated here in one place so the team can change them. They are not a hospital
# policy; the dashboard labels them as targets, not as commitments.
SLA_TARGET_MINUTES = {"High": 15, "Medium": 120, "Low": 480}

# Resolution-time targets in minutes, by priority, for the weekly report's second
# compliance column. Same status as the response targets: proposed, stated once.
RESOLUTION_TARGET_MINUTES = {"High": 240, "Medium": 480, "Low": 1440}


class LifecycleError(ValueError):
    """Raised for an unknown ticket or an invalid transition."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_ts(value) -> Optional[datetime]:
    """Parse an ISO timestamp; return None for anything unusable (never raises)."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def status_of(rec: dict) -> str:
    if rec.get("status") in STATUSES:
        return rec["status"]
    if rec.get("resolved_at"):
        return "Resolved"
    if rec.get("first_response_at"):
        return "In Progress"
    return "Open"


def minutes_between(start, end) -> Optional[float]:
    a, b = parse_ts(start), parse_ts(end)
    if a is None or b is None:
        return None
    minutes = (b - a).total_seconds() / 60
    # A negative interval means bad data (response before creation); refuse it
    # rather than let it drag an average below zero.
    return round(minutes, 2) if minutes >= 0 else None


def update_ticket(ticket_id: str, status: str, at: Optional[str] = None) -> dict:
    """Move a ticket to a new status, stamping the lifecycle timestamps.

    Open -> In Progress stamps first_response_at.
    Any -> Resolved stamps resolved_at (and first_response_at if never set).
    Resolved -> Open/In Progress reopens and clears resolved_at.
    """
    if status not in STATUSES:
        raise LifecycleError(f"status must be one of {', '.join(STATUSES)}")
    stamp = at or _now()
    if at is not None and parse_ts(at) is None:
        raise LifecycleError("timestamp must be ISO-8601, e.g. 2026-11-06T09:30:00+02:00")

    with persistence._lock:
        rows = persistence.load_all()
        target = next((r for r in rows if r.get("ticket_id") == ticket_id), None)
        if target is None:
            raise LifecycleError(f"unknown ticket {ticket_id}")

        created = target.get("timestamp")
        if created and parse_ts(stamp) and parse_ts(created) and parse_ts(stamp) < parse_ts(created):
            raise LifecycleError("a lifecycle timestamp cannot be earlier than ticket creation")

        if status == "In Progress":
            target.setdefault("first_response_at", stamp)
            target.pop("resolved_at", None)
        elif status == "Resolved":
            target.setdefault("first_response_at", stamp)
            target["resolved_at"] = stamp
        else:  # Open (reopen)
            target.pop("resolved_at", None)
        target["status"] = status

        persistence.DB_PATH.parent.mkdir(exist_ok=True)
        with persistence.DB_PATH.open("w") as f:
            import json
            json.dump(rows, f, indent=2, ensure_ascii=False)
    return target


def response_minutes(rec: dict) -> Optional[float]:
    return minutes_between(rec.get("timestamp"), rec.get("first_response_at"))


def resolution_minutes(rec: dict) -> Optional[float]:
    return minutes_between(rec.get("timestamp"), rec.get("resolved_at"))


def sla_met(rec: dict) -> Optional[bool]:
    """True/False once a first response exists; None while it is still unknown."""
    mins = response_minutes(rec)
    target = SLA_TARGET_MINUTES.get(rec.get("priority"))
    if mins is None or target is None:
        return None
    return mins <= target
