"""Week 2: tone control (formal / friendly / urgent).

The interesting test is not "the strings differ". It is that a tone changes the
courtesy and never the facts: same ticket id, same team, same response window.
A friendlier sentence must not become a shorter promise.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import TicketOut
from app.reply_writer import ReplyWriter

MSG = "The ventilator in ICU will not start, alarm is going, patients waiting. Dr Khumalo"


def _ticket():
    return TicketOut(
        ticket_id="MED-777", timestamp="2026-11-13T08:00:00+02:00",
        sender="ICU", category="IT & Medical Tech", priority="High",
        summary="Ventilator in ICU will not start, alarm going", assigned_to="Biomed",
    )


def test_all_three_tones_are_producible_and_labelled():
    w = ReplyWriter()
    labels = {}
    for tone in ("formal", "friendly", "urgent"):
        r = w.draft(_ticket(), tone)
        labels[tone] = r.tone
        assert r.reply_body.strip()
    assert len(set(labels.values())) == 3, f"tones are not distinct: {labels}"


def test_tone_never_changes_the_facts():
    w = ReplyWriter()
    bases = {tone: w.draft(_ticket(), tone).reply_body for tone in ("formal", "friendly", "urgent")}
    for tone, body in bases.items():
        assert "MED-777" in body, f"{tone} lost the ticket id"
        assert "Biomed" in body, f"{tone} lost the assigned team"


def test_urgent_and_formal_promise_the_same_window_when_routine():
    """A 'friendly' reply must not quietly promise a faster turnaround than 'formal'."""
    w = ReplyWriter()
    routine = TicketOut(
        ticket_id="MED-778", timestamp="2026-11-13T08:00:00+02:00", sender="Finance",
        category="Finance", priority="Medium", summary="Invoice query from MedSupply",
        assigned_to="Finance Desk",
    )
    windows = {}
    for tone in ("formal", "friendly"):
        body = w.draft(routine, tone).reply_body
        m = re.search(r"(one|two) working days?", body)
        windows[tone] = m.group(0) if m else None
    assert windows["formal"] == windows["friendly"] == "one working day"


def test_no_tone_argument_keeps_historical_behaviour():
    w = ReplyWriter()
    assert w.draft(_ticket()).tone == "concise-professional"


def test_unknown_tone_is_rejected():
    with pytest.raises(ValueError):
        ReplyWriter().draft(_ticket(), "sarcastic")


def test_api_accepts_tone_and_returns_it():
    c = TestClient(app)
    seen = set()
    for tone in ("formal", "friendly", "urgent"):
        r = c.post("/replies", json={"message": MSG, "tone": tone})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["reply"]["tone"]
        seen.add(body["reply"]["reply_body"])
    assert len(seen) == 3, "the API returned identical replies for different tones"


def test_api_rejects_an_invalid_tone():
    c = TestClient(app)
    r = c.post("/replies", json={"message": MSG, "tone": "shouty"})
    # The service has its own validation handler: a 400 naming the field beats a bare 422.
    assert r.status_code == 400
    body = r.json()
    assert body["fields"][0]["field"] == "tone"
    assert "formal" in body["fields"][0]["problem"]


def test_api_still_screens_the_reply_for_patient_data():
    """Tone must not create a path that skips the compliance screen."""
    c = TestClient(app)
    r = c.post("/replies", json={"message": MSG, "tone": "friendly"})
    assert r.status_code == 200
    assert "compliance" in r.json()
