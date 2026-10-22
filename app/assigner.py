"""Routing table — category + priority -> owning team/role."""
from .models import Category, Priority

ASSIGN: dict[Category, dict[Priority, str]] = {
    "IT & Medical Tech": {
        "High": "IT & Biomedical Engineering on-call",
        "Medium": "IT Service Desk",
        "Low": "IT Service Desk",
    },
    "HR": {"High": "HR Duty Officer", "Medium": "HR Business Partner", "Low": "HR Admin Team"},
    "Finance": {"High": "Finance Duty Officer", "Medium": "Finance Operations Team", "Low": "Finance Operations Team"},
    "Facilities": {"High": "Facilities Emergency Response", "Medium": "Facilities & Maintenance Team", "Low": "Facilities & Maintenance Team"},
}


def assign(category: Category, priority: Priority) -> str:
    return ASSIGN[category][priority]
