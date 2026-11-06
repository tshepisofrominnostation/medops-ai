"""Weekly insight engine (Week 3): turn the analytics contract into findings.

Every finding is computed from numbers, carries the evidence it rests on, and says
when the data is too thin to support a claim. Nothing here calls an LLM; the LLM
layer (app/nlp/narrative.py) may only *reword* these findings, never invent new ones.
"""
from datetime import date, timedelta
from typing import Optional

from .analytics import CATEGORIES, PRIORITIES, _record_date, build_analytics
from .forecast import forecast_volume

MIN_TICKETS_FOR_TREND = 8      # below this, comparisons are noise
MIN_DAYS_FOR_TREND = 4
MIN_MEASURED_FOR_SLA = 5
SLA_GOOD = 0.90    # at or above: on target, say nothing
SLA_WATCH = 0.70   # between WATCH and GOOD: close; below WATCH: well below


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def _fmt_minutes(m: Optional[float]) -> str:
    from .nlp.narrative import fmt_minutes
    return fmt_minutes(m)


def week_window(records: list[dict], end: Optional[str] = None, days: int = 7) -> tuple[str, str]:
    """The 7-day window ending on `end` (default: the latest dated ticket, else today)."""
    if end is None:
        stamps = sorted(r["timestamp"][:10] for r in records
                        if isinstance(r.get("timestamp"), str) and len(r["timestamp"]) >= 10)
        end = stamps[-1] if stamps else date.today().isoformat()
    end_d = date.fromisoformat(end)
    return (end_d - timedelta(days=days - 1)).isoformat(), end_d.isoformat()


