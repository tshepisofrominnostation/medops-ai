"""Week 6: a decision log is only worth having if it is private, append-only and robust."""
import json
from types import SimpleNamespace

from app.decision_log import (build_record, log_decision, read_log, signals_for,
                              language_hint, transparency_note)


def _ticket(priority="High", cat="IT"):
    return SimpleNamespace(ticket_id="MED-101", category=cat, priority=priority, assigned_to="Biomed")


def test_log_never_contains_the_message_text(tmp_path):
    secret = "Mr Dlamini ID 8001015800083 in bed 12 needs the ventilator urgent"
    p = tmp_path / "d.jsonl"
    log_decision(secret, _ticket(), p)
    raw = p.read_text()
    for leak in ("Dlamini", "8001015800083", "bed 12", "ventilator"):
        assert leak not in raw
    assert json.loads(raw)["message_length"] == len(secret)


def test_signals_record_groups_not_words():
    assert "clinical_equipment" in signals_for("the dialysis machine is down")
    assert "urgency_words" in signals_for("the dialysis machine is down")
    assert signals_for("hello") == []


def test_log_is_append_only_across_calls(tmp_path):
    p = tmp_path / "d.jsonl"
    log_decision("first message here", _ticket(), p)
    log_decision("second message here", _ticket("Low"), p)
    rows = read_log(p)
    assert [r["priority"] for r in rows] == ["High", "Low"]


def test_corrupt_line_does_not_hide_the_rest(tmp_path):
    p = tmp_path / "d.jsonl"
    log_decision("good one", _ticket(), p)
    with open(p, "a") as fh:
        fh.write('{"torn": \n')
    log_decision("good two", _ticket("Medium"), p)
    assert len(read_log(p)) == 2


def test_unwritable_path_returns_error_instead_of_raising(tmp_path):
    blocked = tmp_path / "afile"
    blocked.write_text("x")
    # a path UNDER a regular file cannot be created
    out = log_decision("msg", _ticket(), blocked / "sub" / "d.jsonl")
    assert out["ok"] is False
    assert "error" in out


def test_non_english_without_urgency_signal_is_flagged_for_review():
    rec = build_record("Umshini we-dialysis ya-4 awusebenzi, iziguli zilindile, siyadinga usizo ngokushesha",
                       _ticket("Medium"))
    assert rec["language_hint"] == "likely_isizulu"
    assert rec["needs_bias_review"] is True
    assert "person should confirm" in rec["note"]


def test_english_urgent_message_is_not_flagged():
    rec = build_record("Dialysis machine 4 is not working, urgent", _ticket("High"))
    assert rec["needs_bias_review"] is False


def test_afrikaans_hint():
    assert language_hint("Die lift is stukkend en dit is nie reg nie") == "likely_afrikaans"


def test_transparency_note_counts_and_states_limits(tmp_path):
    p = tmp_path / "d.jsonl"
    log_decision("Dialysis machine is not working", _ticket("High"), p)
    log_decision("Umshini awusebenzi iziguli zilindile ngokushesha", _ticket("Medium"), p)
    note = transparency_note(p)
    assert note["decisions"] == 2
    assert note["flagged_for_bias_review"] == 1
    assert note["by_priority"] == {"High": 1, "Medium": 1}
    assert "cheap hint" in note["limits"]
    assert "stores no message text" in note["note"]


def test_empty_log_says_so(tmp_path):
    assert transparency_note(tmp_path / "none.jsonl")["decisions"] == 0
