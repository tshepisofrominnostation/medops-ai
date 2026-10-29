"""Tests for the team integration: Xoli's From: parsing and tone detection."""
from app.parser import parse_sender
from app.pipeline import process_ticket
from app.reply_writer import ReplyWriter
from app.tone_detector import detect_tone
import os
os.environ.setdefault("MEDOPS_DB_PATH", "/tmp/test-team-int.json")


def test_from_header_sender_is_extracted():
    """Xoli's case: an email-style From: header."""
    raw = "From: staff@hospital.org\nSubject: HR request\n\nI need assistance updating my employee details."
    body, sender = parse_sender(raw)
    assert sender == "staff@hospital.org"
    assert "From:" not in body
    assert "I need assistance updating my employee details." in body


def test_override_beats_from_header():
    body, sender = parse_sender("From: staff@hospital.org\nI need help.", override="Jane Smith")
    assert sender == "Jane Smith"


def test_tone_urgent_takes_precedence():
    assert detect_tone("Hi, the ventilator will not start, urgent help needed") == "urgent"


def test_tone_word_boundaries_no_false_positives():
    # 'hi' must not match inside 'this'; 'down' must not match inside 'download'
    assert detect_tone("It says my password expired this morning") == "formal"
    assert detect_tone("Please download the monthly report") == "formal"


def test_tone_is_recorded_on_every_draft():
    t = process_ticket('"Hi, could you please reset my EMR login." - Sr. A. Botha (Ward 2)')
    d = ReplyWriter().draft(t)
    assert d.sender_tone in ("formal", "friendly", "urgent")
    assert d.generated_by.startswith("template")


def test_friendly_sender_gets_warm_opener():
    t = process_ticket('"Hi, could you please reset my EMR login." - Sr. A. Botha (Ward 2)')
    d = ReplyWriter().draft(t)
    assert d.sender_tone == "friendly"
    assert "Thank you for reaching out" in d.reply_body
