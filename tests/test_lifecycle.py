"""Week 3: the lifecycle timestamps that make response time measurable."""
import json
import os

import pytest


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """Isolate persistence for every test in this file."""
    path = tmp_path / "tickets.json"
    monkeypatch.setenv("MEDOPS_DB_PATH", str(path))
    import app.persistence as persistence
    monkeypatch.setattr(persistence, "DB_PATH", path)
    rows = [
        {"ticket_id": "MED-001", "timestamp": "2026-11-02T08:00:00+02:00",
         "category": "HR", "priority": "High", "assigned_to": "HR Admin Team",
         "sender": "x", "summary": "s"},
        {"ticket_id": "MED-002", "timestamp": "2026-11-02T09:00:00+02:00",
         "category": "Finance", "priority": "Low", "assigned_to": "Finance",
         "sender": "y", "summary": "t"},
    ]
    path.write_text(json.dumps(rows))
    return path


def test_new_ticket_is_open_with_no_response_time(db):
    from app import lifecycle, persistence
    rec = persistence.load_all()[0]
    assert lifecycle.status_of(rec) == "Open"
    assert lifecycle.response_minutes(rec) is None
    assert lifecycle.sla_met(rec) is None, "no response yet, so SLA is unknown, not failed"


def test_starting_stamps_first_response(db):
    from app.lifecycle import update_ticket, response_minutes, status_of
    rec = update_ticket("MED-001", "In Progress", at="2026-11-02T08:10:00+02:00")
    assert status_of(rec) == "In Progress"
    assert response_minutes(rec) == 10.0


def test_resolving_stamps_resolution_and_keeps_response(db):
    from app.lifecycle import update_ticket, response_minutes, resolution_minutes, status_of
    update_ticket("MED-001", "In Progress", at="2026-11-02T08:10:00+02:00")
    rec = update_ticket("MED-001", "Resolved", at="2026-11-02T09:00:00+02:00")
    assert status_of(rec) == "Resolved"
    assert response_minutes(rec) == 10.0
    assert resolution_minutes(rec) == 60.0


def test_resolving_an_untouched_ticket_still_sets_a_response(db):
    """A ticket answered and closed in one move is still an answered ticket."""
    from app.lifecycle import update_ticket, response_minutes
    rec = update_ticket("MED-002", "Resolved", at="2026-11-02T09:30:00+02:00")
    assert response_minutes(rec) == 30.0


def test_reopening_clears_resolution_but_keeps_response(db):
    from app.lifecycle import update_ticket, resolution_minutes, response_minutes
    update_ticket("MED-001", "Resolved", at="2026-11-02T08:30:00+02:00")
    rec = update_ticket("MED-001", "Open", at="2026-11-02T10:00:00+02:00")
    assert rec["status"] == "Open"
    assert resolution_minutes(rec) is None
    assert response_minutes(rec) == 30.0, "the first response still happened"


def test_timestamp_before_creation_is_rejected(db):
    from app.lifecycle import update_ticket, LifecycleError
    with pytest.raises(LifecycleError):
        update_ticket("MED-001", "In Progress", at="2026-11-01T08:00:00+02:00")


def test_unknown_ticket_is_rejected(db):
    from app.lifecycle import update_ticket, LifecycleError
    with pytest.raises(LifecycleError):
        update_ticket("MED-999", "In Progress")


def test_invalid_status_is_rejected(db):
    from app.lifecycle import update_ticket, LifecycleError
    with pytest.raises(LifecycleError):
        update_ticket("MED-001", "Done")


def test_sla_bands(db):
    from app.lifecycle import update_ticket, sla_met
    # High target is 15 minutes
    assert sla_met(update_ticket("MED-001", "In Progress", at="2026-11-02T08:05:00+02:00")) is True
    rec = update_ticket("MED-001", "Open", at="2026-11-02T08:05:00+02:00")
    rec["first_response_at"] = "2026-11-02T09:00:00+02:00"   # 60 min
    assert sla_met(rec) is False


def test_bad_timestamps_never_raise():
    from app.lifecycle import parse_ts, minutes_between
    for bad in (None, "", "not a date", 12345, "2026-13-45"):
        assert parse_ts(bad) is None
    assert minutes_between("nonsense", "2026-11-02T08:00:00+02:00") is None
    # a response before creation is refused rather than producing a negative average
    assert minutes_between("2026-11-02T10:00:00+02:00", "2026-11-02T08:00:00+02:00") is None
