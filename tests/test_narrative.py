"""Week 4: the narrative layer may reword, never invent, never leak."""
from app.insights import build_insights
from app.nlp.narrative import (LLMNarrative, DeterministicNarrative, write_narrative,
                               ungrounded_numbers)
from tests.test_insights import week


def insights():
    return build_insights(week(12, "2026-11-06", spread=True) + week(8, "2026-10-30"),
                          end="2026-11-06")


class FakeLLM(LLMNarrative):
    """A stand-in model that returns exactly what the test tells it to."""
    model = "fake-model"

    def __init__(self, output, configured=True):
        self.output = output
        self.configured = configured

    def write(self, _ins):
        return self.output


def test_without_a_key_the_deterministic_engine_writes():
    out = write_narrative(insights(), FakeLLM(None, configured=False))
    assert out["engine"] == "deterministic"
    assert out["text"]


def test_a_grounded_rewrite_is_accepted():
    out = write_narrative(insights(), FakeLLM(
        "There were 12 tickets this week against 8 last week, and every response met its target."))
    assert out["engine"] == "llm"
    assert out["fallback_reason"] is None


def test_an_invented_figure_rejects_the_whole_output():
    out = write_narrative(insights(), FakeLLM("Volume rose 45% and 99 tickets were escalated."))
    assert out["engine"] == "deterministic"
    assert "unsupported figures" in out["fallback_reason"]


def test_patient_information_in_the_output_is_blocked():
    out = write_narrative(insights(), FakeLLM("Mr Dlamini in bed 12 waited a long time."))
    assert out["engine"] == "deterministic"
    assert "compliance" in out["fallback_reason"]


def test_failed_model_falls_back_without_raising():
    class Broken(LLMNarrative):
        configured = True

        def write(self, _ins):
            raise RuntimeError("provider exploded")

    out = write_narrative(insights(), Broken())
    assert out["engine"] == "deterministic"
    assert out["text"]


def test_every_result_carries_its_disclosure_and_verdict():
    out = write_narrative(insights(), FakeLLM(None, configured=False))
    assert "Review before circulating" in out["disclosure"]
    assert out["compliance"]["verdict"] in ("clean", "review", "blocked")
    assert out["grounded"] is True


def test_ungrounded_numbers_detects_a_stray_figure():
    ins = insights()
    assert ungrounded_numbers("There were 12 tickets.", ins) == []
    assert "777" in ungrounded_numbers("There were 777 tickets.", ins)


def test_deterministic_narrative_says_when_data_is_thin():
    ins = build_insights([{"ticket_id": "MED-1", "category": "HR", "priority": "Low",
                           "assigned_to": "T", "timestamp": "2026-11-06T09:00:00+02:00"}],
                         end="2026-11-06")
    text = DeterministicNarrative().write(ins)
    assert "not enough history" in text or "planning aid" in text
