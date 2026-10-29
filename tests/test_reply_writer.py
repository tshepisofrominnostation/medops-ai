"""Reply Writer tests: tone control, safety guardrails, structured output, fallback."""
import os

os.environ.setdefault("MEDOPS_DB_PATH", "/tmp/test-rw-db.json")
if os.path.exists("/tmp/test-rw-db.json"):
    os.remove("/tmp/test-rw-db.json")

from app.pipeline import process_ticket
from app.reply_writer import (DraftedReply, ReplyWriter, TemplateReplyEngine,
                               contains_medical_advice)


def _ticket(msg):
    return process_ticket(msg)


def test_high_priority_tone_is_concise_and_instructional():
    t = _ticket('"The patient monitoring terminal in Bay 3 keeps disconnecting." - Dr. S. Khumalo (Emergency Ward)')
    r = ReplyWriter().draft(t)
    assert r.tone == "concise-professional"
    assert len(r.reply_body.split()) <= 65          # concise
    assert "do not" in r.reply_body.lower()          # instruction-focused
    assert "escalate" in r.reply_body.lower()        # escalation path
    assert r.safety_flags == ["escalated-on-call", "clinical-equipment-escalation"]


def test_routine_tone_is_warm_and_informative():
    t = _ticket('"I need to apply for annual leave from 3 to 7 Dec." - Nurse T. Mokoena (Ward 5)')
    r = ReplyWriter().draft(t)
    assert r.tone == "warm-administrative"
    body = r.reply_body.lower()
    assert "thank you" in body                       # welcoming
    assert "working day" in body                     # informative timeframe
    assert "confirmation" in body                    # reassuring


def test_medical_advice_guardrail():
    assert contains_medical_advice("We recommend a dosage of 500 mg") is not None
    assert contains_medical_advice("The diagnosis is bronchitis") is not None
    assert contains_medical_advice("Do not use the affected equipment") is None


def test_all_categories_have_urgent_and_warm_templates():
    writer = ReplyWriter()
    msgs = {
        "IT & Medical Tech": '"The ICU bedside monitor is alarming." - Sr. L. Mabuza (ICU)',
        "HR": '"We are short two nurses tonight in the Emergency Ward." - Sr. N. Mabaso (Emergency Ward)',
        "Finance": '"Pay the oxygen supplier urgently, supply stops this week." - Mr K. Naidoo (Procurement)',
        "Operations": '"The generator failed and theatre is on backup power." - Sr. M. Peters (Theatre)',
    }
    for cat, m in msgs.items():
        t = _ticket(m)
        assert t.category == cat
        r = writer.draft(t)
        assert r.tone == "concise-professional"
        assert contains_medical_advice(r.reply_body) is None
        assert len(r.reply_body) > 60


def test_structured_output_contract():
    t = _ticket('"All the light bulbs in Reception need replacing." - Ms B. Sithole (Reception)')
    r = TemplateReplyEngine().draft(t)
    d = DraftedReply(**r.model_dump())               # validates the Pydantic contract
    assert d.ticket_id == t.ticket_id
    assert d.generated_by == "template"
    assert d.safety_flags == ["standard-queue"]


def test_llm_fallback_on_failure():
    """A configured-but-unreachable LLM must fall back to the template engine."""
    os.environ["MEDOPS_LLM_BASE_URL"] = "http://127.0.0.1:9/v1"   # unroutable port
    os.environ["MEDOPS_LLM_API_KEY"] = "test-key"
    os.environ["MEDOPS_LLM_TIMEOUT"] = "1"
    import importlib
    import app.reply_writer as rw
    importlib.reload(rw)                              # rebind env at init
    t = process_ticket('"The air conditioner in Ward 5 has stopped cooling." - Nurse T. Mokoena (Ward 5)')
    r = rw.ReplyWriter().draft(t)
    assert r.generated_by == "template (llm-fallback)"
    assert r.tone == "warm-administrative"
    for k in ("MEDOPS_LLM_BASE_URL", "MEDOPS_LLM_API_KEY"):
        os.environ.pop(k, None)
    importlib.reload(rw)                              # restore unconfigured state
