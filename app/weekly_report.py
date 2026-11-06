"""Weekly operations report: the one-page PDF a ward manager reads on a Monday.

Week 3 asks for a weekly summary; Week 4 asks for a report. Both are the same
question at different zoom, so this module sits on the analytics contract rather
than recomputing anything: `build_analytics` supplies the counts, `lifecycle`
supplies the targets, and this module adds what a weekly PDF needs and a
dashboard does not — SLA compliance per priority (response *and* resolution) and
a per-department breakdown with its priority mix.

Targets live in `app/lifecycle.py` only. An earlier draft of this feature carried
its own copy of the targets (Medium 60 minutes where the product has always shown
120), which would have let the dashboard and the PDF disagree about the same
ticket. One definition, imported.

Rendering reuses the stack the executive report already uses (HTML → PDF via
weasyprint), so the project ships one PDF engine rather than two.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Optional

from . import lifecycle
from .analytics import PRIORITIES, build_analytics

# Kept as a module-level name because tests and other callers import it, but it is
# derived from lifecycle so there is exactly one place to change a target.
SLA_TARGETS = {
    priority: {
        "response_minutes": lifecycle.SLA_TARGET_MINUTES[priority],
        "resolution_minutes": lifecycle.RESOLUTION_TARGET_MINUTES[priority],
    }
    for priority in PRIORITIES
}


def _parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _first_response_field(record: dict) -> Optional[str]:
    """`first_response_at` is the field Week 3 introduced.

    Data exported before the lifecycle module existed carries `responded_at`
    instead. Reading both keeps that history measurable rather than silently
    reporting it as "not tracked", and never invents a timestamp for a ticket
    that has none.
    """
    return record.get("first_response_at") or record.get("responded_at")


def _minutes_between(start: Optional[str], end: Optional[str]) -> Optional[float]:
    a, b = _parse_timestamp(start), _parse_timestamp(end)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 60, 2)


def build_sla_summary(records: list[dict]) -> dict:
    """Response and resolution compliance per priority, measured or None.

    A ticket with no response timestamp is counted as *untracked*, never as a
    zero-minute response: an unanswered ticket is not a fast one.
    """
    summary: dict[str, dict] = {}
    for priority, targets in SLA_TARGETS.items():
        rows = [r for r in records if r.get("priority") == priority]
        response_tracked = response_met = 0
        resolution_tracked = resolution_met = 0

        for record in rows:
            response = _minutes_between(record.get("timestamp"), _first_response_field(record))
            if response is not None:
                response_tracked += 1
                if response <= targets["response_minutes"]:
                    response_met += 1

            resolution = _minutes_between(record.get("timestamp"), record.get("resolved_at"))
            if resolution is not None:
                resolution_tracked += 1
                if resolution <= targets["resolution_minutes"]:
                    resolution_met += 1

        summary[priority] = {
            "total_tickets": len(rows),
            "response_target_minutes": targets["response_minutes"],
            "resolution_target_minutes": targets["resolution_minutes"],
            "response_tracked": response_tracked,
            "response_met": response_met,
            "response_compliance": round(response_met / response_tracked * 100, 1)
            if response_tracked else None,
            "resolution_tracked": resolution_tracked,
            "resolution_met": resolution_met,
            "resolution_compliance": round(resolution_met / resolution_tracked * 100, 1)
            if resolution_tracked else None,
        }
    return summary


def build_department_summary(records: list[dict]) -> dict:
    """Tickets, priority mix and status mix per receiving queue.

    Grouped on `assigned_to` (the queue that owns the work, and therefore has
    capacity) rather than on the ward that asked. Tickets that were never routed
    land under "Unassigned" so the total still reconciles.
    """
    groups: dict[str, list[dict]] = {}
    for record in records:
        queue = (record.get("assigned_to") or "").strip() or "Unassigned"
        groups.setdefault(queue, []).append(record)

    out: dict[str, dict] = {}
    for queue, rows in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        priorities = Counter(r.get("priority") or "Unknown" for r in rows)
        statuses = Counter(lifecycle.status_of(r) for r in rows)
        out[queue] = {
            "total_tickets": len(rows),
            "by_priority": dict(priorities),
            "by_status": dict(statuses),
            "categories": dict(Counter(r.get("category") or "Unknown" for r in rows)),
        }
    return out


def _period(records: list[dict], start: Optional[str], end: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """The window the report covers: as asked, or the week ending at the latest ticket."""
    if start or end:
        return start, end
    from .insights import week_window

    return week_window(records)


def build_weekly_summary(records: list[dict], start: Optional[str] = None,
                         end: Optional[str] = None) -> dict:
    """Everything the weekly PDF renders, computed from the analytics contract."""
    window_start, window_end = _period(records, start, end)
    analytics = build_analytics(records, start=window_start, end=window_end)
    in_window = [
        r for r in records
        if analytics["window"]["start"] is None
        or (analytics["window"]["start"] <= (r.get("timestamp") or "")[:10] <= (analytics["window"]["end"] or "9999-12-31"))
    ]
    return {
        "period": {"start": analytics["window"]["start"], "end": analytics["window"]["end"]},
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "analytics": analytics,
        "departments": build_department_summary(in_window),
        "sla": build_sla_summary(in_window),
        "tickets": in_window,
    }


def _fmt(value, suffix="") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        value = round(value, 1)
    return f"{value}{suffix}"


def _minutes(value) -> str:
    if value is None:
        return "—"
    if value < 60:
        return f"{round(value)} min"
    hours, mins = divmod(round(value), 60)
    return f"{hours} h" + (f" {mins} min" if mins else "")


def render_weekly_html(summary: dict) -> str:
    """The PDF's page, in the product's own visual language."""
    period = summary["period"]
    a = summary["analytics"]
    rows = []
    for priority in PRIORITIES:
        s = summary["sla"][priority]
        rows.append(
            "<tr>"
            f"<td>{priority}</td>"
            f"<td>{s['total_tickets']}</td>"
            f"<td>{_fmt(s['response_compliance'], '%')}"
            f" <span class='muted'>({s['response_met']}/{s['response_tracked']} tracked, "
            f"target {_minutes(s['response_target_minutes'])})</span></td>"
            f"<td>{_fmt(s['resolution_compliance'], '%')}"
            f" <span class='muted'>({s['resolution_met']}/{s['resolution_tracked']} tracked, "
            f"target {_minutes(s['resolution_target_minutes'])})</span></td>"
            "</tr>"
        )

    dept_rows = []
    for queue, info in summary["departments"].items():
        mix = ", ".join(f"{p} {n}" for p, n in sorted(info["by_priority"].items()))
        dept_rows.append(
            f"<tr><td>{queue}</td><td>{info['total_tickets']}</td><td class='muted'>{mix or '—'}</td></tr>"
        )

    cat_rows = []
    for category, n in sorted(a["by_category"].items(), key=lambda kv: -kv[1]):
        share = (n / a["total_tickets"] * 100) if a["total_tickets"] else 0
        cat_rows.append(f"<tr><td>{category}</td><td>{n}</td><td class='muted'>{share:.0f}%</td></tr>")

    open_now = a["by_status"].get("Open", 0) + a["by_status"].get("In Progress", 0)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 18mm 16mm; }}
      body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; color: #0f172a; font-size: 10.5pt; }}
      h1 {{ font-size: 19pt; margin: 0 0 2mm; }}
      h2 {{ font-size: 11.5pt; margin: 7mm 0 2mm; color: #0e7490; text-transform: uppercase; letter-spacing: .06em; }}
      .sub {{ color: #475569; margin: 0 0 5mm; }}
      .kpis {{ display: flex; gap: 3mm; margin: 4mm 0 2mm; }}
      .kpi {{ flex: 1; border: 1px solid #e2e8f0; border-radius: 3mm; padding: 3mm; }}
      .kpi .n {{ font-size: 17pt; font-weight: 700; }}
      .kpi .l {{ font-size: 8pt; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 2mm; }}
      th, td {{ text-align: left; padding: 1.6mm 2mm; border-bottom: 1px solid #e2e8f0; font-size: 9.5pt; }}
      th {{ color: #64748b; font-weight: 600; text-transform: uppercase; font-size: 8pt; letter-spacing: .05em; }}
      .muted {{ color: #64748b; }}
      .note {{ margin-top: 6mm; font-size: 8.5pt; color: #475569; border-top: 1px solid #e2e8f0; padding-top: 2mm; }}
    </style></head><body>
      <h1>Weekly operations report</h1>
      <p class="sub">{period['start']} to {period['end']} &middot; generated {summary['generated_at'][:16].replace('T', ' ')}
        &middot; MedOps AI</p>

      <div class="kpis">
        <div class="kpi"><div class="l">Tickets</div><div class="n">{a['total_tickets']}</div></div>
        <div class="kpi"><div class="l">Median first response</div><div class="n">{_minutes(a['response_time']['median_minutes'])}</div></div>
        <div class="kpi"><div class="l">Open now</div><div class="n">{open_now}</div></div>
        <div class="kpi"><div class="l">On target</div><div class="n">{_fmt((a['sla']['attainment'] or 0) * 100 if a['sla']['attainment'] is not None else None, '%')}</div></div>
      </div>

      <h2>Service level compliance</h2>
      <table><tr><th>Priority</th><th>Tickets</th><th>First response in target</th><th>Resolved in target</th></tr>
      {''.join(rows)}</table>

      <h2>Volume by receiving queue</h2>
      <table><tr><th>Queue</th><th>Tickets</th><th>Priority mix</th></tr>{''.join(dept_rows)}</table>

      <h2>What the requests were about</h2>
      <table><tr><th>Category</th><th>Tickets</th><th>Share</th></tr>{''.join(cat_rows)}</table>

      <p class="note">Every figure is computed from stored tickets, including their first-response and
      resolution timestamps. Tickets without a timestamp are reported as untracked, not as fast.
      Targets are proposed internal targets (response: High {_minutes(SLA_TARGETS['High']['response_minutes'])},
      Medium {_minutes(SLA_TARGETS['Medium']['response_minutes'])}, Low {_minutes(SLA_TARGETS['Low']['response_minutes'])};
      resolution: High {_minutes(SLA_TARGETS['High']['resolution_minutes'])},
      Medium {_minutes(SLA_TARGETS['Medium']['resolution_minutes'])},
      Low {_minutes(SLA_TARGETS['Low']['resolution_minutes'])}), not hospital policy.</p>
    </body></html>"""


def generate_weekly_pdf(records: list[dict], start: Optional[str] = None,
                        end: Optional[str] = None) -> bytes:
    """The report as PDF bytes. Raises RuntimeError if the PDF engine is unavailable."""
    html = render_weekly_html(build_weekly_summary(records, start=start, end=end))
    try:
        from weasyprint import HTML
    except Exception as exc:                       # pragma: no cover - environment dependent
        raise RuntimeError(f"PDF engine unavailable: {exc}") from exc
    return HTML(string=html).write_pdf()


def write_weekly_pdf(records: list[dict], out_path: str, start: Optional[str] = None,
                     end: Optional[str] = None) -> dict:
    """Write the weekly PDF and return a small receipt describing it."""
    payload = generate_weekly_pdf(records, start=start, end=end)
    with open(out_path, "wb") as handle:
        handle.write(payload)
    summary = build_weekly_summary(records, start=start, end=end)
    return {
        "path": str(out_path),
        "bytes": len(payload),
        "period": summary["period"],
        "tickets": summary["analytics"]["total_tickets"],
    }
