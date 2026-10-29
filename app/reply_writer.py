"""Core Reply Writer - drafts the department response for each classified ticket.

Two engines behind one interface:
- TemplateReplyEngine: deterministic, offline, tone-controlled drafting. Always available.
- LLMReplyEngine: optional provider (OpenAI-compatible, JSON mode, hard timeout).

ReplyWriter guarantees a safe draft: when the LLM is not configured, or times
out, errors, or produces unsafe output, it falls back to the template engine.
Medical-advice guardrail: no draft may contain diagnosis, medication or dosage
language; violations are rejected and routed to the fallback path.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .models import TicketOut
from .parser import extract_location
from .tone_detector import detect_tone

Tone = Literal["concise-professional", "warm-administrative"]


class DraftedReply(BaseModel):
    """Structured output contract for generated replies."""
    ticket_id: str
    tone: Tone
    reply_body: str = Field(..., min_length=20)
    safety_flags: list[str]
    generated_by: str
    model: Optional[str] = None
    # Detected register of the incoming message (Xoli's tone signal, team PR #25).
    sender_tone: Optional[str] = None


# Words that must NEVER appear in a generated reply: the assistant handles
# operations, not medicine. Matched case-insensitively as substrings.
MEDICAL_ADVICE_BAN = [
    "diagnos", "dosage", "dose of", " mg ", "prescrib", "treatment plan",
    "medication", "antibiotic", "paracetamol", "clinical advice", "medical advice",
]


def contains_medical_advice(text: str) -> Optional[str]:
    """Return the first banned pattern found, or None if the text is safe."""
    low = text.lower()
    for pattern in MEDICAL_ADVICE_BAN:
        if pattern in low:
            return pattern
    return None


def safety_flags_for(ticket: TicketOut) -> list[str]:
    flags = ["standard-queue"]
    if ticket.priority == "High":
        flags = ["escalated-on-call"]
        if ticket.category == "IT & Medical Tech":
            flags.append("clinical-equipment-escalation")
        if ticket.category == "Operations":
            flags.append("area-safety-protocol")
    return flags


class TemplateReplyEngine:
    """Deterministic drafting: fixed structures, tone by priority, category actions."""

    URGENT = {
        "IT & Medical Tech": (
            "{assigned} has been activated for {tid} at {loc}. Do not use the affected "
            "equipment for patient care until it is cleared by biomedical engineering. "
            "Reference {tid} and escalate to the on-call coordinator immediately if the "
            "situation changes."
        ),
        "Operations": (
            "{assigned} is responding to {tid} at {loc}. Close off the affected area and "
            "keep staff clear until the duty manager confirms it is safe. Escalate "
            "immediately if anyone is at risk."
        ),
        "Finance": (
            "{assigned} is processing {tid} as an urgent payment. Confirm the supplier "
            "hold in writing while we complete the release. Escalation line: Finance "
            "Duty Officer."
        ),
        "HR": (
            "{assigned} is sourcing cover now for {tid}. The relevant manager will be "
            "called with confirmation within the hour. Do not leave the shift roster "
            "unconfirmed before handover."
        ),
    }

    WARM_ACTIONS = {
        "IT & Medical Tech": "restore the affected system and confirm your access",
        "Operations": "schedule the maintenance visit and confirm the crew",
        "Finance": "review the account and confirm the outcome",
        "HR": "process your request and confirm the details with you",
    }

    def draft(self, ticket: TicketOut) -> DraftedReply:
        if ticket.priority == "High":
            body = self._urgent(ticket)
            tone = "concise-professional"
        else:
            body = self._routine(ticket)
            tone = "warm-administrative"
        return DraftedReply(
            ticket_id=ticket.ticket_id,
            tone=tone,
            reply_body=body,
            safety_flags=safety_flags_for(ticket),
            generated_by="template",
        )

    def _urgent(self, t: TicketOut) -> str:
        loc = extract_location(t.summary) or "the affected area"
        return self.URGENT[t.category].format(
            assigned=t.assigned_to, tid=t.ticket_id, loc=loc
        )

    def _routine(self, t: TicketOut) -> str:
        window = "one working day" if t.priority == "Medium" else "two working days"
        opener = (
            "Thank you for reaching out."
            if detect_tone(t.summary) == "friendly"
            else "Thank you for logging this."
        )
        return (
            f"{opener} {t.assigned_to} has received {t.ticket_id} and will "
            f"{self.WARM_ACTIONS[t.category]}. Expect an update within {window}; you will "
            "get written confirmation once it is done. Please reply to this ticket with "
            "any extra detail that will help the team."
        )


class LLMReplyEngine:
    """Optional OpenAI-compatible provider with JSON-mode structured output.

    Configured via environment variables:
      MEDOPS_LLM_BASE_URL, MEDOPS_LLM_API_KEY, MEDOPS_LLM_MODEL,
      MEDOPS_LLM_TIMEOUT (seconds, default 8).
    draft() returns None on ANY failure (timeout, HTTP error, bad JSON,
    schema mismatch, medical-advice violation) - never raises, so the
    ReplyWriter fallback path is always safe.
    """
    import os as _os  # noqa: allow env reads at init

    SYSTEM_PROMPT = (
        "You draft department replies for hospital operational tickets. Output ONLY a "
        "JSON object with keys: reply_body (string), tone (string). "
        "Tone rules: priority High -> 'concise-professional': at most 60 words, "
        "instruction-focused, one immediate action plus an escalation path. "
        "Priority Medium or Low -> 'warm-administrative': acknowledge, inform, reassure, "
        "give a timeframe of one or two working days, at most 90 words. "
        "Safety: never include diagnosis, medication, dosage or any medical advice; "
        "never invent names, numbers or procedures. Address the sender professionally."
    )

    def __init__(self):
        import os
        self.base_url = os.environ.get("MEDOPS_LLM_BASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("MEDOPS_LLM_API_KEY", "")
        self.model = os.environ.get("MEDOPS_LLM_MODEL", "gpt-4o-mini")
        self.timeout = float(os.environ.get("MEDOPS_LLM_TIMEOUT", "8"))
        self.configured = bool(self.base_url and self.api_key)

    def draft(self, ticket: TicketOut) -> Optional[DraftedReply]:
        if not self.configured:
            return None
        try:
            import json as _json
            import urllib.request
            payload = _json.dumps({
                "model": self.model,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Ticket {ticket.ticket_id}\nCategory: {ticket.category}\n"
                        f"Priority: {ticket.priority}\nSender: {ticket.sender}\n"
                        f"Issue: {ticket.summary}\nDraft the department reply now."
                    )},
                ],
            }).encode()
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=payload,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = _json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            parsed = _json.loads(content)
            body = parsed["reply_body"]
            if parsed.get("tone") != ("concise-professional" if ticket.priority == "High"
                                     else "warm-administrative"):
                return None  # tone contract violated - reject
            if contains_medical_advice(body):
                return None  # safety guardrail - reject and fall back
            return DraftedReply(
                ticket_id=ticket.ticket_id,
                tone=parsed["tone"],
                reply_body=body,
                safety_flags=safety_flags_for(ticket),
                generated_by="llm",
                model=self.model,
            )
        except Exception:
            return None  # timeout, HTTP error, malformed JSON, schema error


class ReplyWriter:
    """Facade: LLM when configured and safe; template otherwise. Never fails."""

    def __init__(self):
        self.template = TemplateReplyEngine()
        self.llm = LLMReplyEngine()

    def draft(self, ticket: TicketOut) -> DraftedReply:
        if self.llm.configured:
            reply = self.llm.draft(ticket)
            if reply is not None:
                return self._stamp(reply, ticket)
            fallback = self.template.draft(ticket)
            fallback.generated_by = "template (llm-fallback)"
            return self._stamp(fallback, ticket)
        return self._stamp(self.template.draft(ticket), ticket)

    @staticmethod
    def _stamp(reply: DraftedReply, ticket: TicketOut) -> DraftedReply:
        """Attach the detected sender tone to every draft, whichever engine wrote it."""
        if reply.sender_tone is None:
            reply.sender_tone = detect_tone(ticket.summary)
        return reply
