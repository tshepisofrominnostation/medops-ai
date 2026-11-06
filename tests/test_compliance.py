"""S3-2: the screen must block identifiers and clinical advice, and pass clean text."""
from app.compliance import screen, screen_or_raise
import pytest


def test_clean_reply_passes():
    r = screen("Thank you for reporting this. The facilities team has been notified "
               "and will check the ward today. Your ticket reference is MED-042.")
    assert r["passed"] is True and r["verdict"] == "clean"


def test_sa_id_number_blocks():
    r = screen("I have noted your ID 9001015800087 for the record.")
    assert r["passed"] is False
    assert any(f["rule"] == "sa_id_number" for f in r["flags"])


def test_phone_number_blocks():
    r = screen("We will call you on 0821234567 shortly.")
    assert r["passed"] is False and any(f["rule"] == "phone_number" for f in r["flags"])


def test_dosage_instruction_blocks():
    r = screen("You should take 500 mg of paracetamol twice a day.")
    assert r["passed"] is False
    assert any(f["rule"] in ("dosage", "prescription", "medication_advice") for f in r["flags"])


def test_diagnosis_language_blocks():
    r = screen("You have a chest infection, this is not urgent.")
    assert r["passed"] is False and any(f["rule"] == "diagnosis" for f in r["flags"])


def test_review_severity_alone_does_not_block():
    r = screen("There is nothing to worry about, the technician will come.")
    assert r["verdict"] == "review"
    assert r["passed"] is True


def test_screen_or_raise_lists_rules():
    with pytest.raises(ValueError) as e:
        screen_or_raise("Send your details to sister@hospital.co.za")
    assert "email" in str(e.value)
