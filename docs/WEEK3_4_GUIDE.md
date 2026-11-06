# Week 3 and Week 4: build, test, verify, complete

This is the working guide for the last two weeks of the bootcamp project. It assumes
nothing. Every command below was run on this branch and the expected output is quoted.

- **Week 3 goal:** the hospital can *use* the platform day to day and see what happened.
- **Week 4 goal:** the work is tested, documented, honest about its limits, and demo-ready.

---

## 0. What changed, and why

The repository on `main` already carried sprints 1 to 4 in one pass. Two real gaps
remained, both named in `docs/RISK_REPORT.md` by the team itself:

| Gap | Evidence in the repo | What this branch does |
|---|---|---|
| **Response time could not be measured.** Tickets recorded only a creation time, so the Week 3 "analyse response times" task had no data. The dashboard printed a notice saying SLA reporting was pending. | `dashboard.py` section 12; `app/persistence.py` had no lifecycle fields | Adds a ticket lifecycle (`Open → In Progress → Resolved`) with `first_response_at` and `resolved_at`, and derives response time, SLA attainment and status counts from them |
| **The compliance screen caught 0 of 6 semantic PHI phrasings.** | `docs/RISK_REPORT.md` R4 | Adds a semantic PHI detector, saves the six cases as a permanent regression test, and raises the floor to 6/6 |

Plus the NLP and reporting work the brief asks for: a semantic classifier for a
second opinion, a grounded narrative layer, and a one-click week report in PDF, CSV
and JSON per department.

**Nothing from `main` was deleted.** Every new analytics key is additive; the existing
contract keys, tests and modules still work.

---

## 1. Set up (5 minutes)

```bash
git clone https://github.com/tshepisofrominnostation/medops-ai
cd medops-ai
git checkout week2-baseline-rebuild        # this branch
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Check the install is complete:**

```bash
pytest -q
```

Expected: `147 passed`. If you see import errors, you are missing a dependency from
`requirements.txt`; reinstall it.

---

## 2. Get data in (choose one)

**Option A — start clean and type your own.** Nothing to do; the store starts empty.

**Option B — 21 days of realistic history.** Needed for the weekly insight, the charts
and the report to show anything meaningful:

```bash
python scripts/make_demo_data.py --out data/demo_tickets.json --days 21 --end 2026-11-06
```

Expected: `wrote 103 synthetic tickets over 21 days to data/demo_tickets.json`

This runs every message through the **real pipeline**, so the categories, priorities
and routing are the engine's own decisions. Only timestamps and response times are
simulated. Every record is tagged `"synthetic": true` so demo data can never be
mistaken for real hospital data, and it never touches `data/tickets_processed.json`.

To use it, point the API at it (see step 3). To go back to the real store, just drop
the `MEDOPS_DB_PATH` variable.

---

## 3. Start the platform (two terminals)

**Terminal 1 — the API:**

```bash
# with the demo history
MEDOPS_DB_PATH=data/demo_tickets.json uvicorn app.main:app --reload
# or with a clean store
uvicorn app.main:app --reload
```

Windows PowerShell: `$env:MEDOPS_DB_PATH="data/demo_tickets.json"; uvicorn app.main:app --reload`

Check it: open <http://127.0.0.1:8000/health>. You should see:

```json
{"status":"ok","version":"1.2.0","reply_writer":"template","narrative":"deterministic",
 "semantic_classifier":{"loaded":true,"trained_on":289},"statuses":["Open","In Progress","Resolved"]}
