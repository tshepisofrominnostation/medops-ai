"""S4-1: alerts are off by default, log when dry, and never break triage."""
import json, os
from app import notify


def test_disabled_by_default_logs_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "ALERT_LOG", tmp_path / "alerts.log")
    monkeypatch.delenv("MEDOPS_ALERTS", raising=False)
    r = notify.notify_assignment({"ticket_id": "MED-9", "priority": "High", "category": "HR"})
    assert r["sent"] is False and r["transport"] == "dry-run"
    assert (tmp_path / "alerts.log").exists()


def test_enabled_without_transport_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "ALERT_LOG", tmp_path / "alerts.log")
    monkeypatch.setenv("MEDOPS_ALERTS", "1")
    monkeypatch.delenv("MEDOPS_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("MEDOPS_SMTP_HOST", raising=False)
    r = notify.notify_assignment({"ticket_id": "MED-10"})
    assert r["sent"] is False and "no transport" in r["reason"]


def test_webhook_failure_is_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "ALERT_LOG", tmp_path / "alerts.log")
    monkeypatch.setenv("MEDOPS_ALERTS", "1")
    monkeypatch.setenv("MEDOPS_WEBHOOK_URL", "http://127.0.0.1:9/nothing")
    r = notify.notify_assignment({"ticket_id": "MED-11"})
    assert r["sent"] is False and r["transport"] == "error"


def test_webhook_success_records_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "ALERT_LOG", tmp_path / "alerts.log")
    monkeypatch.setattr(notify, "_send_webhook", lambda url, rec: "webhook 200")
    monkeypatch.setenv("MEDOPS_ALERTS", "1")
    monkeypatch.setenv("MEDOPS_WEBHOOK_URL", "https://example.test/hook")
    r = notify.notify_assignment({"ticket_id": "MED-12", "priority": "High"})
    assert r["sent"] is True and r["transport"] == "webhook"
    line = json.loads((tmp_path / "alerts.log").read_text().strip())
    assert line["ticket_id"] == "MED-12"
