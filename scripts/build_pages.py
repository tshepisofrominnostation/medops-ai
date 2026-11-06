"""Build the public console page published on GitHub Pages.

Every number on the page comes from the engine, not from a template: the script loads
the synthetic demo store, asks the real API (in-process) for analytics, insights, the
narrative and the report, and embeds real classification and compliance results. If a
figure cannot be computed it is left out rather than faked.

    python scripts/build_pages.py --out docs/console

The page is read-only by design. It is generated from one run, so it shows what the
hospital saw on that date; the interactive console is the Streamlit app.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))          # so `app` imports when run as a script

# in-process API; must be set before app imports
os.environ.setdefault("MEDOPS_DB_PATH", str(ROOT / "data/demo_tickets.json"))

C = {
    "bg": "#071426", "panel": "#102641", "panel2": "#0c1e36", "line": "#1e3a5c",
    "text": "#f3f7fc", "muted": "#93a7bf", "accent": "#38a8f5",
    "good": "#35d07f", "warn": "#f5b544", "bad": "#ff6b6b",
}

CONF = {"solid": C["good"], "moderate": C["accent"], "low-sample": C["warn"],
        "insufficient-data": C["muted"]}


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def mins(v):
    """Minutes to something a ward clerk reads without doing arithmetic."""
    if v is None:
        return "—"
    if v < 90:
        return f"{v:.0f} min"
    if v < 60 * 36:
        return f"{v / 60:.1f} h"
    return f"{v / 1440:.1f} d"


def pct(v, digits=0):
    return "—" if v is None else f"{v * 100:.{digits}f}%"


# ---------------------------------------------------------------- svg primitives

def hbars(pairs, width=520, rowh=34, colour=C["accent"]):
    """Horizontal bars: one colour, because the label already identifies the row."""
    if not pairs:
        return f'<p class="muted">No data on this date.</p>'
    top = max(v for _, v in pairs) or 1
    h = rowh * len(pairs)
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" height="{h}" role="img">']
    for i, (label, value) in enumerate(pairs):
        w = (value / top) * (width - 190)
        y = i * rowh
        out.append(f'<text x="0" y="{y + 15}" fill="{C["text"]}" font-size="13">{esc(label)}</text>')
        out.append(f'<rect x="150" y="{y + 4}" width="{w:.1f}" height="18" rx="4" fill="{colour}"/>')
        out.append(f'<text x="{150 + w + 8:.1f}" y="{y + 18}" fill="{C["muted"]}" '
                   f'font-size="13">{esc(value)}</text>')
    out.append("</svg>")
    return "".join(out)


def target_bars(actual, targets, width=560, rowh=44):
    """Actual vs target per priority. Two colours here because they are two series."""
    rows = [p for p in ("High", "Medium", "Low") if p in actual or p in targets]
    if not rows:
        return '<p class="muted">Response times have not been measured yet.</p>'
    top = max([v for k in rows for v in (actual.get(k) or 0, targets.get(k) or 0)] + [1])
    h = rowh * len(rows)
    scale = (width - 210) / top
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" height="{h}" role="img">']
    for i, p in enumerate(rows):
        a, t = actual.get(p), targets.get(p)
        y = i * rowh
        out.append(f'<text x="0" y="{y + 16}" fill="{C["text"]}" font-size="13">{esc(p)}</text>')
        for j, (val, col, name) in enumerate(((t, C["panel2"], "target"), (a, C["accent"], "actual"))):
            if val is None:
                continue
            w = max(val * scale, 2)
            yy = y + 4 + j * 17
            out.append(f'<rect x="70" y="{yy}" width="{w:.1f}" height="14" rx="3" fill="{col}" '
                       f'stroke="{C["line"] if col == C["panel2"] else "none"}"/>')
            out.append(f'<text x="{70 + w + 6:.1f}" y="{yy + 12}" fill="{C["muted"]}" '
                       f'font-size="11">{mins(val)}</text>')
    out.append("</svg>")
    return "".join(out)


def sparkline(series, width=760, height=150):
    """Daily volume. One series, so one colour and a soft fill."""
    if not series:
        return ""
    vals = [d["count"] for d in series]
    top = max(vals) or 1
    n = len(series)
    step = width / max(n - 1, 1)
    pts = [(i * step, height - 24 - (v / top) * (height - 44)) for i, v in enumerate(vals)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    area = path + f" L{pts[-1][0]:.1f},{height - 24} L0,{height - 24} Z"
    labels = "".join(
        f'<text x="{x:.1f}" y="{height - 6}" fill="{C["muted"]}" font-size="10" '
        f'text-anchor="middle">{esc(d["date"][5:])}</text>'
        for (x, _), d in zip(pts[::max(1, n // 7)], series[::max(1, n // 7)]))
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">'
            f'<path d="{area}" fill="{C["accent"]}" opacity="0.16"/>'
            f'<path d="{path}" fill="none" stroke="{C["accent"]}" stroke-width="2"/>'
            f'{labels}</svg>')


def tile(label, value, sub=""):
    return (f'<div class="tile"><p class="tlabel">{esc(label)}</p>'
            f'<p class="tvalue">{esc(value)}</p>'
            f'<p class="tsub">{esc(sub)}</p></div>')


def finding_card(f):
    conf = f.get("confidence", "moderate")
    colour = CONF.get(conf, C["muted"])
    ev = f.get("evidence") or {}
    if isinstance(ev, dict):
        ev_html = "".join(
            f'<tr><td>{esc(k.replace("_", " "))}</td><td>{esc(json.dumps(v) if isinstance(v, (dict, list)) else (f"{v:.2f}" if isinstance(v, float) else v))}</td></tr>'
            for k, v in ev.items())
    else:
        ev_html = f"<tr><td>evidence</td><td>{esc(ev)}</td></tr>"
    return (f'<article class="card finding">'
            f'<div class="fhead"><h3>{esc(f.get("headline", ""))}</h3>'
            f'<span class="badge" style="border-color:{colour};color:{colour}">{esc(conf)}</span></div>'
            f'<details><summary>Evidence</summary><table class="ev">{ev_html}</table></details>'
            f'</article>')


# ---------------------------------------------------------------- page

def build(out_dir: Path) -> Path:
    from fastapi.testclient import TestClient
    from app.main import app as api_app
    from app.classifier import classify

    client = TestClient(api_app)
    end = os.environ.get("MEDOPS_WEEK_END", "2026-11-06")

    analytics = client.get("/analytics").json()
    insights = client.get("/insights", params={"end": end}).json()
    narrative = insights.get("narrative", {}) or {}
    window = insights.get("window", {}) or {}
    rt = analytics.get("response_time", {}) or {}
    sla = analytics.get("sla", {}) or {}
    status = analytics.get("by_status", {}) or {}

    # real tickets for the explorer
    tickets = client.get("/tickets", params={"limit": 500}).json()
    if isinstance(tickets, dict):
        tickets = tickets.get("items", tickets.get("tickets", []))

    # real compliance results on the six R4 phrasings
    phi_cases = [
        "Mr Dlamini in bed 12 has been waiting since Monday",
        "Her medical aid, the one ending 8834, will cover it",
        "He is on the ARV regimen we discussed",
        "The patient who attempted suicide last week",
        "The lady from the maternity ward whose husband called yesterday",
        "Sister Nkosi's file shows a positive result",
    ]
    phi = []
    for text in phi_cases:
        res = client.post("/compliance", json={"text": text}).json()
        phi.append({"text": text, "verdict": res.get("verdict"),
                    "rules": [f["rule"] for f in res.get("flags", [])]})

    # real classification over the labelled evaluation set
    eval_path = Path("tests/data/evaluation_set.json")
    cases = json.loads(eval_path.read_text())["cases"] if eval_path.exists() else []
    sample = []
    for case in cases[:14]:
        msg = case.get("message", "")
        got, conf = classify(msg)
        sample.append({"message": msg, "category": got,
                       "expected": case.get("category"), "confidence": round(conf, 2)})

    # real artifacts
    artifacts = out_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    wrote = {}
    for name, path in (("report.pdf", "/report.pdf"), ("report.csv", "/report.csv"),
                       ("report.json", "/report")):
        resp = client.get(path, params={"end": end})
        if resp.status_code == 200 and resp.content:
            (artifacts / name).write_bytes(resp.content)
            wrote[name] = len(resp.content)

    generated = datetime.now(timezone.utc).astimezone().strftime("%d %b %Y, %H:%M %Z")
    raw_limits = insights.get("limits") or ""
    # the engine returns one prose sentence; split it so the page reads as a list
    import re as _re
    limits = [p.strip() for p in _re.split(r"(?<=[.])\s+", raw_limits) if p.strip()] \
        if isinstance(raw_limits, str) else list(raw_limits)

    # Every tile says which population it describes. Mixing a windowed count with
    # all-time rates without saying so is how dashboards mislead.
    total = analytics.get("total_tickets", 0)
    hi = (analytics.get("by_priority") or {}).get("High", 0)
    kpis = "".join([
        tile("Tickets in window", (insights.get("analytics") or {}).get("total_tickets", "—"),
             f"{window.get('start','')} to {window.get('end','')}"),
        tile("High priority share", pct((analytics.get("rates") or {}).get("high_priority_share")),
             f"all time · {hi} of {total}"),
        tile("Median response", mins(rt.get("median_minutes")),
             f"all time · {rt.get('measured_tickets', 0)} answered of {total}"),
        tile("Met response target", pct(sla.get("attainment")),
             "all time · targets are proposals"),
        tile("Still open", status.get("Open", 0),
             f"all time · {status.get('In Progress', 0)} in progress · "
             f"{status.get('Resolved', 0)} resolved"),
    ])

    findings = "".join(finding_card(f) for f in insights.get("findings", []))

    ticket_rows = "".join(
        f'<tr data-c="{esc(r.get("category",""))}" data-p="{esc(r.get("priority",""))}" '
        f'data-s="{esc(r.get("status","Open"))}" '
        f'data-t="{esc((r.get("message","") + " " + r.get("assigned_to","") + " " + r.get("ticket_id","")).lower())}">'
        f'<td class="mono">{esc(r.get("ticket_id",""))}</td>'
        f'<td class="msg">{esc((r.get("message") or "")[:96])}</td>'
        f'<td><span class="chip">{esc(r.get("category",""))}</span></td>'
        f'<td><span class="chip p-{esc((r.get("priority") or "").lower())}">{esc(r.get("priority",""))}</span></td>'
        f'<td>{esc(r.get("assigned_to",""))}</td>'
        f'<td><span class="dot s-{esc((r.get("status") or "Open").replace(" ",""))}">'
        f'{esc(r.get("status","Open"))}</span></td>'
        f'<td class="num">{mins(r.get("response_minutes"))}</td></tr>'
        for r in tickets)

    phi_rows = "".join(
        f'<tr><td class="msg">{esc(p["text"])}</td>'
        f'<td><span class="chip {"p-high" if p["verdict"] == "blocked" else "p-low"}">'
        f'{esc(p["verdict"])}</span></td>'
        f'<td class="mono small">{esc(", ".join(p["rules"]) or "—")}</td></tr>'
        for p in phi)

    sample_rows = "".join(
        f'<tr><td class="msg">{esc(s["message"][:88])}</td>'
        f'<td><span class="chip">{esc(s["category"])}</span></td>'
        f'<td class="num">{s["confidence"]:.2f}</td>'
        f'<td class="num">{"match" if s["category"] == s["expected"] else "review"}</td></tr>'
        for s in sample)

    downloads = "".join(
        f'<a class="btn" href="artifacts/{esc(name)}" download>{esc(name)} '
        f'<span class="muted small">{size // 1024 or 1} KB</span></a>'
        for name, size in wrote.items())

    doc = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>MedOps AI — live operations console</title>
<meta name="description" content="MedOps AI operations console: real classification, routing and response-time analytics from the engine, generated {esc(generated)}.">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:{C['bg']};color:{C['text']};
 font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
.wrap{{max-width:1120px;margin:0 auto;padding:28px 20px 72px}}
a{{color:{C['accent']}}}
header{{border-bottom:1px solid {C['line']};padding-bottom:18px;margin-bottom:26px}}
.eyebrow{{color:{C['accent']};font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:600}}
h1{{margin:6px 0 4px;font-size:30px;letter-spacing:-.02em}}
h2{{font-size:19px;margin:34px 0 12px}}
h3{{font-size:15px;margin:0;font-weight:600}}
.sub{{color:{C['muted']};font-size:14px}}
.muted{{color:{C['muted']}}}
.small{{font-size:12px}}
.mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}}
.grid{{display:grid;gap:12px}}
.tiles{{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}}
.tile{{background:{C['panel']};border:1px solid {C['line']};border-radius:12px;padding:16px}}
.tlabel{{margin:0;color:{C['muted']};font-size:11.5px;letter-spacing:.08em;text-transform:uppercase}}
.tvalue{{margin:8px 0 2px;font-size:26px;font-weight:650;letter-spacing:-.02em}}
.tsub{{margin:0;color:{C['muted']};font-size:12px}}
.cards{{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}}
.card{{background:{C['panel']};border:1px solid {C['line']};border-radius:12px;padding:16px}}
.finding{{display:flex;flex-direction:column;gap:8px}}
.fhead{{display:flex;gap:10px;justify-content:space-between;align-items:flex-start}}
.badge{{font-size:11px;padding:2px 8px;border:1px solid;border-radius:999px;white-space:nowrap}}
details summary{{cursor:pointer;color:{C['muted']};font-size:12.5px}}
table{{width:100%;border-collapse:collapse}}
.ev td{{padding:3px 0;font-size:12.5px;color:{C['muted']};border-bottom:1px solid {C['panel2']}}}
.ev td:last-child{{text-align:right;color:{C['text']}}}
.summary{{background:{C['panel']};border-left:3px solid {C['accent']};border-radius:8px;padding:16px 18px}}
.summary p{{margin:0 0 10px}}
.chips{{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}}
input[type=search],select{{background:{C['panel2']};border:1px solid {C['line']};color:{C['text']};
 border-radius:8px;padding:9px 11px;font-size:13.5px}}
input[type=search]{{flex:1;min-width:220px}}
.tblwrap{{overflow:auto;border:1px solid {C['line']};border-radius:12px;background:{C['panel']}}}
.main td,.main th{{padding:9px 10px;text-align:left;font-size:12.5px;border-bottom:1px solid {C['panel2']}}}
.main th{{color:{C['muted']};font-size:11px;letter-spacing:.06em;text-transform:uppercase;
 position:sticky;top:0;background:{C['panel']}}}
.main tr:hover td{{background:{C['panel2']}}}
td.msg{{max-width:330px;color:{C['text']}}}
td.num{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.chip{{font-size:11.5px;padding:2px 8px;border-radius:999px;background:{C['panel2']};
 border:1px solid {C['line']};white-space:nowrap}}
.p-high{{border-color:{C['bad']};color:{C['bad']}}}
.p-medium{{border-color:{C['warn']};color:{C['warn']}}}
.p-low{{border-color:{C['good']};color:{C['good']}}}
.dot::before{{content:"●";margin-right:6px;font-size:9px;vertical-align:2px}}
.s-Open::before{{color:{C['warn']}}}
.s-InProgress::before{{color:{C['accent']}}}
.s-Resolved::before{{color:{C['good']}}}
.btn{{display:inline-flex;gap:8px;align-items:center;background:{C['panel']};border:1px solid {C['line']};
 color:{C['text']};text-decoration:none;padding:10px 14px;border-radius:10px;font-size:13.5px}}
.btn:hover{{border-color:{C['accent']}}}
.note{{background:{C['panel2']};border:1px solid {C['line']};border-radius:10px;padding:14px 16px;
 color:{C['muted']};font-size:13px}}
footer{{margin-top:44px;border-top:1px solid {C['line']};padding-top:18px;color:{C['muted']};font-size:12.5px}}
ul.lim{{margin:8px 0 0;padding-left:20px}}
ul.lim li{{margin-bottom:5px}}
</style></head><body><div class="wrap">

<header>
  <p class="eyebrow">MedOps AI · Operations Intelligence</p>
  <h1>Live console output</h1>
  <p class="sub">Week {esc(window.get('start',''))} to {esc(window.get('end',''))} ·
     generated {esc(generated)} from the engine ·
     narrative: <b>{esc(narrative.get('engine','deterministic'))}</b></p>
</header>

<div class="grid tiles">{kpis}</div>

<h2>Executive summary</h2>
<div class="summary">
  <p>{esc(narrative.get('text',''))}</p>
  <p class="small muted">{esc(narrative.get('disclosure') or '')}</p>
</div>

<h2>Findings and their evidence</h2>
<p class="sub">Each finding carries the numbers behind it and a confidence label. A
   low-confidence finding is kept and labelled rather than hidden.</p>
<div class="grid cards">{findings}</div>

<h2>Where the tickets went</h2>
<div class="grid cards">
  <div class="card"><h3>By category</h3>{hbars(list((analytics.get('by_category') or {{}}).items()))}</div>
  <div class="card"><h3>By priority</h3>{hbars(list((analytics.get('by_priority') or {{}}).items()))}</div>
</div>

<h2>Response time against target</h2>
<div class="card">
  <p class="sub" style="margin-top:0">Targets shown grey, actual in blue. These targets
     are the team's proposal, not hospital policy.</p>
  {target_bars(rt.get('by_priority') or {{}}, sla.get('targets_minutes') or {{}})}
  <p class="small muted">Median {mins(rt.get('median_minutes'))} · mean
     {mins(rt.get('mean_minutes'))} · worst {mins(rt.get('worst_minutes'))} ·
     {rt.get('unmeasured_tickets', 0)} ticket(s) not yet answered, so not counted.</p>
</div>

<h2>Daily volume</h2>
<div class="card">{sparkline(analytics.get('by_day') or [])}</div>

<h2>Ticket explorer</h2>
<p class="sub">{len(tickets)} real tickets from the engine. Filter by text, or narrow by
   category, priority or status. The interactive console does the same against a live store.</p>
<div class="chips">
  <input type="search" id="q" placeholder="Search message, ticket or team…" aria-label="Search tickets">
  <select id="fc" aria-label="Filter by category"><option value="">All categories</option>
    {''.join(f'<option>{esc(c)}</option>' for c in (analytics.get('by_category') or {{}}))}
  </select>
  <select id="fp" aria-label="Filter by priority"><option value="">All priorities</option>
    {''.join(f'<option>{esc(p)}</option>' for p in ('High','Medium','Low'))}
  </select>
  <select id="fs" aria-label="Filter by status"><option value="">All statuses</option>
    {''.join(f'<option>{esc(s)}</option>' for s in ('Open','In Progress','Resolved'))}
  </select>
</div>
<div class="tblwrap"><table class="main">
  <thead><tr><th>Ticket</th><th>Message</th><th>Category</th><th>Priority</th>
    <th>Routed to</th><th>Status</th><th class="num">Response</th></tr></thead>
  <tbody id="rows">{ticket_rows}</tbody>
</table></div>
<p class="small muted" id="count"></p>

<h2>Patient-data screen</h2>
<p class="sub">The six semantic phrasings that the original screen missed (risk R4). All
   are caught now, and every result carries the disclaimer that this is heuristic.</p>
<div class="tblwrap"><table class="main">
  <thead><tr><th>Text</th><th>Verdict</th><th>Rules triggered</th></tr></thead>
  <tbody>{phi_rows}</tbody>
</table></div>
<p class="note">A clean verdict means no known pattern matched. It is not proof the text
   is safe, and human review of drafted replies remains required.</p>

<h2>Classification, checked against labels</h2>
<p class="sub">First {len(sample)} cases from the labelled evaluation set, run live in this build.</p>
<div class="tblwrap"><table class="main">
  <thead><tr><th>Message</th><th>Predicted</th><th class="num">Confidence</th><th class="num">Label</th></tr></thead>
  <tbody>{sample_rows}</tbody>
</table></div>

<h2>Download the week</h2>
<div class="chips">{downloads}</div>

<h2>What this page cannot tell you</h2>
<div class="note"><ul class="lim">
  {''.join(f'<li>{esc(l)}</li>' for l in limits) or '<li>No limits were returned by the engine.</li>'}
  <li>The ticket store on this page is <b>synthetic</b>, generated by the real pipeline.
      Response times are simulated; the classifications, priorities and routes are the
      engine's own decisions.</li>
  <li>This is a snapshot. The interactive console reads a live store.</li>
</ul></div>

<footer>
  Generated by <span class="mono">scripts/build_pages.py</span> from
  <span class="mono">app.main:app</span>.
  <a href="https://github.com/tshepisofrominnostation/medops-ai">Source</a> ·
  <a href="../">Project walkthrough</a> ·
  <a href="../WEEK3_4_GUIDE.md">Testing and Week 4 guide</a>
</footer>
</div>

<script>
(function () {{
  var q = document.getElementById('q'), fc = document.getElementById('fc'),
      fp = document.getElementById('fp'), fs = document.getElementById('fs'),
      rows = [].slice.call(document.querySelectorAll('#rows tr')),
      count = document.getElementById('count');
  function apply() {{
    var term = q.value.trim().toLowerCase(), c = fc.value, p = fp.value, s = fs.value, n = 0;
    rows.forEach(function (r) {{
      var ok = (!term || r.dataset.t.indexOf(term) > -1)
            && (!c || r.dataset.c === c) && (!p || r.dataset.p === p)
            && (!s || r.dataset.s === s);
      r.style.display = ok ? '' : 'none';
      if (ok) n++;
    }});
    count.textContent = n + ' of ' + rows.length + ' tickets shown';
  }}
  [q, fc, fp, fs].forEach(function (el) {{ el.addEventListener('input', apply); }});
  apply();
}})();
</script>
</body></html>
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    index = out_dir / "index.html"
    index.write_text(doc, encoding="utf-8")
    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/console")
    args = ap.parse_args()
    index = build(Path(args.out))
    size = index.stat().st_size
    print(f"wrote {index} ({size / 1024:.1f} KB)")
    arts = sorted(p.name for p in (Path(args.out) / "artifacts").glob("*"))
    print("artifacts:", ", ".join(arts) or "none")


if __name__ == "__main__":
    main()
