"""Serialise the engine's knowledge so the browser can run it without duplicating it.

app/ keeps its keyword weights, routing table and sender regexes as Python constants.
The published page needs exactly those values. Rather than retype them into JavaScript
(which is how two copies drift apart), build_pages.py and the parity checker both call
build_bundle() here and get a JSON-ready copy straight from the importing modules.

Anything that is control flow is ported by hand in web/engine.js; anything that is
knowledge passes through this file.
"""
import re

from app.assigner import ASSIGN
from app.classifier import CATEGORY_KEYWORDS, DEFAULT_CATEGORY
from app.parser import FROM_RE, SIGNED_RE
from app.prioritizer import (
    CLINICAL_CONTEXT,
    CLINICAL_EQUIPMENT,
    ROUTINE,
    SAFETY,
    STAFFING_CRITICAL,
    URGENT,
)


def _flags(pattern: re.Pattern) -> str:
    """Python re flags -> JavaScript flags."""
    out = ""
    if pattern.flags & re.IGNORECASE:
        out += "i"
    if pattern.flags & re.MULTILINE:
        out += "m"
    if pattern.flags & re.DOTALL:
        out += "s"
    return out


def build_bundle() -> dict:
    return {
        "category_keywords": {cat: dict(words) for cat, words in CATEGORY_KEYWORDS.items()},
        "default_category": DEFAULT_CATEGORY,
        "assign": {cat: dict(row) for cat, row in ASSIGN.items()},
        "priority": {
            "clinical_context": list(CLINICAL_CONTEXT),
            "clinical_equipment": list(CLINICAL_EQUIPMENT),
            "safety": list(SAFETY),
            "urgent": list(URGENT),
            "staffing_critical": list(STAFFING_CRITICAL),
            "routine": list(ROUTINE),
            # mirrors the thresholds in prioritizer.prioritize
            "high_threshold": 5,
            "medium_threshold": 2,
        },
        "parser": {
            "from": FROM_RE.pattern,
            "from_flags": _flags(FROM_RE),
            "signed": SIGNED_RE.pattern,
            "signed_flags": _flags(SIGNED_RE),
        },
        "summary": {"max_words": 22},
    }
