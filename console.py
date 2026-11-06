"""MedOps AI — Operations Console (Week 3 and Week 4).

This is the working surface, not a read-only dashboard. It covers the four things
Week 3 asks the team to actually DO with the platform:

  1. Intake        submit a raw hospital request and see what the engine decided
  2. Work the queue  move tickets Open -> In Progress -> Resolved (this is what makes
                   response time measurable; without it analytics has nothing to show)
  3. Weekly insight  what happened this week, with the evidence and honest caveats
  4. Reports       per-department PDF, CSV and JSON for the department head

Design rules
  - The backend owns every number. This file only displays what the API returns, so
    the screen can never disagree with the report.
  - Every screen names its data source and its limits.
  - No silent failure: a dead API produces an instruction, not an empty chart.

Run:  streamlit run console.py     (with the API up: uvicorn app.main:app)
"""
import json
import os
from datetime import date, timedelta

import altair as alt
import pandas as pd
import requests
import streamlit as st

# Transport. Two modes, one code path:
#
#   MEDOPS_API_URL set   -> talk to that server over HTTP (local dev, or API deployed
#                           separately from the UI)
#   MEDOPS_API_URL unset -> run the same FastAPI app in-process
#
# The in-process mode exists so the console can be deployed as a single Streamlit app
# with no backend service. It is not a second implementation: it calls app.main:app,
# the same routes a remote client would hit, so the screen still cannot disagree with
# the report. The only difference is that the process holds the ticket store itself,
# which means data does not survive a restart on an ephemeral host. The sidebar says so.
API_URL = os.getenv("MEDOPS_API_URL", "").rstrip("/")
IN_PROCESS = not API_URL
HTTP_FALLBACK = "http://127.0.0.1:8000"

# Where the store lives, shown in the sidebar so nobody has to guess.
DB_PATH = os.getenv("MEDOPS_DB_PATH") or "data/tickets_processed.json"


@st.cache_resource(show_spinner=False)
def _inproc_client():
    """The real FastAPI app, called in-process. Cached across reruns."""
    from fastapi.testclient import TestClient
    from app.main import app as _app
    return TestClient(_app)


def _send(method: str, path: str, **kw):
    """Issue one request through whichever transport is configured."""
    if IN_PROCESS:
        kw.pop("timeout", None)          # TestClient has no timeout argument
        return _inproc_client().request(method, path, **kw)
    return requests.request(method, f"{API_URL}{path}", timeout=kw.pop("timeout", 30), **kw)


class ApiError(Exception):
    def __init__(self, message, hint):
        super().__init__(message)
        self.hint = hint


def _read(method: str, path: str, **kw):
    """Shared error handling: every failure becomes something a tester can act on."""
    try:
        r = _send(method, path, **kw)
    except requests.exceptions.ConnectionError:
        raise ApiError("Cannot reach the MedOps API.",
                       f"Start it first: <code>uvicorn app.main:app --reload</code> "
                       f"(expected at {API_URL}), or unset <code>MEDOPS_API_URL</code> "
                       f"to run the engine in-process.")
    except requests.exceptions.Timeout:
        raise ApiError("The API took too long to answer.", "Try again, then check the API logs.")
    except Exception as exc:                      # in-process import or runtime failure
        raise ApiError("The classification engine failed to load.",
                       f"{type(exc).__name__}: {exc}")
    if r.status_code >= 500:
        detail = ""
        try:
            detail = r.json().get("detail", "")
        except Exception:
            pass
        raise ApiError(f"The API failed ({r.status_code}).", detail or "Check the API log.")
    if r.status_code >= 400:
        detail = ""
        try:
            body = r.json()
            detail = body.get("detail") or body.get("error") or str(body)
        except Exception:
            detail = r.text[:200]
        raise ApiError(f"Request rejected ({r.status_code}).", str(detail))
    return r


def api(method: str, path: str, **kw):
    r = _read(method, path, **kw)
    try:
        return r.json()
    except ValueError:
        return r.text


def api_bytes(path: str, **kw):
    """For PDF and CSV: bytes, or None when the endpoint could not produce them."""
    try:
        return _read("GET", path, **kw).content
    except ApiError:
        return None


