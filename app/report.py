"""One-click weekly summary report, one PDF per department (S2-3).

Renders an HTML summary from the analytics contract and converts it to PDF with
WeasyPrint. If WeasyPrint is unavailable the HTML is still written, so the
deliverable degrades rather than fails.
"""
from datetime import date
from pathlib import Path
from typing import Optional

import csv
import html as _html
import io
import json

from .analytics import build_analytics, CATEGORIES


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "0.0%"


def build_report_data(records: list[dict], department: Optional[str] = None) -> dict:
    """Everything the report needs, computed from the same analytics contract."""
    scoped = [r for r in records
              if department is None or r.get("assigned_to") == department]
    a = build_analytics(scoped)
    a["department_filter"] = department
    a["generated_on"] = date.today().isoformat()
    return a


def build_full_report(records: list[dict], department: Optional[str] = None,
                      end: Optional[str] = None, use_llm: bool = True) -> dict:
    """Week 4: analytics + findings + executive narrative, scoped to a department.

    The narrative engine is the LLM only when MEDOPS_LLM_* is configured and its output
    passes the grounding and compliance checks; otherwise the deterministic engine writes it.
    """
    from .insights import build_insights
    from .nlp.narrative import write_narrative, LLMNarrative

    ins = build_insights(records, department=department, end=end)
    narrative = write_narrative(ins) if use_llm else write_narrative(ins, _NoLLM())
    base = build_report_data(records, department)
    return {
        "report": "MedOps AI weekly business report",
        "generated_on": base["generated_on"],
        "scope": ins["scope"],
        "window": ins["window"],
        "analytics": ins["analytics"],
        "previous_analytics": ins["previous_analytics"],
        "findings": ins["findings"],
        "forecast": ins["forecast"],
        "narrative": narrative,
        "limits": ins["limits"],
    }


class _NoLLM:
    """Stand-in that forces the deterministic engine (used by tests and offline runs)."""
    configured = False
    model = None


def report_to_csv(full: dict) -> str:
    """Flat, spreadsheet-friendly export of the report's numbers."""
    a = full["analytics"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "metric", "value"])
    w.writerow(["meta", "scope", full["scope"]])
    w.writerow(["meta", "window_start", full["window"]["start"]])
    w.writerow(["meta", "window_end", full["window"]["end"]])
    w.writerow(["totals", "tickets", a["total_tickets"]])
    w.writerow(["totals", "undated_tickets", a["undated_tickets"]])
    for k, v in a["by_category"].items():
        w.writerow(["category", k, v])
    for k, v in a["by_priority"].items():
        w.writerow(["priority", k, v])
    for k, v in a["by_status"].items():
        w.writerow(["status", k, v])
    for k, v in a["by_department"].items():
        w.writerow(["department", k, v])
    rt = a["response_time"]
    for k in ("measured_tickets", "unmeasured_tickets", "mean_minutes", "median_minutes", "worst_minutes"):
        w.writerow(["response_time", k, "" if rt[k] is None else rt[k]])
    w.writerow(["sla", "attainment", "" if a["sla"]["attainment"] is None else a["sla"]["attainment"]])
    for d in a["by_day"]:
        w.writerow(["daily_volume", d["date"], d["count"]])
    return buf.getvalue()


