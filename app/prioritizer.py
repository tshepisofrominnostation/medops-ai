"""Dynamic priority assignment — clinical context beats administrative routine.

Scoring: safety hazards and clinical equipment failures escalate to High;
routine admin language de-escalates to Low. Sender department (e.g.
Emergency Ward) contributes context, not just the message body.
"""
from .models import Priority

CLINICAL_CONTEXT = ["emergency", "icu", "intensive care", "theatre", "operating room",
                    "telemetry", "patient monitor", "patient bay", "ward", "bay "]
CLINICAL_EQUIPMENT = ["ventilator", "defibrillator", "patient monitor", "monitoring terminal",
                      "telemetry", "infusion pump", "dialysis", "crash cart", "life support"]
SAFETY = ["fire", "flood", "gas leak", "power failure", "outage", "electrical hazard", "spill"]
URGENT = ["down", "not working", "fail", "keeps disconnect", "urgent", "immediately",
          "critical", "alarm", "no power", "offline", "will not start", "stopped"]
ROUTINE = ["invoice", "query", "leave request", "schedule", "booking", "question",
           "monthly", "routine", "annual", "reminder", "planning"]


def prioritize(message: str, sender: str = "") -> Priority:
    text = f"{message} {sender}".lower()
    score = 0
    if any(k in text for k in CLINICAL_CONTEXT): score += 3
    if any(k in text for k in CLINICAL_EQUIPMENT): score += 3
    if any(k in text for k in SAFETY): score += 4
    if any(k in text for k in URGENT): score += 2
    if any(k in text for k in ROUTINE): score -= 2
    if "high" in text or "emergency" in text: score += 1
    if score >= 5:
        return "High"
    if score >= 2:
        return "Medium"
    return "Low"
