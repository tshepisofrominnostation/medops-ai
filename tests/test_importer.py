"""Tickets generated on the published page must survive the trip into the store."""
import json

import pytest

from app import persistence
from app.importer import import_tickets


def _row(**over):
    row = {
        "sender": "Sister Naidoo (ICU)",
        "category": "IT & Medical Tech",
        "priority": "High",
        "summary": "Ventilator in ICU Bay 3 will not start. Reported by ICU; classified as "
                   "IT & Medical Tech with High priority.",
        "assigned_to": "IT & Biomedical Engineering on-call",
        "timestamp": "2026-11-06T11:30:00+02:00",
    }
    row.update(over)
    return row


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = tmp_path / "tickets.json"
    path.write_text("[]")
    monkeypatch.setattr(persistence, "DB_PATH", path)
    return path


def test_import_appends_and_assigns_ids(store):
    report = import_tickets([_row(), _row(sender="Mr Adams (Block B)", summary="Generator failed test.")])
    assert report["summary"]["added"] == 2
    rows = json.loads(store.read_text())
    assert [r["ticket_id"] for r in rows] == ["MED-001", "MED-002"]
    assert all(r["status"] == "Open" for r in rows)
    assert all(r["first_response_at"] is None for r in rows)
    assert all(r["synthetic"] is False for r in rows)


def test_import_is_idempotent(store):
    import_tickets([_row()])
    second = import_tickets([_row()])
    assert second["summary"]["added"] == 0
    assert second["summary"]["skipped"] == 1
    assert len(json.loads(store.read_text())) == 1


def test_bad_rows_are_rejected_with_a_reason(store):
    report = import_tickets([
        _row(category="Facilities"),          # renamed in Sprint 2
        _row(priority="Urgent"),
        _row(sender=""),
        _row(timestamp="last Tuesday"),
        "not a row",
    ])
    assert report["summary"]["added"] == 0
    assert report["summary"]["rejected"] == 5
    assert "unknown category" in report["rejected"][0]["reason"]
    assert "unknown priority" in report["rejected"][1]["reason"]
    assert json.loads(store.read_text()) == []


def test_dry_run_writes_nothing(store):
    report = import_tickets([_row()], dry_run=True)
    assert report["summary"]["added"] == 1
    assert json.loads(store.read_text()) == []


def test_accepts_the_page_export_envelope(store):
    report = import_tickets({"tickets": [_row()]})
    assert report["summary"]["added"] == 1


def test_cli_import_honours_store_flag(tmp_path):
    """Import must say where it wrote, and --store must be what decides it."""
    import subprocess
    import sys

    export = tmp_path / "export.json"
    export.write_text(json.dumps([_row()]))
    store = tmp_path / "seed.json"
    store.write_text("[]")
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "import", str(export), "--store", str(store)],
        cwd=__file__.rsplit("/tests/", 1)[0], capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["summary"]["added"] == 1
    assert report["summary"]["store"] == str(store)
    assert json.loads(store.read_text())[0]["ticket_id"] == "MED-001"
