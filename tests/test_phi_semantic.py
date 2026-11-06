"""R4 regression: the six adversarial PHI phrasings from docs/RISK_REPORT.md.

These were run inline during the Sprint 3 audit and never saved, so nothing stopped
the screen from regressing. They are permanent now. The floor is 6/6.
"""
import json
import os

import pytest

from app.compliance import screen
from app.nlp.phi import detect

MUST_FLAG = [
    "Mr Dlamini in bed 12 has been waiting since Monday",
    "The lady from the maternity ward whose husband called yesterday",
    "Her medical aid, the one ending 8834, will cover it",
    "He is on the ARV regimen we discussed",
    "The patient who attempted suicide last week",
]
CLEAN_CONTROL = "Your reference is MED-042"

# Phrasings that were NOT used while tuning the detector.
UNSEEN_MUST_FLAG = [
    "Mrs Naidoo from ward 4 is asking about her results",
    "She was diagnosed with TB last month",
    "Patient in bed 3 is HIV positive and refusing consent",
    "His medical aid number ends 5521",
    "Baby Mahlangu was admitted on Tuesday",
    "The woman who was assaulted is in room 9",
]

BENIGN = [
    "The biomedical team will inspect the monitor in Bay 3 today.",
    "Thank you for logging this. Finance has received MED-014 and will respond within two working days.",
    "Hello Team, the generator test is scheduled for Friday.",
    "The Duty Manager will confirm once the area is safe.",
    "The lift in Block C will be serviced on Monday morning.",
]


@pytest.mark.parametrize("text", MUST_FLAG)
def test_semantic_phi_is_flagged_by_the_screen(text):
    r = screen(text)
    assert r["verdict"] in ("blocked", "review"), f"screen called this clean: {text}"
    assert r["flags"], text


@pytest.mark.parametrize("text", UNSEEN_MUST_FLAG)
def test_unseen_phi_is_flagged(text):
    assert detect(text)["flags"], f"missed: {text}"


def test_clean_control_stays_clean():
    assert screen(CLEAN_CONTROL)["verdict"] == "clean"


@pytest.mark.parametrize("text", BENIGN)
def test_benign_operational_text_is_not_flagged(text):
    assert screen(text)["verdict"] == "clean", text


def test_staff_name_is_review_not_block():
    r = screen("Dr Naidoo has been notified.")
    assert r["verdict"] == "review" and r["passed"] is True


def test_patient_name_blocks():
    assert screen("Mr Dlamini is waiting")["passed"] is False


def test_every_reply_the_system_writes_passes(tmp_path):
    """The platform must not trip its own screen."""
    os.environ["MEDOPS_DB_PATH"] = str(tmp_path / "t.json")
    import importlib
    import app.persistence as persistence
    importlib.reload(persistence)
    from app.pipeline import process_ticket
    from app.reply_writer import ReplyWriter
    cases = json.load(open("tests/data/evaluation_set.json"))["cases"]
    w = ReplyWriter()
    bad = []
    for c in cases:
        reply = w.draft(process_ticket(c["message"]))
        res = screen(reply.reply_body)
        if res["verdict"] == "blocked":
            bad.append((c["id"], [f["rule"] for f in res["flags"]]))
    assert not bad, bad


def test_screen_result_states_its_limits():
    assert "Human review" in screen("hello")["disclaimer"]
