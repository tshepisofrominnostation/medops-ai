"""Bring tickets generated in the published console into the real store.

The public page runs the engine in the browser, so a ticket created there is real
engine output but lives in that browser. This is the door back: the page exports the
same JSON shape the store uses, and `python -m app.cli import` merges it in, so the
shared dashboard and the reports pick the tickets up on the next build.

Deliberately strict. A malformed row is rejected with a reason rather than coerced:
a dashboard that silently accepts a bad category is worse than one that refuses it.
Rows already in the store are skipped by sender + summary, so importing the same export
twice does not create duplicates.
"""
import json
import typing
from datetime import datetime, timezone
from pathlib import Path

from . import persistence
from .models import Category, Priority

VALID_CATEGORIES = set(typing.get_args(Category))
VALID_PRIORITIES = set(typing.get_args(Priority))
REQUIRED_TEXT = ("sender", "summary", "assigned_to")


def fingerprint(record: dict) -> tuple[str, str]:
    return (
        str(record.get("sender", "")).strip().lower(),
        str(record.get("summary", "")).strip().lower(),
    )


def _read_rows(payload) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("tickets"), list):
        return payload["tickets"]
    raise ValueError("expected a list of tickets or an object with a 'tickets' list")


def _validate(row: dict) -> tuple[dict | None, str | None]:
    if not isinstance(row, dict):
        return None, "row is not an object"
    for field in REQUIRED_TEXT:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            return None, f"missing or empty '{field}'"
    category = row.get("category")
    if category not in VALID_CATEGORIES:
        return None, f"unknown category {category!r}"
    priority = row.get("priority")
    if priority not in VALID_PRIORITIES:
        return None, f"unknown priority {priority!r}"
    timestamp = row.get("timestamp")
    if timestamp is not None:
        try:
            datetime.fromisoformat(str(timestamp))
        except ValueError:
            return None, f"timestamp is not ISO 8601: {timestamp!r}"
    return {
        "ticket_id": "",                      # assigned by persistence.append
        "timestamp": timestamp or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "sender": row["sender"].strip(),
        "category": category,
        "priority": priority,
        "summary": row["summary"].strip(),
        "assigned_to": row["assigned_to"].strip(),
        "first_response_at": None,            # nothing has answered it yet
        "status": "Open",
        "resolved_at": None,
        "synthetic": False,                   # a person typed it; it is not seeded data
    }, None


def import_tickets(payload, dry_run: bool = False) -> dict:
    """Merge rows into the store. Returns what happened, never raises on bad rows."""
    rows = _read_rows(payload)
    existing = {fingerprint(r) for r in persistence.load_all()}
    added, skipped, rejected = [], [], []

    for index, row in enumerate(rows):
        clean, reason = _validate(row)
        if reason:
            rejected.append({"row": index, "reason": reason})
            continue
        key = fingerprint(clean)
        if key in existing:
            skipped.append({"row": index, "reason": "already in the store"})
            continue
        existing.add(key)
        if not dry_run:
            clean = persistence.append(clean)
        added.append({"ticket_id": clean["ticket_id"] or "(pending)", "sender": clean["sender"]})

    return {
        "added": added,
        "skipped": skipped,
        "rejected": rejected,
        "dry_run": dry_run,
        "summary": {
            "added": len(added),
            "skipped": len(skipped),
            "rejected": len(rejected),
            "store": str(persistence.DB_PATH),
            "dry_run": dry_run,
        },
    }


def import_file(path: str | Path, dry_run: bool = False) -> dict:
    return import_tickets(json.loads(Path(path).read_text()), dry_run=dry_run)
