"""S2-3: the weekly PDF report renders real numbers and scopes by department."""
from app.report import build_report_data, render_html, write_report
import os


def _recs():
    return [
        {"ticket_id": "MED-1", "category": "HR", "priority": "High",
         "assigned_to": "HR Admin Team", "timestamp": "2026-11-02T09:00:00+00:00"},
        {"ticket_id": "MED-2", "category": "HR", "priority": "Low",
         "assigned_to": "HR Admin Team", "timestamp": "2026-11-02T11:00:00+00:00"},
        {"ticket_id": "MED-3", "category": "Operations", "priority": "Medium",
         "assigned_to": "Facilities Team", "timestamp": "2026-11-03T08:00:00+00:00"},
    ]


def test_html_contains_real_counts():
    html = render_html(build_report_data(_recs()))
    assert "3" in html and "Weekly operations summary" in html
    assert "All departments" in html
    assert "66.7%" in html          # two of three tickets are HR


def test_department_scope_filters():
    d = build_report_data(_recs(), "Facilities Team")
    assert d["total_tickets"] == 1
    assert d["department_filter"] == "Facilities Team"


def test_report_files_written(tmp_path):
    info = write_report(_recs(), str(tmp_path / "summary.pdf"))
    assert os.path.exists(info["html"])
    assert info["tickets"] == 3
    if info["pdf"]:
        assert os.path.getsize(info["pdf"]) > 500
