"""Smart Classification Engine — weighted keyword scoring over four departments.

Rule-based by design for Sprint 1: deterministic, testable, zero API cost,
no PHI leaving the building. The classifier interface matches the planned
LLM upgrade (classify(message) -> category, confidence) so the backend can
swap engines without touching the pipeline.
"""
import re
from .models import Category

CATEGORY_KEYWORDS: dict[Category, dict[str, int]] = {
    "IT & Medical Tech": {
        "network": 3, "server": 3, "terminal": 3, "telemetry": 3, "monitoring": 2,
        "monitor": 2, "disconnect": 2, "wifi": 3, "software": 2, "login": 2,
        "emr": 3, "database": 3, "computer": 2, "system": 1, "connectivity": 2,
        "bedside monitor": 3, "scheduling": 2, "synch": 1, "sync": 1, "reboot": 2, "crash": 2, "offline": 2, "workstation": 2,
        "ventilator": 3, "defibrillator": 3, "infusion pump": 3, "dialysis": 3,
        "crash cart": 3, "x-ray": 3, "scanner": 2, "eeg": 3, "ecg": 3,
    },
    "HR": {
        "leave": 3, "shift": 2, "contract": 2, "recruitment": 3, "hiring": 3,
        "onboarding": 3, "payslip": 3, "overtime": 2, "nurse": 2, "staffing": 2, "roster": 2, "sabbatical": 2, "grievance": 2,
        "disciplinary": 2, "training": 1, "resignation": 3, "payroll": 2, "hr": 3,
        "overtime": 2, "personnel": 2,
    },
    "Finance": {
        "invoice": 3, "billing": 3, "payment": 3, "claim": 3, "budget": 3,
        "pay ": 3,
        "purchase": 2, "reimbursement": 3, "tender": 2, "expense": 2,
        "accounts": 2, "debtors": 3, "medical aid": 3, "tariff": 2, "finance": 3,
        "overcharge": 2, "tender": 3,
    },
    "Operations": {
        "light": 2, "kitchen": 2, "cold room": 3, "bulb": 2, "aircon": 3, "air conditioning": 3, "water": 2, "leak": 3,
        "generator": 3, "door": 1, "elevator": 2, "lift": 2, "cleaning": 2,
        "plumbing": 3, "maintenance": 3, "ceiling": 2, "paint": 2, "refuse": 2,
        "bed ": 1, "garden": 2, "kitchen": 2,
    },
}

DEFAULT_CATEGORY: Category = "Operations"  # operations catch-all for unmatched text


def classify(message: str) -> tuple[Category, float]:
    """Return (category, confidence). Confidence = top score share of total."""
    text = message.lower()
    scores = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        s = 0
        for kw, weight in kws.items():
            if kw in text:
                s += weight * (1 + text.count(kw) - 1)  # repeat mentions add up
        scores[cat] = s
    total = sum(scores.values())
    if total == 0:
        return DEFAULT_CATEGORY, 0.0
    best = max(scores, key=scores.get)
    return best, round(scores[best] / total, 3)
