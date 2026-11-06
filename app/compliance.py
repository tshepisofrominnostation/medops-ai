"""Compliance screen for generated replies (S3-2).

A hospital cannot send a drafted reply that leaks patient identifiers or gives
clinical advice. This module screens text before it is ever sent and returns
explicit flags, so the pipeline can block rather than trust.

Severity:
  block  - must not be sent (identifiers, clinical advice, financial promises)
  review - a human should read it first (soft patterns)
"""
import re
from typing import Optional

# --- identifier patterns (South African context) -------------------------------
IDENTIFIERS = [
    ("sa_id_number", r"\b\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{7}\b",
     "block", "Looks like a South African ID number"),
    ("phone_number", r"\b(?:\+27|0)\s?\d{2}[\s-]?\d{3}[\s-]?\d{4}\b",
     "block", "Looks like a phone number"),
    ("email", r"[\w.+-]+@[\w-]+\.[\w.]{2,}", "block", "Email address"),
    ("medical_aid", r"\b(?:medical aid|scheme)\s*(?:no|number|#)?\s*[:]?\s*\d{5,}\b",
     "block", "Medical aid membership number"),
    ("bank_card", r"\b(?:\d[ -]?){13,19}\b", "block", "Long digit string, possible card number"),
]

# --- clinical advice: the platform triages, it does not diagnose ----------------
CLINICAL = [
    ("diagnosis", r"\byou (?:have|are suffering from|likely have)\b",
     "block", "States a diagnosis"),
    ("prescription", r"\b(?:take|increase|reduce|stop taking)\s+\d+\s?(?:mg|ml|tablets?|capsules?)\b",
     "block", "Gives a dosage instruction"),
    ("medication_advice", r"\b(?:you should take|i recommend (?:taking|you take))\b",
     "block", "Recommends medication"),
    ("reassurance", r"\b(?:nothing to worry about|you are fine|no need to see a doctor)\b",
     "review", "Reassures about a health outcome"),
]

# --- promises the platform cannot keep -----------------------------------------
PROMISES = [
    ("payment_promise", r"\b(?:refund|payment|money)\b.{0,30}\b(?:guaranteed|will be paid today|immediately)\b",
     "review", "Promises a payment outcome"),
    ("absolute", r"\b(?:guaranteed|100% safe|never fails)\b", "review", "Absolute claim"),
]

RULES = IDENTIFIERS + CLINICAL + PROMISES


def screen(text: str) -> dict:
    """Screen one drafted reply. Returns a verdict plus every flag found."""
    body = text or ""
    flags = []
    for name, pattern, severity, why in RULES:
        for m in re.finditer(pattern, body, flags=re.IGNORECASE):
            flags.append({
                "rule": name,
                "severity": severity,
                "why": why,
                "match": m.group(0)[:60],
                "span": [m.start(), m.end()],
            })
    blocked = [f for f in flags if f["severity"] == "block"]
    review = [f for f in flags if f["severity"] == "review"]
    return {
        "passed": not blocked,
        "verdict": "blocked" if blocked else ("review" if review else "clean"),
        "counts": {"block": len(blocked), "review": len(review)},
        "flags": flags,
    }


def screen_or_raise(text: str) -> str:
    """Return the text if it passes, else raise ValueError listing the rules hit."""
    result = screen(text)
    if not result["passed"]:
        names = sorted({f["rule"] for f in result["flags"] if f["severity"] == "block"})
        raise ValueError(f"reply blocked by compliance screen: {', '.join(names)}")
    return text
