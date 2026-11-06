"""One-click weekly summary report, one PDF per department (S2-3).

Renders an HTML summary from the analytics contract and converts it to PDF with
WeasyPrint. If WeasyPrint is unavailable the HTML is still written, so the
deliverable degrades rather than fails.
"""
from datetime import date
from pathlib import Path
from typing import Optional

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
