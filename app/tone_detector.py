"""Sender-tone detection: the register of the incoming message itself.

Adapted from Xoli's contribution in team PR #25 (feature/response-generator).
Kept as its own module so the reply writer can use the signal without
depending on her template generator, which the reply writer supersedes.

This is deliberately separate from ticket PRIORITY: priority answers "how
urgent is this for the hospital", tone answers "how is the sender writing".
A polite message can still be an emergency.
"""
import re
from typing import Literal

Tone = Literal["formal", "friendly", "urgent"]

URGENT_INDICATORS = (
    "urgent", "urgently", "immediately", "emergency", "critical",
    "life-threatening", "not working", "will not start", "down",
    "danger", "unsafe", "asap",
)

FRIENDLY_INDICATORS = (
    "hi", "hello", "hey", "please help", "could you please",
    "thank you", "thanks", "i would appreciate",
)


_URGENT_PATTERNS = [re.compile(r"\b" + re.escape(i) + r"\b") for i in URGENT_INDICATORS]
_FRIENDLY_PATTERNS = [re.compile(r"\b" + re.escape(i) + r"\b") for i in FRIENDLY_INDICATORS]


def detect_tone(message: str) -> Tone:
    """Return the detected register of the message: urgent, friendly, or formal.

    Urgency takes precedence: a warm greeting should never soften an emergency.

    Matching uses word boundaries, not raw substrings: 'hi' must not match
    inside 'this', and 'down' must not match inside 'download'.
    """
    text = message.lower()
    if any(p.search(text) for p in _URGENT_PATTERNS):
        return "urgent"
    if any(p.search(text) for p in _FRIENDLY_PATTERNS):
        return "friendly"
    return "formal"