```

That one response tells you which capabilities are actually live: the reply writer and
narrative engine fall back to template/deterministic until you set `MEDOPS_LLM_*`.

**Terminal 2 — the console:**

```bash
streamlit run console.py
```

It opens at <http://localhost:8501>. The sidebar shows **API connected** and the same
capability list. If it shows a red box instead, the API is not running.

> `dashboard.py` (the analytics dashboard) still works and is unchanged. `console.py`
> is the working surface for Week 3; keep the dashboard as the read-only view.

---

## 4. Week 3 acceptance walkthrough

Work through this in order. Each step names what you should see, so a marker can
follow along without reading the code.

### 4.1 Submit a request and see the whole loop — *"message in, routed ticket out"*

Go to **➕ New request** and paste, exactly:

```
"The patient monitoring terminal in Bay 3 keeps disconnecting from the local network during telemetry sync." - Dr. S. Khumalo (Emergency Ward)
```

Press **Classify and draft**. Expected:

| Field | Value |
|---|---|
| Ticket | `MED-0NN` (next in sequence) |
| Category | `IT & Medical Tech` |
| Priority | `High` (red) |
| Routed to | `IT & Biomedical Engineering on-call` |
| Drafted reply | ≤ 65 words, one immediate action, an escalation path |
| Safety screen | `CLEAN`, 0 blocking |
| Second opinion | `Agrees` |

That is the graded Week 1 scenario: a telemetry failure in an emergency ward must
route to IT & Medical Tech at High priority. Now try a routine one to see the
contrast:

```
"Medical aid rejected the claim for a surgical admission." - Ms. C. Ndlovu (Billing)
```

Expected: `Finance`, `Low`, `Finance Operations Team`, `warm-administrative` tone.

**Why the second opinion exists.** The rule engine only knows its lexicon. Paste:

```
I am locked out of my account and cannot sign in
```

The rules say `Operations` (no keyword matches), the semantic model says something
else. When the two disagree and the model is confident, the panel says a human
should confirm the category. That is the point: the platform asks for review instead
of guessing silently.

### 4.2 Work the queue — *this is the Week 3 mechanic that makes analytics possible*

Go to **🗂 Work the queue**.

1. Set **Status = Open**. The oldest ticket is at the top.
2. Press **▶ Start** on a ticket.
3. Its status becomes `In Progress` and **First response** starts showing minutes.
4. Press **✓ Resolve**. Status becomes `Resolved`.
5. Press **↺ Reopen** on a resolved ticket to check it can be corrected.

**Verify the response-time clock actually moved:**

```bash
curl -s "http://127.0.0.1:8000/analytics" | python -m json.tool | head -40
```

```json
"response_time": {"measured_tickets": 30, "unmeasured_tickets": 2,
                  "mean_minutes": 53.4, "median_minutes": 21.0, "worst_minutes": 470.2},
"sla": {"attainment": 0.67, "by_priority": {"High": 0.55, "Medium": 0.6, "Low": 0.79},
        "targets_minutes": {"High": 15, "Medium": 120, "Low": 480}},