st.set_page_config(page_title="MedOps AI · Operations Console", page_icon="🏥",
                   layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------- palette + css
C = {"page": "#071426", "panel": "#102641", "panel2": "#0d2038", "border": "#234363",
     "text": "#f3f7fc", "muted": "#a9bdd2", "blue": "#38a8f5", "cyan": "#42c7d5",
     "amber": "#f5b544", "red": "#f06464", "green": "#31c48d", "purple": "#8b7cf6"}
CATEGORY_COLOURS = {"IT & Medical Tech": C["blue"], "HR": C["purple"],
                    "Finance": C["green"], "Operations": C["cyan"]}
PRIORITY_COLOURS = {"High": C["red"], "Medium": C["amber"], "Low": C["green"]}

st.markdown(f"""<style>
.stApp {{ background: radial-gradient(ellipse at 80% 0%, #102b4b 0%, transparent 45%), {C['page']};
         color: {C['text']}; }}
.block-container {{ max-width: 1500px; padding-top: 2.2rem; padding-bottom: 3rem; }}
[data-testid="stSidebar"] {{ background: linear-gradient(180deg,#0d2340 0%,#09182c 100%);
         border-right: 1px solid {C['border']}; }}
[data-testid="stSidebar"] * {{ color: {C['text']}; }}
#MainMenu, footer {{ visibility: hidden; }}
h1,h2,h3,h4 {{ color: {C['text']} !important; letter-spacing: -0.02em; }}
p, label, span, div {{ color: {C['text']}; }}
.eyebrow {{ color: {C['cyan']}; text-transform: uppercase; letter-spacing: .13em;
         font-size: .7rem; font-weight: 700; }}
.sub {{ color: {C['muted']}; font-size: .95rem; margin-top: -.4rem; }}
.panel {{ background: linear-gradient(145deg,#122b48 0%,#0e223b 100%);
         border: 1px solid {C['border']}; border-radius: 14px; padding: 1.05rem 1.2rem; }}
.tile {{ background: linear-gradient(145deg,#122b48 0%,#0e223b 100%);
         border: 1px solid {C['border']}; border-radius: 14px; padding: .95rem 1.1rem; height: 100%; }}
.tile .k {{ color: {C['muted']}; text-transform: uppercase; letter-spacing: .07em;
         font-size: .68rem; font-weight: 700; }}
.tile .v {{ font-size: 1.85rem; font-weight: 800; line-height: 1.15; margin-top: .25rem; }}
.tile .d {{ font-size: .76rem; color: {C['muted']}; margin-top: .15rem; }}
.pill {{ display: inline-block; padding: .12rem .5rem; border-radius: 999px;
         font-size: .72rem; font-weight: 700; border: 1px solid; }}
.note {{ border-left: 3px solid {C['blue']}; background: #0f2744; padding: .7rem .9rem;
         border-radius: 8px; font-size: .85rem; color: {C['muted']}; }}
.warn {{ border-left: 3px solid {C['amber']}; background: #2a2413; padding: .7rem .9rem;
         border-radius: 8px; font-size: .85rem; color: #f7e9c8; }}
.stop {{ border-left: 3px solid {C['red']}; background: #2b1618; padding: .7rem .9rem;
         border-radius: 8px; font-size: .85rem; color: #fbdada; }}
.ok {{ border-left: 3px solid {C['green']}; background: #0f2a22; padding: .7rem .9rem;
         border-radius: 8px; font-size: .85rem; color: #d3f5e7; }}
.reply {{ background: #0b1d35; border: 1px solid {C['border']}; border-radius: 10px;
         padding: 1rem 1.1rem; white-space: pre-wrap; line-height: 1.55; }}
div[data-testid="stMetricValue"] {{ color: {C['text']}; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; }}
.stTabs [aria-selected="true"] {{ color: {C['cyan']} !important; }}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------- api client
def show_api_error(e: ApiError):
    st.markdown(f'<div class="stop"><b>{e}</b><br>{e.hint}</div>', unsafe_allow_html=True)


def fetch(path, **kw):
    try:
        return api("GET", path, **kw)
    except ApiError as e:
        show_api_error(e)
        st.stop()


# ------------------------------------------------------------------- formatting
def mins(v):
    if v is None:
        return "—"
    if v < 60:
        return f"{v:.0f} min"
    h, rem = divmod(int(round(v)), 60)
    return f"{h} h {rem} min" if rem else f"{h} h"


def pct(v, digits=0):
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def tile(label, value, detail="", colour=None):
    style = f" style='color:{colour}'" if colour else ""
    st.markdown(f"""<div class="tile"><div class="k">{label}</div>
        <div class="v"{style}>{value}</div><div class="d">{detail}</div></div>""",
                unsafe_allow_html=True)


def priority_pill(p):
    col = PRIORITY_COLOURS.get(p, C["muted"])
    return (f"<span class='pill' style='color:{col};border-color:{col}'>"
            f"{p or 'unknown'}</span>")


# ------------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown(f"""<div style="text-align:center;padding:.6rem 0 1rem">
        <div style="font-size:2.4rem">🏥</div>
        <div style="font-size:1.4rem;font-weight:800">MedOps AI</div>
        <div style="font-size:.8rem;color:{C['muted']}">Operations Console · Week 3</div></div>""",
                unsafe_allow_html=True)
    st.divider()
    if IN_PROCESS:
        st.markdown(f"""<div class="note"><b>Single-service mode</b><br>
            The engine runs inside this app, so there is no API to start. The ticket
            store is <code>{DB_PATH}</code>.</div>""", unsafe_allow_html=True)
        st.caption("On a hosted demo the store is ephemeral: tickets added today are "
                   "lost when the host restarts. The numbers stay reproducible because "
                   "the same pipeline regenerates them.")
    try:
        health = api("GET", "/health", timeout=6)
        st.markdown(f"""<div class="ok"><b>API connected</b><br>
            version {health.get('version')}<br>
            reply writer: {health.get('reply_writer')}<br>
            narrative: {health.get('narrative')}<br>
            semantic model: {health.get('semantic_classifier', {}).get('trained_on', 0)} docs
            </div>""", unsafe_allow_html=True)
    except ApiError as e:
        show_api_error(e)
        health = {}
    if IN_PROCESS:
        from pathlib import Path as _Path
        _demo = _Path("data/demo_tickets.json")
        _store = _Path(DB_PATH)
        _empty = not _store.exists() or not _store.read_text(encoding="utf-8").strip(" \n[]")
        if _empty and _demo.exists():
            st.markdown('<div class="warn">This deployment starts empty. Load 21 days of '
                        '<b>synthetic</b> history to see the weekly insight and reports.</div>',
                        unsafe_allow_html=True)
            if st.button("Load demo history", type="primary", width="stretch"):
                import shutil
                _store.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(_demo, _store)
                st.cache_data.clear()
                st.rerun()
            st.caption("Synthetic data from the real pipeline. It never touches a "
                       "hospital file, and every record is tagged synthetic.")
    st.divider()
    if st.button("↻  Reload data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"API: `{API_URL or 'in-process'}`")
    st.caption("Every figure on screen is computed by the API layer from persisted "
               "tickets, never in this file.")

tabs = st.tabs(["➕  New request", "🗂  Work the queue", "📈  Weekly insight", "📄  Reports"])


# ============================================================== 1. INTAKE
with tabs[0]:
    st.markdown('<div class="eyebrow">Step 1</div>', unsafe_allow_html=True)
    st.title("Log a hospital request")
    st.markdown('<div class="sub">Paste the message exactly as it arrived. The engine '
                'classifies it, sets priority, routes it and drafts the reply.</div>',
                unsafe_allow_html=True)
    st.write("")

    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.form("intake", clear_on_submit=False):
            message = st.text_area(
                "The request",
                height=150,
                placeholder='"The patient monitoring terminal in Bay 3 keeps disconnecting '
                            'from the network." - Dr. S. Khumalo (Emergency Ward)')
            sender = st.text_input("Sender override (optional)",
                                  placeholder="Dr. S. Khumalo (Emergency Ward)")
            use_override = st.checkbox("Use the override instead of the signature in the message",
                                       value=False)
            submitted = st.form_submit_button("Classify and draft", type="primary",
                                              width="stretch")

    with right:
        st.markdown('<div class="panel"><b>What you can paste</b><br>'
                    '<span style="font-size:.86rem;color:#a9bdd2">'
                    'A ward complaint, a signed email, a forwarded message.<br><br>'
                    '<b>Two examples that are graded in the test set</b><br>'
                    '• Telemetry terminal dropping off the network<br>'
                    '• Medical-aid invoice query<br><br>'
                    'Minimum 5 characters, maximum 2000.</span></div>',
                    unsafe_allow_html=True)

    if submitted:
        payload = {"message": message}
        if use_override and sender.strip():
            payload["sender"] = sender.strip()
        try:
            with st.spinner("Classifying, prioritising, drafting…"):
                result = api("POST", "/replies", json=payload)
        except ApiError as e:
            show_api_error(e)
            result = None
        if result:
            t, rep, comp = result["ticket"], result["reply"], result["compliance"]
            st.write("")
            a, b, c, d = st.columns(4)
            with a: tile("Ticket", t["ticket_id"], t["timestamp"][:16].replace("T", " "))
            with b: tile("Category", t["category"])
            with c: tile("Priority", t["priority"], t["assigned_to"],
                         PRIORITY_COLOURS.get(t["priority"]))
            with d: tile("Routed to", t["assigned_to"].split(" on-call")[0])

            st.write("")
            n1, n2 = st.columns([3, 2], gap="large")
            with n1:
                st.markdown("##### Drafted reply")
                st.markdown(f'<div class="reply">{rep["reply_body"]}</div>', unsafe_allow_html=True)
                st.caption(f"Tone: {rep['tone']} · engine: {rep['generated_by']}"
                           + (f" ({rep['model']})" if rep.get("model") else "")
                           + f" · sender register: {rep.get('sender_tone') or 'not detected'}")
            with n2:
                st.markdown("##### Safety screen")
                verdict = comp["verdict"]
                cls = {"blocked": "stop", "review": "warn", "clean": "ok"}[verdict]
                st.markdown(f'<div class="{cls}"><b>{verdict.upper()}</b><br>'
                            f'{comp["counts"]["block"]} blocking, {comp["counts"]["review"]} '
                            f'to review</div>', unsafe_allow_html=True)
                for f in comp.get("flags", []):
                    st.markdown(f"- **{f['rule']}** ({f['severity']}): {f['why']}")
                st.caption(comp.get("disclaimer", ""))
                st.markdown("##### Second opinion")
                try:
                    check = api("POST", "/check/category", json={"message": payload["message"]})
                    agree = check["agree"]
                    st.markdown(
                        f"{'✅ Agrees' if agree else '⚠️ Disagrees'} with the rule engine. "
                        f"Semantic: **{check['semantic_category'] or 'no match'}** "
                        f"(similarity {check['semantic_similarity']}).")
                    if check["needs_review"]:
                        st.markdown('<div class="warn">A human should confirm this category '
                                    'before the ticket is worked.</div>', unsafe_allow_html=True)
                except ApiError as e:
                    st.caption(f"Second opinion unavailable: {e}")

            st.write("")
            st.info("The ticket is saved. Open **Work the queue** to mark it In Progress — "
                    "that is what starts the response-time clock.")
            st.caption(f"Summary: {t['summary']}")


# ============================================================== 2. QUEUE
with tabs[1]:
    st.markdown('<div class="eyebrow">Step 2</div>', unsafe_allow_html=True)
    st.title("Work the queue")
    st.markdown('<div class="sub">Move tickets through their lifecycle. Response time and '
                'SLA performance only exist because staff record this.</div>',
                unsafe_allow_html=True)

    f1, f2, f3, f4 = st.columns([1, 1, 1, 2])
    with f1:
        status_f = st.selectbox("Status", ["All", "Open", "In Progress", "Resolved"])
    with f2:
        cat_f = st.selectbox("Category", ["All", "IT & Medical Tech", "HR", "Finance", "Operations"])
    with f3:
        pri_f = st.selectbox("Priority", ["All", "High", "Medium", "Low"])
    with f4:
        search = st.text_input("Search the summary", placeholder="e.g. lift, invoice, ventilator")

    params = {}
    if status_f != "All":
        params["status"] = status_f
    if cat_f != "All":
        params["category"] = cat_f
    if pri_f != "All":
        params["priority"] = pri_f
    rows = fetch("/tickets", params=params)
    rows = [r for r in rows if search.lower() in (r.get("summary", "") + r.get("sender", "")).lower()] \
        if search else rows

    if not rows:
        st.markdown('<div class="note">Nothing matches these filters. '
                    'Log a request on the first tab, or clear the filters.</div>',
                    unsafe_allow_html=True)
    else:
        open_n = sum(1 for r in rows if r["status"] == "Open")
        prog_n = sum(1 for r in rows if r["status"] == "In Progress")
        done_n = sum(1 for r in rows if r["status"] == "Resolved")
        k1, k2, k3, k4 = st.columns(4)
        with k1: tile("In view", len(rows), "matching the filters")
        with k2: tile("Open", open_n, "not yet answered", C["amber"] if open_n else None)
        with k3: tile("In progress", prog_n, "being worked")
        with k4: tile("Resolved", done_n, "closed", C["green"])

        st.write("")
        st.markdown(f"<div class='note'><b>Oldest first.</b> Answer the top ticket first. "
                    f"Targets shown are the team's <i>proposed</i> response times, "
                    f"not hospital policy.</div>", unsafe_allow_html=True)
        st.write("")

        rows_sorted = sorted(rows, key=lambda r: r.get("timestamp", ""))
        for r in rows_sorted[:60]:
            with st.container():
                st.markdown(f"""<div class="panel" style="margin-bottom:.7rem">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                      <div><b>{r['ticket_id']}</b> &nbsp; {priority_pill(r['priority'])}
                        &nbsp;<span style="color:{C['muted']};font-size:.85rem">
                        {r['category']} · {r['assigned_to']}</span></div>
                      <div style="color:{C['muted']};font-size:.8rem">
                        {r['timestamp'][:16].replace('T',' ')} · {r['status']}</div>
                    </div>
                    <div style="margin-top:.45rem;font-size:.92rem">{r.get('summary','')}</div>
                    <div style="margin-top:.3rem;color:{C['muted']};font-size:.78rem">
                      {('First response: ' + mins(r['response_minutes'])) if r.get('response_minutes') is not None else 'No response recorded yet'}
                      &nbsp;·&nbsp; sender: {r.get('sender','—')}</div>
                    </div>""", unsafe_allow_html=True)
                b1, b2, b3, _ = st.columns([1, 1, 1, 3])
                tid = r["ticket_id"]
                if r["status"] == "Open":
                    if b1.button("▶ Start", key=f"start-{tid}", width="stretch"):
                        try:
                            api("POST", f"/tickets/{tid}/status", json={"status": "In Progress"})
                            st.cache_data.clear()
                            st.rerun()
                        except ApiError as e:
                            show_api_error(e)
                if r["status"] in ("Open", "In Progress"):
                    if b2.button("✓ Resolve", key=f"done-{tid}", width="stretch"):
                        try:
                            api("POST", f"/tickets/{tid}/status", json={"status": "Resolved"})
                            st.cache_data.clear()
                            st.rerun()
                        except ApiError as e:
                            show_api_error(e)
                if r["status"] == "Resolved":
                    if b3.button("↺ Reopen", key=f"reopen-{tid}", width="stretch"):
                        try:
                            api("POST", f"/tickets/{tid}/status", json={"status": "In Progress"})
                            st.cache_data.clear()
                            st.rerun()
                        except ApiError as e:
                            show_api_error(e)
        if len(rows_sorted) > 60:
            st.caption(f"Showing the oldest 60 of {len(rows_sorted)} matching tickets.")


# ============================================================== 3. INSIGHTS
with tabs[2]:
    st.markdown('<div class="eyebrow">Step 3</div>', unsafe_allow_html=True)
    st.title("Weekly insight")
    st.markdown('<div class="sub">What happened, why it matters, and how much to trust it.</div>',
                unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        dept_list = ["All departments"] + sorted(
            {r["assigned_to"] for r in fetch("/tickets", params={"limit": 1000}) if r.get("assigned_to")})
        dept = st.selectbox("Scope", dept_list)
    with c2:
        end = st.date_input("Week ending", value=date.today())
    with c3:
        st.write("")
        st.write("")
        refresh = st.button("Analyse", type="primary", width="stretch")

    params = {"end": end.isoformat()}
    if dept != "All departments":
        params["department"] = dept
    ins = fetch("/insights", params=params)
    a = ins["analytics"]
    rt, sla = a["response_time"], a["sla"]

    st.write("")
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: tile("Tickets", a["total_tickets"], f"{ins['window']['start']} → {ins['window']['end']}")
    with k2: tile("High priority", a["by_priority"]["High"],
                  pct(a["by_priority"]["High"] / a["total_tickets"]) + " of week" if a["total_tickets"] else "no tickets",
                  PRIORITY_COLOURS["High"])
    with k3: tile("Median response", mins(rt["median_minutes"]),
                  f"across {rt['measured_tickets']} answered")
    with k4: tile("Met target", pct(sla["attainment"]),
                  f"n={sla['measured_tickets']} answered",
                  C["green"] if (sla["attainment"] or 0) >= 0.9 else C["amber"])
    with k5: tile("Unanswered", a["by_status"]["Open"], "still Open",
                  C["amber"] if a["by_status"]["Open"] else None)

    st.write("")
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.markdown("##### Executive summary")
        nar = ins["narrative"]
        for line in nar["text"].split("\n"):
            if line.strip():
                st.markdown(line)
        engine = nar["engine"]
        cap = f"Written by the {engine} engine"
        if nar.get("model"):
            cap += f" ({nar['model']})"
        if nar.get("fallback_reason"):
            cap += f" · fell back: {nar['fallback_reason']}"
        st.caption(cap + f" · compliance: {nar['compliance']['verdict']}")
        st.caption(nar["disclosure"])

        st.write("")
        st.markdown("##### Findings and their evidence")
        conf_badge = {"solid": ("ok", "solid evidence"),
                      "low-sample": ("warn", "small sample"),
                      "insufficient-data": ("warn", "not enough data")}
        for f in ins["findings"]:
            cls, label = conf_badge.get(f["confidence"], ("note", f["confidence"]))
            st.markdown(f'<div class="{cls}" style="margin-bottom:.45rem">'
                        f'{f["headline"]}<br><span style="font-size:.75rem;opacity:.85">'
                        f'{label} · evidence: {f["evidence"]}</span></div>',
                        unsafe_allow_html=True)

    with right:
        st.markdown("##### Volume by category")
        cat_df = pd.DataFrame([{"category": k, "tickets": v}
                               for k, v in a["by_category"].items()])
        st.altair_chart(
            alt.Chart(cat_df).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                       stroke=None).encode(
                y=alt.Y("category:N", sort="-x", title=None,
                        axis=alt.Axis(labelColor=C["muted"], labelLimit=160)),
                x=alt.X("tickets:Q", title="tickets", axis=alt.Axis(labelColor=C["muted"],
                                                                   gridColor="#1b3355")),
                color=alt.Color("category:N",
                                scale=alt.Scale(domain=list(CATEGORY_COLOURS),
                                                range=list(CATEGORY_COLOURS.values())),
                                legend=None),
                tooltip=["category", "tickets"]).properties(height=170),
            width="stretch")

        st.markdown("##### Priority mix")
        pri_df = pd.DataFrame([{"priority": k, "tickets": v} for k, v in a["by_priority"].items()])
        st.altair_chart(
            alt.Chart(pri_df).mark_arc(innerRadius=42, stroke=None).encode(
                theta=alt.Theta("tickets:Q"),
                color=alt.Color("priority:N",
                                scale=alt.Scale(domain=list(PRIORITY_COLOURS),
                                                range=list(PRIORITY_COLOURS.values())),
                                legend=alt.Legend(labelColor=C["muted"], title=None)),
                tooltip=["priority", "tickets"]).properties(height=170),
            width="stretch")

        st.markdown("##### Response time by priority vs target")
        resp_rows = []
        for p in ("High", "Medium", "Low"):
            m = rt["by_priority"].get(p)
            if m is not None:
                resp_rows.append({"priority": p, "mean": m, "kind": "actual"})
            resp_rows.append({"priority": p, "mean": sla["targets_minutes"][p], "kind": "target"})
        if resp_rows:
            st.altair_chart(
                alt.Chart(pd.DataFrame(resp_rows)).mark_bar(stroke=None).encode(
                    x=alt.X("priority:N", sort=["High", "Medium", "Low"], title=None,
                            axis=alt.Axis(labelColor=C["muted"])),
                    xOffset=alt.XOffset("kind:N"),
                    y=alt.Y("mean:Q", title="minutes (mean)",
                            axis=alt.Axis(labelColor=C["muted"])),
                    color=alt.Color("kind:N", scale=alt.Scale(domain=["actual", "target"],
                                                              range=[C["blue"], "#3d5a7d"]),
                                    legend=alt.Legend(labelColor=C["muted"], title=None)),
                    tooltip=["priority", "kind", "mean"]).properties(height=170),
                width="stretch")

    st.write("")
    st.markdown("##### Daily volume by category")
    cbd = a["by_category_by_day"]
    if cbd:
        long_df = pd.DataFrame(cbd).melt(id_vars="date", var_name="category", value_name="tickets")
        st.altair_chart(
            alt.Chart(long_df).mark_bar(stroke=None).encode(
                x=alt.X("date:N", title=None, axis=alt.Axis(labelColor=C["muted"], labelAngle=-45)),
                y=alt.Y("tickets:Q", title="tickets", axis=alt.Axis(labelColor=C["muted"])),
                color=alt.Color("category:N",
                                scale=alt.Scale(domain=list(CATEGORY_COLOURS),
                                                range=list(CATEGORY_COLOURS.values())),
                                legend=alt.Legend(labelColor=C["muted"], title=None, orient="top")),
                tooltip=["date", "category", "tickets"]).properties(height=230),
            width="stretch")
    else:
        st.caption("No dated tickets in this window.")

    fc = ins.get("forecast")
    if fc and fc.get("forecast"):
        st.write("")
        st.markdown("##### Next 7 days (planning aid)")
        fcol1, fcol2 = st.columns([2, 3])
        with fcol1:
            mae = fc.get("backtest_mae")
            days = fc.get("history_days", 0)
            if days >= 14 and mae is not None:
                st.markdown(f'<div class="note">About <b>{fc["predicted_total"]}</b> tickets expected '
                            f'over {fc["horizon"]} days. Backtest error <b>{mae}</b> tickets/day on '
                            f'{days} days of history. A planning aid, not a prediction.</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="warn">About <b>{fc["predicted_total"]}</b> tickets expected '
                            f'over {fc["horizon"]} days, but only <b>{days}</b> days of history: '
                            f'no error margin can be quoted. Do not plan staffing on this.</div>',
                            unsafe_allow_html=True)
        with fcol2:
            st.altair_chart(
                alt.Chart(pd.DataFrame(fc["forecast"])).mark_line(
                    point=alt.OverlayMarkDef(color=C["blue"], filled=True, size=45), strokeWidth=2.4,
                    color=C["blue"]).encode(
                    x=alt.X("date:N", title=None, axis=alt.Axis(labelColor=C["muted"], labelAngle=-45)),
                    y=alt.Y("predicted:Q", title="expected tickets",
                            axis=alt.Axis(labelColor=C["muted"])),
                    tooltip=["date", "predicted"]).properties(height=200),
                width="stretch")

    st.write("")
    st.markdown(f'<div class="note"><b>What this view cannot tell you.</b> {ins["limits"]}</div>',
                unsafe_allow_html=True)


# ============================================================== 4. REPORTS
with tabs[3]:
    st.markdown('<div class="eyebrow">Step 4</div>', unsafe_allow_html=True)
    st.title("Weekly reports")
    st.markdown('<div class="sub">One click, one PDF per department, plus CSV and JSON for '
                'anyone who wants to check the numbers.</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 2, 1])
    all_tickets = fetch("/tickets", params={"limit": 1000})
    depts = ["All departments"] + sorted({r["assigned_to"] for r in all_tickets if r.get("assigned_to")})
    with c1:
        rep_dept = st.selectbox("Department", depts, key="rep_dept")
    with c2:
        rep_end = st.date_input("Week ending", value=date.today(), key="rep_end")
    with c3:
        st.write("")
        st.write("")
        make = st.button("Generate", type="primary", width="stretch")

    rparams = {"end": rep_end.isoformat()}
    if rep_dept != "All departments":
        rparams["department"] = rep_dept

    if make:
        try:
            with st.spinner("Building the report…"):
                full = api("GET", "/report", params=rparams)
                pdf_bytes = api_bytes("/report.pdf", params=rparams)
                csv_bytes = api_bytes("/report.csv", params=rparams)
            st.session_state["report"] = full
            st.session_state["pdf_bytes"] = pdf_bytes
            st.session_state["csv_bytes"] = csv_bytes
            st.session_state["pdf_missing"] = pdf_bytes is None
        except ApiError as e:
            show_api_error(e)

    full = st.session_state.get("report")
    if full:
        a = full["analytics"]
        st.write("")
        k1, k2, k3, k4 = st.columns(4)
        with k1: tile("Scope", full["scope"], f"{full['window']['start']} → {full['window']['end']}")
        with k2: tile("Tickets", a["total_tickets"], f"{a['undated_tickets']} undated")
        with k3: tile("Median response", mins(a["response_time"]["median_minutes"]),
                      f"n={a['response_time']['measured_tickets']}")
        with k4: tile("Narrative engine", full["narrative"]["engine"],
                      full["narrative"]["compliance"]["verdict"])

        st.write("")
        d1, d2, d3 = st.columns(3)
        if st.session_state.get("pdf_bytes"):
            d1.download_button("⬇  Download PDF", st.session_state["pdf_bytes"],
                               file_name=f"medops-weekly-{rep_dept.lower().replace(' ', '-')}.pdf",
                               mime="application/pdf", width="stretch", type="primary")
        if st.session_state.get("pdf_missing"):
            st.markdown('<div class="warn">The PDF engine is not available on this host '
                        '(WeasyPrint needs system libraries). The CSV and JSON below carry '
                        'the same numbers, and the <code>/report.pdf</code> endpoint works '
                        'on any host that installs them.</div>', unsafe_allow_html=True)
        if st.session_state.get("csv_bytes"):
            d2.download_button("⬇  Download CSV", st.session_state["csv_bytes"],
                               file_name=f"medops-weekly-{rep_dept.lower().replace(' ', '-')}.csv",
                               mime="text/csv", width="stretch")
        d3.download_button("⬇  Download JSON", json.dumps(full, indent=2, default=str),
                           file_name=f"medops-weekly-{rep_dept.lower().replace(' ', '-')}.json",
                           mime="application/json", width="stretch")

        st.write("")
        st.markdown("##### In this report")
        st.markdown(full["narrative"]["text"])
        st.caption(full["narrative"]["disclosure"])
        st.markdown(f'<div class="note">{full["limits"]}</div>', unsafe_allow_html=True)

        st.write("")
        st.markdown("##### Numbers behind the report")
        t1, t2, t3 = st.columns(3)
        with t1:
            st.caption("Category")
            st.dataframe(pd.DataFrame(
                [{"category": k, "tickets": int(v)} for k, v in a["by_category"].items()],
                columns=["category", "tickets"]), width="stretch", hide_index=True)
        with t2:
            st.caption("Priority and status")
            st.dataframe(pd.DataFrame(
                [{"item": k, "tickets": int(v)} for k, v in
                 list(a["by_priority"].items()) + [(f"status · {k}", v) for k, v in a["by_status"].items()]],
                columns=["item", "tickets"]), width="stretch", hide_index=True)
        with t3:
            st.caption("Team")
            st.dataframe(pd.DataFrame(
                [{"team": k, "tickets": int(v)} for k, v in a["by_department"].items()],
                columns=["team", "tickets"]), width="stretch", hide_index=True)

        st.caption("Response time by priority (minutes)")
        st.dataframe(pd.DataFrame([
            {"priority": p,
             "mean": a["response_time"]["by_priority"][p],
             "target": a["sla"]["targets_minutes"][p],
             "met": a["sla"]["by_priority"][p]}
            for p in ("High", "Medium", "Low")]),
            width="stretch", hide_index=True)
    else:
        st.markdown('<div class="note">Pick a department and week, then <b>Generate</b>. '
                    'The PDF is the deliverable for a department head; the CSV and JSON are '
                    'for anyone checking the numbers.</div>', unsafe_allow_html=True)