def render_executive_html(full: dict) -> str:
    """The Week 4 executive PDF source: narrative first, evidence after, ethics last."""
    a = full["analytics"]
    total = a["total_tickets"]
    esc = _html.escape
    n = full["narrative"]
    rt, sla = a["response_time"], a["sla"]

    def tbl(rows, head):
        body = "".join(f"<tr>{''.join(f'<td>{esc(str(c))}</td>' for c in r)}</tr>" for r in rows)
        th = "".join(f"<th>{esc(h)}</th>" for h in head)
        return f"<table><tr>{th}</tr>{body}</table>"

    from .nlp.narrative import fmt_minutes as mins

    LABEL = {"volume_trend": "Volume trend", "top_category": "Largest category",
             "priority_pressure": "High-priority load", "response_time": "First response",
             "sla": "Response targets", "sla_gap": "Target gaps", "backlog": "Unanswered",
             "data_quality": "Data quality", "empty": "Activity"}

    def evidence(f):
        e = f.get("evidence") or {}
        k = f["kind"]
        if k == "volume_trend" and "change" in e:
            return f"{e['last_week']} to {e['this_week']} tickets ({e['change'] * 100:+.0f}%)"
        if k == "volume_trend":
            return f"{e.get('this_week', 0)} this week, {e.get('last_week', 0)} last week"
        if k == "top_category":
            return f"{e['count']} tickets, {e['share'] * 100:.0f}% share"
        if k == "priority_pressure":
            return f"{e['high']} High, {e['share'] * 100:.0f}% of week"
        if k == "response_time":
            return (f"median {mins(e['median'])}, mean {mins(e['mean'])}, n={e['measured']}"
                    if "median" in e else f"{e.get('unmeasured', 0)} unanswered")
        if k == "sla":
            return f"{e['attainment'] * 100:.0f}% met, n={e['measured']}"
        if k == "sla_gap":
            return "; ".join(x for x in (
                ("well below: " + ", ".join(e["behind"])) if e["behind"] else "",
                ("close to: " + ", ".join(e["watch"])) if e["watch"] else "") if x)
        if k == "backlog":
            return f"{e['open']} of {e['total']} Open"
        if k == "data_quality":
            return f"{e['undated']} undated"
        return ""

    findings = tbl([(LABEL.get(f["kind"], f["kind"]), evidence(f), f["confidence"])
                    for f in full["findings"]], ["Finding", "Evidence", "Confidence"])
    narrative_html = "".join(f"<p>{esc(line)}</p>" for line in n["text"].split("\n") if line.strip())
    fc = full.get("forecast")
    fc_rows = [[f["date"], f["predicted"]] for f in fc["forecast"]] if fc and fc.get("forecast") else []

    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
 @page {{ size: A4; margin: 16mm 15mm 18mm;
   @bottom-center {{ content: "MedOps AI  |  page " counter(page) " of " counter(pages); font-size: 8pt; color: #6b7c93; }} }}
 body {{ font-family: Arial, Helvetica, sans-serif; color: #14233a; font-size: 10pt; line-height: 1.45; }}
 .band {{ background: #0e2a4a; color: #fff; padding: 7mm 8mm; border-radius: 2.5mm; }}
 .band h1 {{ margin: 0; font-size: 19pt; }} .band .sub {{ color: #a9c4e4; font-size: 9pt; margin-top: 1.5mm; }}
 h2 {{ font-size: 10.5pt; text-transform: uppercase; letter-spacing: .08em; color: #1f6fb2;
       border-bottom: .3mm solid #cfdcec; padding-bottom: 1mm; margin: 6.5mm 0 2.5mm; }}
 .kpis {{ display: flex; gap: 4mm; margin: 5mm 0 0; }}
 .kpi {{ flex: 1; border: .3mm solid #cfdcec; border-radius: 2mm; padding: 3mm 4mm; }}
 .kpi b {{ display: block; font-size: 15pt; color: #0e2a4a; }}
 .kpi span {{ font-size: 7.5pt; color: #5b6e86; text-transform: uppercase; letter-spacing: .06em; }}
 table {{ width: 100%; border-collapse: collapse; margin-top: 1.5mm; page-break-inside: avoid; }}
 tr {{ page-break-inside: avoid; }} h2 {{ page-break-after: avoid; }} .ethics {{ page-break-inside: avoid; }}
 th, td {{ text-align: left; padding: 1.6mm 2mm; border-bottom: .25mm solid #e1eaf4; font-size: 9pt; }}
 th {{ color: #5b6e86; font-size: 7.5pt; text-transform: uppercase; letter-spacing: .06em; }}
 .tag {{ font-size: 7pt; background: #fff3d6; color: #7a5200; padding: .4mm 1.6mm; border-radius: 1mm; }}
 .ethics {{ background: #f1f6fc; border-left: 1.2mm solid #1f6fb2; padding: 3mm 4mm; font-size: 8.5pt; margin-top: 6mm; }}
 ul {{ margin: 1mm 0 0 4mm; padding: 0; }} li {{ margin-bottom: 1.2mm; }}
 p {{ margin: 0 0 2mm; }}
</style></head><body>
 <div class="band"><h1>Weekly business report</h1>
  <div class="sub">{esc(full['scope'])} &middot; {esc(full['window']['start'])} to {esc(full['window']['end'])}
   &middot; generated {esc(full['generated_on'])}</div></div>

 <div class="kpis">
  <div class="kpi"><b>{total}</b><span>tickets</span></div>
  <div class="kpi"><b>{a['by_priority']['High']}</b><span>high priority</span></div>
  <div class="kpi"><b>{mins(rt['median_minutes'])}</b><span>median response</span></div>
  <div class="kpi"><b>{'n/a' if sla['attainment'] is None else f"{sla['attainment'] * 100:.0f}%"}</b><span>met response target</span></div>
 </div>

 <h2>Executive summary</h2>{narrative_html}
 <h2>Key findings</h2>{findings}

 <h2>Volume by category</h2>
 {tbl([(c, v, f"{100 * v / total:.0f}%" if total else "0%") for c, v in a['by_category'].items()], ["Category", "Tickets", "Share"])}
 <h2>Priority and status</h2>
 {tbl([(p, v) for p, v in a['by_priority'].items()] + [("Status: " + k, v) for k, v in a['by_status'].items()], ["Item", "Tickets"])}
 <h2>Response time</h2>
 {tbl([(p, mins(a['response_time']['by_priority'][p]), f"{sla['targets_minutes'][p]} min", "n/a" if sla['by_priority'][p] is None else f"{sla['by_priority'][p] * 100:.0f}%") for p in ('High', 'Medium', 'Low')], ["Priority", "Mean first response", "Proposed target", "Met target"])}
 <h2>Teams</h2>
 {tbl(list(a['by_department'].items()), ["Team", "Tickets"]) if a['by_department'] else '<p>No assigned tickets.</p>'}
 {('<h2>Next 7 days (planning aid)</h2>' + tbl(fc_rows, ['Date', 'Expected tickets'])) if fc_rows else ''}

 <div class="ethics"><b>Responsible AI notice.</b> {esc(n['disclosure'])}
  Narrative engine: <b>{esc(n['engine'])}</b>{(' (' + esc(n['model']) + ')') if n.get('model') else ''}.
  Compliance screen on this text: <b>{esc(n['compliance']['verdict'])}</b>.
  {esc(full['limits'])}
  {('Note: ' + esc(n['fallback_reason'])) if n.get('fallback_reason') else ''}</div>
</body></html>"""


def write_full_report(records: list[dict], out_dir: str, department: Optional[str] = None,
                      end: Optional[str] = None, use_llm: bool = True) -> dict:
    """Write PDF + HTML + JSON + CSV for one department scope. Returns the paths."""
    full = build_full_report(records, department, end, use_llm)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slug = "".join(c if c.isalnum() else "-" for c in (department or "all").lower()).strip("-")
    stem = out / f"weekly-report-{slug}"
    html = render_executive_html(full)
    stem.with_suffix(".html").write_text(html, encoding="utf-8")
    stem.with_suffix(".json").write_text(json.dumps(full, indent=2, default=str), encoding="utf-8")
    stem.with_suffix(".csv").write_text(report_to_csv(full), encoding="utf-8")
    pdf = None
    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(stem.with_suffix(".pdf")))
        pdf = str(stem.with_suffix(".pdf"))
    except Exception:
        pdf = None
    return {"pdf": pdf, "html": str(stem.with_suffix(".html")),
            "json": str(stem.with_suffix(".json")), "csv": str(stem.with_suffix(".csv")),
            "scope": full["scope"], "tickets": full["analytics"]["total_tickets"],
            "engine": full["narrative"]["engine"]}


def write_all_department_reports(records: list[dict], out_dir: str, end: Optional[str] = None,
                                 use_llm: bool = True) -> list[dict]:
    """One report per department present in the data, plus the all-departments report."""
    results = [write_full_report(records, out_dir, None, end, use_llm)]
    for dept in sorted({r.get("assigned_to") for r in records if r.get("assigned_to")}):
        results.append(write_full_report(records, out_dir, dept, end, use_llm))
    return results


def render_html(data: dict) -> str:
    total = data["total_tickets"]
    cats = data["by_category"]
    prios = data["by_priority"]
    depts = data["by_department"]
    days = data["by_day"]
    scope = data["department_filter"] or "All departments"

    cat_rows = "".join(
        f"<tr><td>{c}</td><td class='n'>{n}</td><td class='n'>{_pct(n, total)}</td></tr>"
        for c, n in cats.items())
    prio_rows = "".join(
        f"<tr><td>{p}</td><td class='n'>{n}</td><td class='n'>{_pct(n, total)}</td></tr>"
        for p, n in prios.items())
    dept_rows = "".join(
        f"<tr><td>{d}</td><td class='n'>{n}</td><td class='n'>{_pct(n, total)}</td></tr>"
        for d, n in depts.items())
    peak = max(days, key=lambda d: d["count"]) if days else None
    peak_text = (f"{peak['date']} with {peak['count']} tickets" if peak
                 else "no dated tickets in this window")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 18mm 16mm; }}
  body {{ font-family: Arial, Helvetica, sans-serif; color: #241a12; font-size: 10.5pt; }}
  h1 {{ font-size: 20pt; margin: 0 0 2mm; }}
  h2 {{ font-size: 11pt; margin: 7mm 0 2mm; text-transform: uppercase;
        letter-spacing: .08em; color: #8a6b45; }}
  .meta {{ color: #6b5747; font-size: 9pt; }}
  .kpis {{ display: flex; gap: 6mm; margin: 6mm 0 2mm; }}
  .kpi {{ border: 1px solid #ddcbb4; border-radius: 3mm; padding: 4mm 5mm; flex: 1; }}
  .kpi b {{ display: block; font-size: 17pt; }}
  .kpi span {{ font-size: 8.5pt; color: #6b5747; text-transform: uppercase; letter-spacing: .06em; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 2mm; }}
  th, td {{ text-align: left; padding: 2mm 2mm; border-bottom: 0.3mm solid #e6d8c6; }}
  th {{ font-size: 8.5pt; text-transform: uppercase; letter-spacing: .06em; color: #8a6b45; }}
  td.n, th.n {{ text-align: right; }}
  .foot {{ margin-top: 8mm; font-size: 8pt; color: #6b5747; border-top: 0.3mm solid #e6d8c6; padding-top: 3mm; }}
</style></head><body>
  <h1>Weekly operations summary</h1>
  <div class="meta">Scope: <b>{scope}</b> &middot; generated {data['generated_on']}
    &middot; window {data['date_range']['first'] or '—'} to {data['date_range']['last'] or '—'}</div>

  <div class="kpis">
    <div class="kpi"><b>{total}</b><span>tickets</span></div>
    <div class="kpi"><b>{_pct(prios.get('High', 0), total)}</b><span>high priority</span></div>
    <div class="kpi"><b>{data['rates']['tickets_per_day']}</b><span>tickets / day</span></div>
    <div class="kpi"><b>{len(days)}</b><span>days covered</span></div>
  </div>

  <h2>Peak day</h2>
  <p>{peak_text}.</p>

  <h2>By category</h2>
  <table><tr><th>Category</th><th class="n">Tickets</th><th class="n">Share</th></tr>{cat_rows}</table>

  <h2>By priority</h2>
  <table><tr><th>Priority</th><th class="n">Tickets</th><th class="n">Share</th></tr>{prio_rows}</table>

  <h2>By department</h2>
  <table><tr><th>Department</th><th class="n">Tickets</th><th class="n">Share</th></tr>{dept_rows}</table>

  <div class="foot">MedOps AI &middot; generated from the analytics contract
  (app/analytics.py). Counts are of persisted tickets; empty windows are reported
  as zero rather than estimated.</div>
</body></html>"""


def write_report(records: list[dict], out_path: str, department: Optional[str] = None) -> dict:
    """Write a PDF (and the HTML beside it). Returns what was written and how."""
    data = build_report_data(records, department)
    html = render_html(data)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    html_path = out.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    pdf_written = False
    try:
        from weasyprint import HTML  # imported lazily so the module works without it
        HTML(string=html).write_pdf(str(out))
        pdf_written = True
    except Exception:
        pdf_written = False

    return {
        "pdf": str(out) if pdf_written else None,
        "html": str(html_path),
        "pdf_engine": "weasyprint" if pdf_written else "unavailable (HTML only)",
        "tickets": data["total_tickets"],
        "department": department,
    }


def build_department_reports(records: list[dict], out_dir: str) -> list[dict]:
    """One PDF per department present in the data, plus an all-departments summary."""
    out = Path(out_dir)
    written = [write_report(records, str(out / "summary-all.pdf"))]
    for dept in sorted({r.get("assigned_to") for r in records if r.get("assigned_to")}):
        slug = "".join(c if c.isalnum() else "-" for c in dept.lower()).strip("-")
        written.append(write_report(records, str(out / f"summary-{slug}.pdf"), dept))
    return written