"by_status": {"Open": 2, "In Progress": 8, "Resolved": 22}
```

Reset the clock cleanly if you want a before/after: note `measured_tickets`, resolve
one ticket, refresh, and confirm it went up by one.

**The proposed targets** (High 15 min, Medium 2 h, Low 8 h) live in one place,
`app/lifecycle.py: SLA_TARGET_MINUTES`. They are the team's proposal, not hospital
policy, and every screen labels them that way. Change them there if your ward agrees
different numbers.

### 4.3 Weekly insight — *"the hospital sees what is happening"*

Go to **📈 Weekly insight**. Set scope and week ending, then read in this order:

1. **KPI row** — tickets, High share, median response, met target, unanswered.
2. **Executive summary** — five or six sentences of prose.
3. **Findings and their evidence** — each finding carries the numbers behind it and a
   confidence badge.
4. **Charts** — category mix, priority mix, actual vs target response time, daily
   volume by category, forecast.

**Test the honesty rules, they are the most important part:**

```bash
# a window with no data must say so, not show zeros as if nothing happened
curl -s "http://127.0.0.1:8000/insights?end=2020-01-01" | python -m json.tool | head -20
```

Expected: a single `empty` finding and the sentence *"No tickets were logged for All
departments between …"*.

With only a few days of history, the `volume_trend` finding reports
`insufficient-data` and says it needs 8+ tickets in each of two weeks. **It refuses to
call a trend from noise.** Do not "fix" that.

### 4.4 Report — *the deliverable a department head holds*

Go to **📄 Reports**, pick a department and week, press **Generate**.

Three download buttons appear: **PDF** (the document), **CSV** (spreadsheet numbers),
**JSON** (everything, for checking). Open the PDF and confirm all six sections:

1. Header band with scope and week
2. Four KPI tiles
3. Executive summary
4. Key findings with evidence and confidence
5. Tables: category, priority/status, response time vs target, teams, 7-day outlook
6. **Responsible AI notice** — engine used, compliance verdict, and the limits

That last box is deliberate. A report that does not state its own limits is not
finished.

**Check the files are real, not empty shells:**

```bash
curl -s -o /tmp/r.pdf "http://127.0.0.1:8000/report.pdf" && file /tmp/r.pdf
# /tmp/r.pdf: PDF document, version 1.4, 3 pages
curl -s "http://127.0.0.1:8000/report.csv" | head -3
# section,metric,value
# meta,scope,All departments
# meta,window_start,2026-10-31
```

---

## 5. Week 4: complete, test, document

### 5.1 Run the whole test suite

```bash
pytest -q                      # 147 passed
python -m tests.evaluate       # 100% on all five metrics (20 cases)
PYTHONPATH=. python scripts/risk_audit.py    # probes our own output
```

| Suite | What it proves |
|---|---|
| `tests/test_engine.py`, `test_reply_writer.py` | classification, priority, replies (pre-existing) |
| `tests/test_api_robustness.py` | bad input returns 400, never 500 |
| `tests/test_lifecycle.py` | response/resolution stamps, reopen, impossible timestamps rejected |
| `tests/test_insights.py` | no trend claim from thin data, undated tickets disclosed, SLA wording |
| `tests/test_phi_semantic.py` | the six R4 phrasings stay caught; benign text stays clean |
| `tests/test_narrative.py` | an LLM that invents a number or leaks a name is rejected |
| `tests/test_semantic.py` | second opinion, measured accuracy floor, never guesses |
| `tests/test_api_week34.py` | queue work, insights, report PDF/CSV/JSON |
| `tests/test_console_ui.py` | every tab renders, buttons work, a dead API explains itself |

The last one is the important one for a demo: it starts a real server and drives the
actual console, so a broken chart fails the build instead of failing on stage.

### 5.2 Verify the guardrails yourself (the responsible-AI section)

```bash
# 1. Semantic PHI: all six must be flagged
python - <<'PY'
from app.compliance import screen
for t in ["Mr Dlamini in bed 12 has been waiting since Monday",
          "Her medical aid, the one ending 8834, will cover it",
          "He is on the ARV regimen we discussed",
          "The patient who attempted suicide last week",
          "The lady from the maternity ward whose husband called yesterday"]:
    print(screen(t)["verdict"], "|", t)
PY

# 2. Benign operational text must stay clean
python - <<'PY'
from app.compliance import screen
print(screen("The biomedical team will inspect the monitor in Bay 3 today.")["verdict"])  # clean
PY

# 3. An LLM narration that invents a figure is rejected
python - <<'PY'
from app.insights import build_insights
from app.nlp.narrative import LLMNarrative, write_narrative
ins = build_insights([{"ticket_id":"MED-1","category":"HR","priority":"Low",
                       "assigned_to":"T","timestamp":"2026-11-06T09:00:00+02:00"}],
                     end="2026-11-06")
class Fake(LLMNarrative):
    configured = True; model = "fake"
    def write(self, _): return "Volume rose 45% and 99 tickets were escalated."
