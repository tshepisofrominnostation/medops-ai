"""MedOps AI Sprint 1 test suite — includes the exact graded validation scenario."""
import re

from app.classifier import classify
from app.models import TicketOut
from app.pipeline import process_ticket
from app.prioritizer import prioritize

REQUIRED_KEYS = {"ticket_id", "timestamp", "sender", "category", "priority", "summary", "assigned_to"}


def process_fresh(tmp_path, monkeypatch, message, sender=None):
    """Run the pipeline against a clean database."""
    monkeypatch.setattr("app.persistence.DB_PATH", tmp_path / "tickets_processed.json")
    return process_ticket(message, sender)


def test_required_emergency_scenario(tmp_path, monkeypatch):
    """Dr. S. Khumalo's telemetry failure: IT & Medical Tech + High + valid schema."""
    raw = ('"The patient monitoring terminal in Bay 3 keeps disconnecting from the '
           'local network during telemetry sync." - Dr. S. Khumalo (Emergency Ward)')
    t = process_fresh(tmp_path, monkeypatch, raw)
    assert t.category == "IT & Medical Tech"
    assert t.priority == "High"
    assert t.sender == "Dr. S. Khumalo (Emergency Ward)"
    assert t.assigned_to == "IT & Biomedical Engineering on-call"
    assert re.match(r"^MED-\d{3,}$", t.ticket_id)
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", t.timestamp)
    assert t.summary.endswith(".")


def test_schema_strictness(tmp_path, monkeypatch):
    """Output contains exactly the seven required keys."""
    t = process_fresh(tmp_path, monkeypatch, "The theatre lights need replacing. - J. Nkosi (Theatre 2)")
    assert set(t.model_dump().keys()) == REQUIRED_KEYS


def test_billing_routes_to_finance_low(tmp_path, monkeypatch):
    raw = ('"I have a query about the invoice for a patient medical aid claim '
           'from last month." - T. Mokoena (Accounts)')
    t = process_fresh(tmp_path, monkeypatch, raw)
    assert t.category == "Finance"
    assert t.priority == "Low"


def test_leave_routes_to_hr_low(tmp_path, monkeypatch):
    raw = '"Nurse Dlamalo requests annual leave for December." - S. Dlamalo (ICU)'
    t = process_fresh(tmp_path, monkeypatch, raw)
    assert t.category == "HR"
    assert t.priority == "Low"


def test_aircon_routes_to_facilities_medium(tmp_path, monkeypatch):
    raw = '"The air conditioner in the staff room is not working." - P. Sithole (Admin Block)'
    t = process_fresh(tmp_path, monkeypatch, raw)
    assert t.category == "Operations"
    assert t.priority == "Medium"


def test_ventilator_icu_high(tmp_path, monkeypatch):
    raw = '"The ventilator in ICU bed 4 is showing an alarm and will not start." - Dr. Peters (ICU)'
    t = process_fresh(tmp_path, monkeypatch, raw)
    assert t.category == "IT & Medical Tech"
    assert t.priority == "High"


def test_persistence_appends_and_sequences(tmp_path, monkeypatch):
    monkeypatch.setattr("app.persistence.DB_PATH", tmp_path / "db.json")
    a = process_ticket("Server is down in the emergency department. - IT Ops (Emergency)")
    b = process_ticket("Monthly budget query. - Finance (Admin)")
    import json
    rows = json.loads((tmp_path / "db.json").read_text())
    assert len(rows) == 2
    assert a.ticket_id == "MED-001" and b.ticket_id == "MED-002"
    assert {r["ticket_id"] for r in rows} == {a.ticket_id, b.ticket_id}


def test_unit_classifier_prioritizer():
    cat, conf = classify("network telemetry disconnect server")
    assert cat == "IT & Medical Tech" and conf > 0.5
    assert prioritize("patient monitoring terminal keeps disconnecting telemetry sync", "Dr (Emergency Ward)") == "High"
    assert prioritize("invoice query for medical aid claim") == "Low"
