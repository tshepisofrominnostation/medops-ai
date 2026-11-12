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


def test_webhook_payload_carries_full_ticket_json(monkeypatch):
    seen = {}

    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(req, timeout=0):
        seen["body"] = json.loads(req.data)
        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    rec = {"ticket_id": "MED-20", "priority": "High", "category": "HR",
           "assigned_to": "HR Duty Officer", "summary": "s", "sender": "A", "status": "Open"}
    notify._send_webhook("https://example.test/hook", rec)
    assert seen["body"]["ticket"] == rec


def test_per_team_route_overrides_default(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "ALERT_LOG", tmp_path / "alerts.log")
    urls = []
    monkeypatch.setattr(notify, "_send_webhook", lambda url, rec: urls.append(url) or "webhook 200")
    monkeypatch.setenv("MEDOPS_ALERTS", "1")
    monkeypatch.setenv("MEDOPS_WEBHOOK_URL", "https://default.test/hook")
    monkeypatch.setenv("MEDOPS_ALERT_ROUTES",
                       json.dumps({"HR Duty Officer": {"webhook": "https://hr.test/hook"}}))
    notify.notify_assignment({"ticket_id": "MED-21", "assigned_to": "HR Duty Officer"})
    notify.notify_assignment({"ticket_id": "MED-22", "assigned_to": "IT Service Desk"})
    assert urls == ["https://hr.test/hook", "https://default.test/hook"]


def test_bad_routes_json_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "ALERT_LOG", tmp_path / "alerts.log")
    monkeypatch.setenv("MEDOPS_ALERT_ROUTES", "{not json")
    assert notify._route_for({"assigned_to": "x"}) == {}