out = write_narrative(ins, Fake())
print(out["engine"], "|", out["fallback_reason"])
# deterministic | llm introduced unsupported figures: 45, 99
PY
```

### 5.3 Optional: turn the LLM paths on

Everything works without a key. To draft replies and narrate with a model:

```bash
export MEDOPS_LLM_BASE_URL="https://api.openai.com/v1"
export MEDOPS_LLM_API_KEY="sk-..."
export MEDOPS_LLM_MODEL="gpt-4o-mini"
uvicorn app.main:app --reload
```

`/health` then reports `"reply_writer":"llm"` and `"narrative":"llm"`. Any timeout, bad
JSON, invented figure, PHI leak or medical-advice violation silently falls back to the
template engine, so drafting never fails and reporting never stalls.
`GET /insights` shows the fallback reason when it happens.

**Before any demo:** leave it **off** unless you have budget and a network you trust.
A recorded fallback is more impressive than a live timeout.

### 5.4 Deploy (Week 4 delivery step)

`render.yaml` is ready. Connect the repository at <https://render.com>, choose the
blueprint, then follow `docs/DEPLOY.md`. Two things to set before a pilot:

1. `MEDOPS_DB_PATH` → `/var/data/tickets.json` **with a persistent disk attached**,
   otherwise history resets on every deploy.
2. Warm the service before a demo (free tier sleeps after 15 minutes, cold start is
   30–60 s).

Then run this against the live URL:

```bash
BASE="https://your-service.onrender.com"
curl -s $BASE/health | python -m json.tool
curl -s -X POST $BASE/tickets -H "Content-Type: application/json" \
     -d '{"message":"\"The aircon in Theatre 2 is not working.\" - Dr. Naidoo (Theatre 2)"}'
