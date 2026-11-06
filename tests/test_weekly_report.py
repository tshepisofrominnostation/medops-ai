"""S2-3 weekly reporting: summaries, departments, SLA compliance and the PDF.

The feature arrived as a pull request that carried its own copy of the SLA targets
and read `responded_at`. Both are reconciled here: targets come from
app/lifecycle.py (one definition for dashboard, report and page), and the response
timestamp is `first_response_at` with `responded_at` accepted for data written
before the lifecycle module existed.
"""
from app import lifecycle
from app.weekly_report import (
    SLA_TARGETS,
    build_department_summary,
    build_sla_summary,
    build_weekly_summary,
    generate_weekly_pdf,
)

ROWS = [
    {
        "ticket_id": "MED-101",
        "timestamp": "2026-11-02T09:00:00+02:00",
        "category": "IT & Medical Tech",
        "priority": "High",
        "assigned_to": "IT Service Desk",
    },
    {
        "ticket_id": "MED-102",
        "timestamp": "2026-11-02T10:00:00+02:00",
        "category": "HR",
        "priority": "Low",
        "assigned_to": "HR Admin Team",
    },
    {
        "ticket_id": "MED-103",
        "timestamp": "2026-11-03T09:00:00+02:00",
        "category": "Finance",
        "priority": "Medium",
        "assigned_to": "Finance Duty Officer",
    },
]


def test_department_summary_counts_tickets():
    result = build_department_summary(ROWS)
    assert result["IT Service Desk"]["total_tickets"] == 1
    assert result["HR Admin Team"]["total_tickets"] == 1
    assert result["Finance Duty Officer"]["total_tickets"] == 1


def test_department_summary_groups_priorities():
    result = build_department_summary(ROWS)
    assert result["IT Service Desk"]["by_priority"] == {"High": 1}
    assert result["HR Admin Team"]["by_priority"] == {"Low": 1}


def test_unassigned_tickets_are_included():
    rows = ROWS + [{"ticket_id": "MED-104", "timestamp": "2026-11-03T09:00:00+02:00",
                    "category": "Operations", "priority": "Low", "assigned_to": ""}]
    result = build_department_summary(rows)
    assert result["Unassigned"]["total_tickets"] == 1


def test_sla_targets_are_defined_for_all_priorities():
    """One source of truth: the values must be the ones lifecycle publishes."""
    assert set(SLA_TARGETS) == {"High", "Medium", "Low"}
    for priority in ("High", "Medium", "Low"):
        assert SLA_TARGETS[priority]["response_minutes"] == lifecycle.SLA_TARGET_MINUTES[priority]
        assert SLA_TARGETS[priority]["resolution_minutes"] == lifecycle.RESOLUTION_TARGET_MINUTES[priority]
    assert SLA_TARGETS["High"]["response_minutes"] == 15
    assert SLA_TARGETS["High"]["resolution_minutes"] == 240
    assert SLA_TARGETS["Medium"]["response_minutes"] == 120
    assert SLA_TARGETS["Low"]["response_minutes"] == 480


def test_sla_without_actual_timestamps_is_not_tracked():
    result = build_sla_summary([ROWS[0]])
    assert result["High"]["response_compliance"] is None
    assert result["High"]["resolution_compliance"] is None
    assert result["High"]["response_tracked"] == 0
    # An unanswered ticket is never a zero-minute response.
    assert result["High"]["response_met"] == 0


def test_sla_compliance_uses_actual_timestamps():
    rows = [{
        "ticket_id": "MED-105",
        "timestamp": "2026-11-02T09:00:00+02:00",
        "first_response_at": "2026-11-02T09:10:00+02:00",
        "resolved_at": "2026-11-02T11:00:00+02:00",
        "priority": "High",
    }]
    result = build_sla_summary(rows)
    assert result["High"]["response_tracked"] == 1
    assert result["High"]["response_met"] == 1
    assert result["High"]["response_compliance"] == 100.0
    assert result["High"]["resolution_tracked"] == 1
    assert result["High"]["resolution_met"] == 1
    assert result["High"]["resolution_compliance"] == 100.0


def test_legacy_responded_at_is_still_measured():
    """Tickets exported before the lifecycle module wrote `responded_at`."""
    rows = [{
        "ticket_id": "MED-107",
        "timestamp": "2026-11-02T09:00:00+02:00",
        "responded_at": "2026-11-02T09:05:00+02:00",
        "priority": "High",
    }]
    result = build_sla_summary(rows)
    assert result["High"]["response_tracked"] == 1
    assert result["High"]["response_met"] == 1


def test_sla_missed_target_is_not_compliant():
    rows = [{
        "ticket_id": "MED-106",
        "timestamp": "2026-11-02T09:00:00+02:00",
        "first_response_at": "2026-11-02T10:00:00+02:00",
        "priority": "High",
    }]
    result = build_sla_summary(rows)
    assert result["High"]["response_tracked"] == 1
    assert result["High"]["response_met"] == 0
    assert result["High"]["response_compliance"] == 0.0


def test_weekly_summary_filters_date_range():
    result = build_weekly_summary(ROWS, start="2026-11-02", end="2026-11-02")
    assert result["analytics"]["total_tickets"] == 2
    assert result["departments"]["IT Service Desk"]["total_tickets"] == 1
    assert result["departments"]["HR Admin Team"]["total_tickets"] == 1
    assert "Finance Duty Officer" not in result["departments"]


def test_weekly_summary_contains_required_sections():
    result = build_weekly_summary(ROWS)
    assert set(("analytics", "departments", "sla", "period", "tickets")) <= set(result)


def test_pdf_generation_returns_valid_pdf():
    pdf = generate_weekly_pdf(ROWS)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000


def test_empty_history_can_generate_pdf():
    """A quiet week still produces a report, and it must not claim 0-minute responses."""
    pdf = generate_weekly_pdf([])
    assert pdf.startswith(b"%PDF-")
    summary = build_weekly_summary([])
    assert summary["analytics"]["total_tickets"] == 0
    assert summary["sla"]["High"]["response_compliance"] is None


def test_endpoints_serve_the_weekly_report():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    data = client.get("/report/weekly.json")
    assert data.status_code == 200
    body = data.json()
    assert {"period", "analytics", "departments", "sla"} <= set(body)

    pdf = client.get("/report/weekly.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")


def test_bad_dates_are_rejected_with_a_reason():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.get("/report/weekly.json?start=2026-13-01").status_code == 400
    backwards = client.get("/report/weekly.json?start=2026-11-05&end=2026-11-01")
    assert backwards.status_code == 400
    assert "after" in backwards.json()["detail"].lower(), backwards.json()["detail"]
