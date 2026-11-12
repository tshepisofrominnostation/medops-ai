"""Decision log and transparency note (Week 6).

A governance layer has to answer one question after the fact: "why did the system
do that?" This module writes an append-only record of every automated decision,
with the SIGNALS that drove it, so a reviewer can reconstruct the reasoning without
re-running anything.

Design choices that matter:
  * Append-only JSON Lines. Nothing is edited or deleted by this module.
  * NO message text is stored. Hospital messages can contain patient information, so
    a log that copied them would be a new privacy leak. We store category, priority,
    which signal groups fired, and a short hash for de-duplication, never the words.
  * Separate from the ticket. The ticket schema is a contract with the dashboard;
    governance metadata lives beside it, not inside it.
  * Failure to log never blocks triage. A broken log file must not cost a patient a
    routed ticket; the error is returned to the caller, not raised.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

LOG_PATH = Path(os.environ.get("MEDOPS_DECISION_LOG", "data/decisions.jsonl"))

# Mirrors the groups in app/prioritizer.py. Kept as names only; the log records
# WHICH group fired, not the matched words.
SIGNAL_GROUPS = {
    "clinical_context": ["emergency", "icu", "intensive care", "theatre", "operating room",
                         "telemetry", "patient monitor", "patient bay", "bedside monitor",
                         "patient monitoring", "patient care"],
    "clinical_equipment": ["ventilator", "defibrillator", "patient monitor", "monitoring terminal",
                           "telemetry", "infusion pump", "dialysis", "crash cart", "life support",
                           "bedside monitor", "oxygen"],
    "safety_hazard": ["fire", "flood", "gas leak", "power failure", "outage", "electrical hazard",
                      "spill", "generator", "water leak"],
    "urgency_words": ["down", "not working", "fail", "urgent", "immediately", "critical", "alarm",
                      "no power", "offline", "will not start", "stopped", "leaking"],
    "routine_words": ["invoice", "query", "leave request", "schedule", "booking", "question",
                      "monthly", "routine", "annual", "reminder", "planning"],
}

# Characters used by the languages the English-only lists cannot read.
_NON_ASCII_LETTERS = set("áàâäãåéèêëíìîïóòôöõúùûüñçšžœêôûäöü")
_AFRIKAANS_HINTS = (" die ", " nie ", " het ", " is ", " dit ", " van ", " en ", " 'n ")
_ZULU_HINTS = ("umshini", "iziguli", "ngokushesha", "usizo", "awusebenzi", " ya-", "ukuthi", "yini")


def signals_for(text: str) -> List[str]:
    t = text.lower()
    return [name for name, words in SIGNAL_GROUPS.items() if any(w in t for w in words)]


def language_hint(text: str) -> str:
    """A cheap hint, not a detector. Used only to flag rows for the bias review."""
    t = f" {text.lower()} "
    if any(h in t for h in _ZULU_HINTS):
        return "likely_isizulu"
    if sum(h in t for h in _AFRIKAANS_HINTS) >= 2 or any(c in _NON_ASCII_LETTERS for c in t):
        return "likely_afrikaans"
    return "english_or_unknown"


def build_record(message: str, ticket) -> dict:
    sig = signals_for(message)
    lang = language_hint(message)
    # No English urgency signal fired on a non-English message: exactly the pattern the
    # bias audit found, so it is flagged for a human to look at.
    review = lang != "english_or_unknown" and "urgency_words" not in sig
    return {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ticket_id": getattr(ticket, "ticket_id", None),
        "category": str(getattr(ticket, "category", "")),
        "priority": str(getattr(ticket, "priority", "")),
        "assigned_to": getattr(ticket, "assigned_to", None),
        "signals_fired": sig,
        "language_hint": lang,
        "message_fingerprint": hashlib.sha256(message.strip().lower().encode()).hexdigest()[:12],
        "message_length": len(message),
        "needs_bias_review": review,
        "note": ("Non-English wording and no urgency signal fired: priority may under-state "
                 "need. A person should confirm it." if review else ""),
    }


def log_decision(message: str, ticket, path: Optional[Path] = None) -> dict:
    """Append one record. Never raises: returns {"ok": False, "error": ...} on failure."""
    rec = build_record(message, ticket)
    target = Path(path) if path else LOG_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"ok": True, "record": rec}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "record": rec}


def read_log(path: Optional[Path] = None, limit: Optional[int] = None) -> List[dict]:
    target = Path(path) if path else LOG_PATH
    if not target.exists():
        return []
    rows = []
    with open(target, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue   # a torn last line must not hide the rest of the log
    return rows[-limit:] if limit else rows


def transparency_note(path: Optional[Path] = None) -> dict:
    """A plain-language summary of what the system has decided and where it is unsure."""
    rows = read_log(path)
    n = len(rows)
    if not n:
        return {"decisions": 0, "note": "No decisions have been logged yet."}
    flagged = [r for r in rows if r.get("needs_bias_review")]
    non_en = [r for r in rows if r.get("language_hint") != "english_or_unknown"]
    by_priority: Dict[str, int] = {}
    for r in rows:
        by_priority[r["priority"]] = by_priority.get(r["priority"], 0) + 1
    return {
        "decisions": n,
        "by_priority": by_priority,
        "non_english_messages": len(non_en),
        "flagged_for_bias_review": len(flagged),
        "note": (
            f"{n} automated decisions logged. {len(flagged)} were flagged because the message "
            f"looked non-English and no urgency signal fired, which is the pattern the bias "
            f"audit found under-prioritises need. The log stores no message text, only "
            f"category, priority, which signal groups fired and a short fingerprint."),
        "limits": ("Language is a cheap hint, not a detector, so counts are approximate. "
                   "The flag asks a person to look; it does not change the priority."),
    }