curl -s "$BASE/insights" | python -m json.tool | head -30
curl -s -o report.pdf "$BASE/report.pdf" && file report.pdf
```

### 5.5 Week 4 completion checklist

Tick these before you say Week 4 is done.

**Functionality**
- [ ] `pytest -q` → 147 passed
- [ ] `python -m tests.evaluate` → PASS on all five metrics
- [ ] All four console tabs work with no exceptions
- [ ] Status buttons move a ticket and change `measured_tickets`
- [ ] Department report generates with all six sections
- [ ] PDF opens, CSV parses, JSON loads

**Honesty and safety**
- [ ] `/insights?end=2020-01-01` returns an `empty` finding, not zeros
- [ ] A thin week reports `insufficient-data` rather than a trend
- [ ] Undated tickets are disclosed, not silently dropped
- [ ] Response targets are labelled *proposed*, forecasts *a planning aid*
- [ ] The six PHI phrasings are caught; benign text is clean
- [ ] An invented figure in a narration is rejected
- [ ] The report states which engine wrote it and what it cannot claim

**Delivery**
- [ ] `docs/DEPLOY.md` followed end to end on a real URL
- [ ] Persistent disk attached, or "history resets on deploy" stated in the pitch
- [ ] `docs/HANDOVER.md` updated with the current state
- [ ] Demo script rehearsed once, offline key off

---

## 6. Demo script (7 minutes)

1. **The problem (30 s).** A ward sends a message to a shared inbox. Nobody owns it.
2. **Intake (90 s).** Paste the telemetry message. Read the category, priority,
   owner and drafted reply aloud. Point at the second opinion panel.
3. **Work the queue (90 s).** Start it, show the response clock appear, resolve it.
   Say: *"this is the click that makes response time measurable."*
4. **Insight (2 min).** Weekly tab. Read the executive summary. Then read a
   `low-sample` badge out loud and say why it is there.
5. **Report (90 s).** Generate the department PDF. Scroll to the Responsible AI box.
6. **Honesty (60 s).** `/insights?end=2020-01-01`. *"It tells you when it does not
   know. That is the feature."*

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Red box: *Cannot reach the MedOps API* | API not running, or wrong port | Start `uvicorn app.main:app --reload`; set `MEDOPS_API_URL` if not on 8000 |
| Charts show "No dated tickets in this window" | Store is empty or the week has no data | Generate demo data, or change the week ending |
| `measured_tickets` stays 0 | No ticket has been moved out of Open | Use **Work the queue → Start** |
| PDF button returns 503 | WeasyPrint missing system libraries | `pip install -r requirements.txt`; on Linux also `apt install libpango-1.0-0` |
| Playwright/UI test fails with a port error | Port already in use | The fixture picks a free port; re-run, and close other servers |
| `insights` says `insufficient-data` everywhere | Fewer than 8 tickets per week | That is correct behaviour; load more history |

---

## 8. What this branch deliberately does **not** claim

- **Not 100% accurate.** 20 of 20 on a hand-written set by the same author is an upper
  bound, not accuracy (R1). The semantic model's honest number is ~71% by
  cross-validation on 80 synthetic sentences, which is a smoke test.
- **Not clinical.** It routes and drafts operations replies. It does not diagnose.
- **Not a guarantee on patient data.** The PHI detector is heuristic. It is a floor,
  and human review of drafted replies stays required (state this in the pitch).
- **Not a prediction engine.** The forecast is a planning aid with a published backtest
  error, and it says when it has too little history to quote one (R3).
- **Not load tested.** Single-user throughput is all we know.

---

## 9. One app: the console page

The published page is not a report with a form bolted on, and it is not a second
product next to the Streamlit console. It is one app:

* you generate a ticket at the top,
* the ticket is classified by the same engine,
* and the tiles, the mix charts and the ticket table below are recomputed from the
  same store, so the number you just changed is the number you can see.

Live at <https://tshepisofrominnostation.github.io/medops-ai/> (the console and the
dashboard are now one page; see [WEEK3_ANALYTICS.md](WEEK3_ANALYTICS.md)).

### How the two halves stay honest

The page is static, so the deterministic core runs in the browser:

| What | Where | Checked by |
|---|---|---|
| keyword tables, routing table, sender regexes | `app/*.py`, serialised by `scripts/engine_bundle.py` | nothing to drift: read from Python at build time |
| scoring, confidence, priority, routing, summary | `web/engine.js` | `scripts/check_engine_parity.mjs` against the Python engine |
| form, store, dashboard, filters, clear, export | `web/console.js` | `scripts/check_console.mjs` in a headless DOM |
| export file shape | `web/export.js` | `tests/test_export_contract.py` feeds it to `app/importer.py` |

Run all three:

```bash
npm install          # jsdom, dev only
npm run check        # engine parity + console behaviour
python -m pytest     # includes both of the above as tests when node is present
```

### The store, and what "your tickets" means

Tickets you generate live in that browser's `localStorage`. That is the honest
consequence of a static host: no server, no shared state, and nothing sent anywhere.
The page says so, next to the tickets.

The committed store is still the shared record. Two stores exist on purpose:

| File | Role |
|---|---|
| `data/demo_tickets.json` | committed seed; the published page is built from it |
| `data/tickets_processed.json` | this machine's working store for the API and CLI |

`--store` decides where an import lands, and the result always names the file it wrote,
so "which dashboard did my ticket go to" is never a guess.

```bash
# on the page: Export for import  ->  medops-my-tickets.json

# publish them: into the seed the page is built from
python -m app.cli import medops-my-tickets.json --store data/demo_tickets.json --dry-run
python -m app.cli import medops-my-tickets.json --store data/demo_tickets.json
python scripts/build_pages.py && git add docs/console && git commit -m "chore: rebuild"

# or keep working locally, without touching what is published
python -m app.cli import medops-my-tickets.json
```

Either way the ticket lands with status `Open`, no first response, `synthetic: false`,
so it is counted as an open ticket rather than quietly padding the response-time
figures and the importer rejects unknown categories, missing fields and bad timestamps
with a reason. It also skips rows already in the store, so importing the same file
twice is safe.

### What still needs Python

The written executive summary is composed at build time, so it keeps describing the
committed store until you rebuild; the page tells the reader that instead of pretending
otherwise. The semantic layer, the drafted replies and the patient-data screen also run
only in the console (`streamlit run console.py`, no API server needed).

### Publishing

`docs/index.html` is generated: GitHub Pages serves it from `main`/`docs`, so the link
rebuilds whenever `main` moves. Do not hand-edit it.

```bash
python scripts/build_pages.py            # writes docs/index.html + artifacts/
git add docs/console && git commit -m "chore(pages): regenerate console page"
```

The ticket explorer takes deep links, so you can send someone a view rather than
describe it in the dashboard's table and filters.

One caveat for the pitch: the seeded store on that page is synthetic (simulated response
gaps, real classifications). Tickets you generate are your own input, classified by the
real engine.
