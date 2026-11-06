"""Week 3 and Week 4 API surface: queue work, insights, reports."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDOPS_DB_PATH", str(tmp_path / "tickets.json"))
    import app.persistence as persistence
    monkeypatch.setattr(persistence, "DB_PATH", tmp_path / "tickets.json")
    c = TestClient(app)
    for msg in ('"The patient monitoring terminal in Bay 3 keeps disconnecting." '
                '- Dr. S. Khumalo (Emergency Ward)',
                '"The aircon in Theatre 2 is not working." - Dr. Naidoo (Theatre 2)',
                '"My payslip shows the wrong overtime hours." - Nurse K. Zulu (Ward 2)'):
        r = c.post("/tickets", json={"message": msg})
        assert r.status_code == 200, r.text
    return c


def test_health_reports_the_real_capabilities(client):
    h = client.get("/health").json()
    assert h["version"] == "1.2.0"
    assert h["semantic_classifier"]["loaded"] is True
    assert h["statuses"] == ["Open", "In Progress", "Resolved"]
    assert h["narrative"] in ("llm", "deterministic")


def test_new_tickets_start_open_with_no_response_time(client):
    rows = client.get("/tickets").json()
    assert len(rows) == 3
    assert all(r["status"] == "Open" for r in rows)
    assert all(r["response_minutes"] is None for r in rows)


def test_full_lifecycle_through_the_api(client):
    tid = client.get("/tickets").json()[0]["ticket_id"]
    started = client.post(f"/tickets/{tid}/status", json={"status": "In Progress"}).json()
    assert started["status"] == "In Progress"
    assert started["response_minutes"] is not None
    done = client.post(f"/tickets/{tid}/status", json={"status": "Resolved"}).json()
    assert done["status"] == "Resolved"
    assert done["resolution_minutes"] is not None
    assert done["sla_met"] in (True, False)


def test_get_one_ticket_and_404(client):
    tid = client.get("/tickets").json()[0]["ticket_id"]
    assert client.get(f"/tickets/{tid}").json()["ticket_id"] == tid
    assert client.get("/tickets/MED-999").status_code == 404


def test_status_is_validated(client):
    tid = client.get("/tickets").json()[0]["ticket_id"]
    assert client.post(f"/tickets/{tid}/status", json={"status": "Done"}).status_code == 400
    assert client.post(f"/tickets/{tid}/status", json={}).status_code == 400
    assert client.post("/tickets/MED-999/status", json={"status": "Open"}).status_code == 404


def test_queue_filters(client):
    assert len(client.get("/tickets", params={"status": "Open"}).json()) == 3
    assert len(client.get("/tickets", params={"category": "HR"}).json()) == 1
    assert len(client.get("/tickets", params={"priority": "High"}).json()) >= 1
    assert client.get("/tickets", params={"status": "Resolved"}).json() == []


def test_insights_endpoint_returns_findings_and_a_narrative(client):
    body = client.get("/insights").json()
    for key in ("scope", "window", "analytics", "findings", "narrative", "limits"):
        assert key in body
    assert body["narrative"]["text"]
    assert body["narrative"]["engine"] in ("llm", "deterministic")
    assert body["findings"]


def test_insights_accepts_a_department_scope(client):
    dept = client.get("/tickets").json()[0]["assigned_to"]
    body = client.get("/insights", params={"department": dept}).json()
    assert body["scope"] == dept
    assert body["analytics"]["total_tickets"] >= 1


def test_response_time_appears_in_analytics_once_a_ticket_is_worked(client):
    before = client.get("/analytics").json()["response_time"]["measured_tickets"]
    tid = client.get("/tickets").json()[0]["ticket_id"]
    client.post(f"/tickets/{tid}/status", json={"status": "In Progress"})
    after = client.get("/analytics").json()["response_time"]
    assert after["measured_tickets"] == before + 1
    assert after["median_minutes"] is not None


def test_report_json_carries_the_week4_payload(client):
    body = client.get("/report").json()
    for key in ("scope", "window", "analytics", "findings", "narrative", "limits"):
        assert key in body
    assert "Review before circulating" in body["narrative"]["disclosure"]


def test_report_pdf_is_a_pdf(client):
    r = client.get("/report.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"


def test_report_csv_is_parseable(client):
    import csv, io
    r = client.get("/report.csv")
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["section", "metric", "value"]
    assert any(row[0] == "totals" and row[1] == "tickets" for row in rows[1:])


def test_check_category_returns_the_second_opinion(client):
    body = client.post("/check/category", json={"message": "The lift is stuck between floors"}).json()
    assert body["rule_category"] == "Operations"
    assert "semantic_category" in body and "needs_review" in body
    assert client.post("/check/category", json={}).status_code == 400
