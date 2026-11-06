"""Week 3: the insight engine must state only what the data supports."""
from app.insights import build_insights, week_window
from app.nlp.narrative import DeterministicNarrative, write_narrative


def rec(tid, cat, pri, day, resp=None, resolved=None, dept="Team A"):
    r = {"ticket_id": tid, "category": cat, "priority": pri, "assigned_to": dept,
         "timestamp": f"{day}T09:00:00+02:00"}
    if resp is not None:
        r["first_response_at"] = f"{day}T09:{resp:02d}:00+02:00"
    if resolved is not None:
        r["resolved_at"] = f"{day}T10:{resolved:02d}:00+02:00"
    return r


DAYS = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]


def week(n, day, cat="HR", pri="Medium", resp=20, dept="Team A", spread=False):
    """n tickets. spread=True spreads them across that week's days, which the trend
    rule requires (a single busy day is not a trend, it is one busy day)."""
    out = []
    for i in range(n):
        d = DAYS[i % len(DAYS)] if spread else day
        out.append(rec(f"MED-{day}-{i}", cat, pri, d, resp, dept=dept))
    return out


def kinds(ins):
    return {f["kind"] for f in ins["findings"]}


def test_window_is_seven_days_ending_on_the_given_date():
    rows = [rec("MED-001", "HR", "Low", "2026-11-06")]
    ins = build_insights(rows, end="2026-11-06")
    assert ins["window"] == {"start": "2026-10-31", "end": "2026-11-06"}
    assert ins["previous_window"] == {"start": "2026-10-24", "end": "2026-10-30"}


def test_default_window_ends_on_the_latest_ticket():
    rows = [rec("MED-001", "HR", "Low", "2026-10-02"), rec("MED-002", "HR", "Low", "2026-10-09")]
    assert week_window(rows)[1] == "2026-10-09"


def test_no_trend_claim_from_thin_data():
    """Two weeks with 3 tickets each is not evidence of a trend."""
    rows = week(3, "2026-11-06") + week(3, "2026-10-30")
    ins = build_insights(rows, end="2026-11-06")
    trend = next(f for f in ins["findings"] if f["kind"] == "volume_trend")
    assert trend["confidence"] == "insufficient-data"
    assert "not enough history" in trend["headline"]


def test_trend_is_claimed_when_both_weeks_are_substantial():
    """Both weeks need MIN_TICKETS_FOR_TREND; 9 vs 4 is correctly refused below."""
    rows = week(12, "2026-11-06", spread=True) + week(8, "2026-10-30")
    ins = build_insights(rows, end="2026-11-06")
    trend = next(f for f in ins["findings"] if f["kind"] == "volume_trend")
    assert trend["confidence"] == "solid"
    assert trend["evidence"]["this_week"] == 12 and trend["evidence"]["last_week"] == 8


def test_one_thin_week_is_enough_to_refuse_the_trend():
    rows = week(12, "2026-11-06", spread=True) + week(4, "2026-10-30")
    ins = build_insights(rows, end="2026-11-06")
    trend = next(f for f in ins["findings"] if f["kind"] == "volume_trend")
    assert trend["confidence"] == "insufficient-data"


def test_response_time_finding_carries_its_numbers():
    ins = build_insights(week(10, "2026-11-06", resp=20), end="2026-11-06")
    rt = next(f for f in ins["findings"] if f["kind"] == "response_time")
    assert rt["evidence"]["median"] == 20.0
    assert "20 min" in rt["headline"]


def test_unanswered_tickets_are_reported_not_hidden():
    rows = week(4, "2026-11-06") + [rec(f"MED-X{i}", "HR", "Medium", "2026-11-06") for i in range(3)]
    ins = build_insights(rows, end="2026-11-06")
    backlog = next(f for f in ins["findings"] if f["kind"] == "backlog")
    assert backlog["evidence"]["open"] == 3


def test_no_response_data_is_stated_plainly():
    rows = [rec(f"MED-{i}", "HR", "Low", "2026-11-06") for i in range(6)]
    ins = build_insights(rows, end="2026-11-06")
    rt = next(f for f in ins["findings"] if f["kind"] == "response_time")
    assert rt["confidence"] == "insufficient-data"
    assert "cannot be reported" in rt["headline"]


def test_department_scope_narrows_everything():
    rows = week(4, "2026-11-06", dept="HR Admin Team") + week(5, "2026-11-06", dept="Finance")
    ins = build_insights(rows, department="HR Admin Team", end="2026-11-06")
    assert ins["analytics"]["total_tickets"] == 4
    assert ins["scope"] == "HR Admin Team"


def test_undated_tickets_are_disclosed():
    rows = week(3, "2026-11-06") + [{"ticket_id": "MED-U", "category": "HR",
                                    "priority": "Low", "assigned_to": "Team A"}]
    ins = build_insights(rows, end="2026-11-06")
    quality = next(f for f in ins["findings"] if f["kind"] == "data_quality")
    assert quality["evidence"]["undated"] == 1


def test_sla_language_distinguishes_close_from_well_below():
    """79% of target is 'close', not 'missed'. The distinction must survive."""
    rows = ([rec(f"MED-A{i}", "HR", "Low", "2026-11-06", resp=30) for i in range(8)]
            + [rec(f"MED-B{i}", "HR", "Low", "2026-11-06", resp=5) for i in range(2)])
    ins = build_insights(rows, end="2026-11-06")
    gap = [f for f in ins["findings"] if f["kind"] == "sla_gap"]
    if gap:
        ev = gap[0]["evidence"]
        assert "Low" in ev["watch"] and "Low" not in ev["behind"]


def test_empty_week_is_handled_without_crashing():
    ins = build_insights([], end="2026-11-06")
    assert ins["analytics"]["total_tickets"] == 0
    assert ins["findings"][0]["kind"] == "empty"
    assert write_narrative(ins)["text"].startswith("No tickets were logged")


def test_deterministic_narrative_invents_no_numbers():
    rows = week(12, "2026-11-06", spread=True) + week(8, "2026-10-30")
    ins = build_insights(rows, end="2026-11-06")
    text = DeterministicNarrative().write(ins)
    assert "12" in text and "8" in text
    assert "not enough history" not in text
    # every number quoted must exist in the findings
    from app.nlp.narrative import ungrounded_numbers
    assert ungrounded_numbers(text, ins) == []


def test_forecast_is_labelled_a_planning_aid():
    ins = build_insights(week(10, "2026-11-06", spread=True), end="2026-11-06")
    text = DeterministicNarrative().write(ins)
    assert "planning aid, not a prediction" in text