def build_insights(records: list[dict], department: Optional[str] = None,
                   end: Optional[str] = None) -> dict:
    """Findings for one week, optionally scoped to a department.

    Compares the window with the preceding window of equal length and refuses to
    state a trend when either side has too little data.
    """
    scoped = [r for r in records if department is None or r.get("assigned_to") == department]
    # Undated tickets cannot be placed in a week. Counting them only inside the
    # window (as build_analytics does) hides them entirely, which is exactly the
    # failure R2 in docs/RISK_REPORT.md describes. Count them at scope level and
    # say so out loud instead.
    undated_in_scope = sum(1 for r in scoped if _record_date(r) is None)
    start, stop = week_window(scoped, end)
    prev_end = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    prev_start = (date.fromisoformat(prev_end) - timedelta(days=6)).isoformat()

    cur = build_analytics(scoped, start=start, end=stop)
    prev = build_analytics(scoped, start=prev_start, end=prev_end)
    total, prev_total = cur["total_tickets"], prev["total_tickets"]

    findings: list[dict] = []

    def add(kind, headline, evidence, confidence="solid"):
        findings.append({"kind": kind, "headline": headline,
                         "evidence": evidence, "confidence": confidence})

    if total == 0:
        add("empty", "No tickets in this window.",
            {"window": [start, stop]}, "solid")
        return _wrap(cur, prev, findings, start, stop, prev_start, prev_end, department,
                     forecast=None, undated_in_scope=undated_in_scope)

    # -- volume trend vs the previous week (only if both weeks have enough data) ----
    enough = (total >= MIN_TICKETS_FOR_TREND and prev_total >= MIN_TICKETS_FOR_TREND
              and len(cur["by_day"]) >= MIN_DAYS_FOR_TREND)
    if enough:
        change = (total - prev_total) / prev_total
        direction = "up" if change > 0.05 else "down" if change < -0.05 else "flat"
        add("volume_trend",
            f"Ticket volume is {direction} {abs(change) * 100:.0f}% on last week "
            f"({prev_total} to {total}).",
            {"this_week": total, "last_week": prev_total, "change": round(change, 3)})
    else:
        add("volume_trend",
            f"{total} tickets this week; not enough history to call a trend "
            f"(needs {MIN_TICKETS_FOR_TREND}+ tickets in each of two weeks and "
            f"{MIN_DAYS_FOR_TREND}+ active days).",
            {"this_week": total, "last_week": prev_total, "days_active": len(cur["by_day"])},
            "insufficient-data")

    # -- dominant category -------------------------------------------------------------
    cats = cur["by_category"]
    top_cat = max(cats, key=cats.get)
    share = cats[top_cat] / total
    if cats[top_cat] > 0:
        add("top_category",
            f"{top_cat} is the largest category with {cats[top_cat]} of {total} tickets "
            f"({share * 100:.0f}%).",
            {"category": top_cat, "count": cats[top_cat], "share": round(share, 3)},
            "solid" if total >= 5 else "low-sample")

    # -- priority pressure -------------------------------------------------------------
    high = cur["by_priority"]["High"]
    hp = high / total
    if hp >= 0.4:
        add("priority_pressure",
            f"High-priority tickets make up {hp * 100:.0f}% of the week ({high} of {total}); "
            f"on-call capacity is under pressure.",
            {"high": high, "share": round(hp, 3)}, "solid" if total >= 5 else "low-sample")
    elif high:
        add("priority_pressure",
            f"{high} high-priority ticket{'s' if high != 1 else ''} this week "
            f"({hp * 100:.0f}%).", {"high": high, "share": round(hp, 3)})

    # -- response time & SLA -----------------------------------------------------------
    rt, sla = cur["response_time"], cur["sla"]
    if rt["measured_tickets"] == 0:
        add("response_time",
            "No response times are recorded yet, so SLA performance cannot be reported. "
            "Mark tickets In Progress or Resolved to start measuring.",
            {"unmeasured": rt["unmeasured_tickets"]}, "insufficient-data")
    else:
        conf = "solid" if rt["measured_tickets"] >= MIN_MEASURED_FOR_SLA else "low-sample"
        add("response_time",
            f"Median first response was {_fmt_minutes(rt['median_minutes'])} "
            f"(mean {_fmt_minutes(rt['mean_minutes'])}, worst {_fmt_minutes(rt['worst_minutes'])}) "
            f"across {rt['measured_tickets']} answered ticket"
            f"{'s' if rt['measured_tickets'] != 1 else ''}"
            + (f"; {rt['unmeasured_tickets']} still unanswered." if rt["unmeasured_tickets"] else "."),
            {"median": rt["median_minutes"], "mean": rt["mean_minutes"],
             "measured": rt["measured_tickets"]}, conf)
        if sla["attainment"] is not None:
            targets = sla["targets_minutes"]
            add("sla",
                f"{_pct(sla['attainment'])} of answered tickets met their proposed response target "
                f"(High {targets['High']} min, Medium {targets['Medium']} min, "
                f"Low {targets['Low']} min).",
                {"attainment": sla["attainment"], "by_priority": sla["by_priority"],
                 "measured": sla["measured_tickets"]},
                "solid" if sla["measured_tickets"] >= MIN_MEASURED_FOR_SLA else "low-sample")
            # Attainment bands, stated once. "Well below" is reserved for a real
            # shortfall; a priority a few points under the line is "close to".
            conf_sla = ("solid" if sla["measured_tickets"] >= MIN_MEASURED_FOR_SLA
                        else "low-sample")
            behind = [p for p in PRIORITIES if sla["by_priority"][p] is not None
                      and sla["by_priority"][p] < SLA_WATCH]
            watch = [p for p in PRIORITIES if sla["by_priority"][p] is not None
                     and SLA_WATCH <= sla["by_priority"][p] < SLA_GOOD]
            if behind or watch:
                add("sla_gap", "Response performance is behind the proposed targets.",
                    {"priorities": behind + watch, "behind": behind, "watch": watch,
                     "by_priority": sla["by_priority"]}, conf_sla)

    # -- backlog -----------------------------------------------------------------------
    st = cur["by_status"]
    open_n = st["Open"]
    if open_n:
        add("backlog", f"{open_n} ticket{'s are' if open_n != 1 else ' is'} still Open "
            f"(unanswered) out of {total}.", {"open": open_n, "total": total})

    # -- data quality: never hide a gap -----------------------------------------------
    if undated_in_scope:
        add("data_quality",
            f"{undated_in_scope} ticket{'s in this scope have' if undated_in_scope != 1 else ' in this scope has'} "
            "no date, so it cannot appear in this week or in the daily trend. "
            "Report it as a data-entry gap, not as zero activity.",
            {"undated": undated_in_scope, "scope": department or "all departments"},
            "solid")

    fc = forecast_volume(cur["by_day"], horizon=7) if cur["by_day"] else None
    return _wrap(cur, prev, findings, start, stop, prev_start, prev_end, department, fc,
                 undated_in_scope=undated_in_scope)


def _wrap(cur, prev, findings, start, stop, prev_start, prev_end, department, forecast,
          undated_in_scope=0):
    return {
        "scope": department or "All departments",
        "window": {"start": start, "end": stop},
        "previous_window": {"start": prev_start, "end": prev_end},
        "analytics": cur,
        "previous_analytics": prev,
        "undated_in_scope": undated_in_scope,
        "findings": findings,
        "forecast": forecast,
        "limits": ("Computed from persisted tickets only. Response times exist only for "
                   "tickets that staff moved out of Open. Targets are proposed, not policy. "
                   "Forecasts are a planning aid and carry their own backtest error."),
    }
