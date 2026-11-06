# Week 3 — Data tracking & analytics

Sprint 2 deliverable for the MedOps AI project. This is the module that answers "what
happened this week, and how would we know?" — it stores every ticket with its timestamps,
derives operational metrics from that store, shows them on a dashboard, and writes a weekly
summary from the same numbers.

Everything here is in the app the project already had:
**https://tshepisofrominnostation.github.io/medops-ai/**

One page, three tabs: **Log a request** → **Dashboard** → **Weekly summary**. There is no
second application to open and nothing to install to read it.

---

## 1. Data storage structure

### The record

One JSON object per ticket, append-only. The same shape is written by the browser, by the
Python API (`app/pipeline.py` → `app/persistence.py`), and read back by the report
generator, so a ticket does not change shape when it crosses a language boundary.

| field | type | written by | meaning |
| --- | --- | --- | --- |
| `ticket_id` | string `MED-###` | creation | monotonic id; the sequence survives restarts |
| `timestamp` | ISO-8601 with offset | creation | when the request arrived. Every duration is measured from here |
| `sender` | string | parser | who asked, as written ("Dr. A. Pillay (Cardiology)") |
| `ward` | string | parser | department the sender named, when they named one |
| `category` | enum | classifier | `IT & Medical Tech` \| `HR` \| `Finance` \| `Operations` |
| `priority` | enum | prioritizer | `High` \| `Medium` \| `Low` |
| `summary` | string | summarizer | one-line description, **patient identifiers redacted** |
| `assigned_to` | string | router | the queue that owns the work |
| `status` | enum | lifecycle | `Open` \| `In Progress` \| `Resolved` |
| `first_response_at` | ISO-8601 \| absent | lifecycle | stamped when a reply is drafted or a human responds |
| `resolved_at` | ISO-8601 \| absent | lifecycle | stamped on resolve; cleared on reopen |
| `ai_response` | object | reply writer | the log of what the assistant said, and what made it |
| `signals` | object | classifier | the evidence behind the classification (see below) |

`ai_response` is the "AI response log" the brief asks for:

```json
"ai_response": {
  "draft": "Thank you for logging this. IT & Biomedical Engineering on-call has been activated for MED-104 at ICU...",
  "tone": "urgent",
  "tone_evidence": ["urgent", "unacceptable"],
  "engine": "semantic-tfidf → signals → template",
  "generated_at": "2026-11-06T11:33:12.418Z"
}
```

`signals` makes the classification auditable rather than oracular:

```json
"signals": {
  "category_confidence": 0.4471,
  "category_margin": 0.2691,
  "unsure": false,
  "runner_up": { "category": "Operations", "similarity": 0.178 },
  "priority_score": 11,
  "priority_signals": [
    { "signal": "clinical setting named", "weight": 3, "terms": ["icu"] },
    { "signal": "patient-care equipment named", "weight": 3, "terms": ["ventilator"] }
  ],
  "phi_blocked": false,
  "phi_flags": [],
  "matched": [{ "text": "ventilator not starting in icu", "category": "IT & Medical Tech", "similarity": 0.71 }]
}
```

### Where it is stored

| store | file / key | role |
| --- | --- | --- |
| committed history | `data/demo_tickets.json` | 103 tickets, the sample the public page is built from |
| browser store | `localStorage["medops.week3.store.v1"]` | this visitor's copy; the page seeds it from the committed history on first load |
| service store | `data/tickets_processed.json` (or `MEDOPS_DB_PATH`) | what the Python API appends to when running for real |

A static host cannot write to disk, so the page keeps its store in the browser and says so
in the ticket log. To move your tickets into the committed history:

```bash
python -m app.cli import medops-tickets.json --store data/demo_tickets.json
python scripts/build_pages.py
```

The importer validates each row, rejects bad ones with a reason, and skips duplicates by
fingerprint — it is not a blind merge (`app/importer.py`, `tests/test_importer.py`).

### Why those fields

Timestamps are the whole point: without `first_response_at` a ticket has no response time,
and the analytics can say nothing about service. The lifecycle rules live in one place
(`app/lifecycle.py`) and are mirrored in `web/analytics.js`:

- `Open → In Progress` stamps `first_response_at` once and never overwrites it.
- `Resolved` stamps `resolved_at` (and `first_response_at` if it was never set).
- Reopening clears `resolved_at`.
- A lifecycle stamp earlier than `timestamp` is refused rather than stored, because a
  negative duration would silently drag an average below zero.

---

## 2. Trend analysis logic

The functions are in `web/analytics.js` (the page) and `app/analytics.py` (the service).
They are two implementations of one contract: **the browser is compared against Python on
the same records and must produce identical output** (`scripts/check_app_parity.mjs`,
`tests/test_app_parity.py`), so the number on the page is the number in the PDF.

| function | returns |
| --- | --- |
| `buildAnalytics(records, start, end)` | totals, `by_category`, `by_priority`, `by_department`, `by_day`, `by_status`, rates, response-time block, SLA block |
| `weekWindow(records, end, days=7)` | the 7-day window ending on the latest dated ticket |
| `shiftWindow(win, days)` | the window before it, for week-on-week comparison |
| `responseMinutes(rec)` / `resolutionMinutes(rec)` | minutes from creation to first response / resolution, or `null` |
| `slaMet(rec)` | whether first response beat the priority target; `null` while unmeasured |
| `statusOf(rec)` | `Open` / `In Progress` / `Resolved`, tolerating records with no status field |
| `median(values)`, `mean(values)` | central tendency, refusing empty sets instead of returning 0 |

The insights the brief names, and where they come from:

- **Total volume per department** — `by_department`, grouped on `assigned_to` (the queue that
  owns the work) rather than the ward that asked for it, because the queue is what has
  capacity. Named departments include on-call escalation routes, so "IT & Biomedical
  Engineering on-call" and "IT Service Desk" appear separately.
- **Categorisation breakdown** — `by_category` and `by_category_by_day`, from the classifier's
  labels, with the mix change week-on-week.
- **Average response times** — `response_time.mean_minutes`, `median_minutes`,
  `worst_minutes`, split by priority and by category. Median sits next to mean because one
  ticket answered after a weekend skews a mean badly.
- **Target attainment** — `sla.attainment` and per priority, against stated targets
  (High 15 min, Medium 120, Low 480). These are proposed internal targets, and the page
  labels them as such.

Refusals are deliberate: an empty window returns `null` rather than `0`, an unmeasured
ticket is counted in `unmeasured_tickets` rather than as a zero-minute response, and a
window under eight tickets is flagged as too thin for a trend claim.

---

## 3. Visual dashboard

Tab 2 of the page. It recomputes on every change; nothing is a screenshot.

| component | what it answers |
| --- | --- |
| Four KPI tiles | tickets in window (with week-on-week delta), median first response, share on target, open now |
| Volume by department | where the work lands, as ranked bars with counts |
| Category mix | what the requests were about, by classifier label |
| First response against target | median minutes per priority against the target, coloured by whether the median clears it |
| Tickets in this window | the rows behind the numbers: id, date, category, priority, queue, status, response minutes |

Windows: this week / last 30 days / all time. Charts are inline SVG-free CSS bars, no chart
library, so the page is one file with no external requests and works offline
(`tests/test_page_app.py::test_page_is_self_contained`).

---

## 4. Summary generator

Tab 3. `weeklySummary(rows, window)` in `web/app.js` produces:

- a **headline** sentence with the period, volume, target attainment and open count;
- **findings**, each with a title, a sentence of explanation, and the evidence object it
  rests on (`thin data` badge when the sample cannot support the claim);
- a **window** and the window it is compared against;
- **Copy summary** and **Download JSON** for pasting into a stand-up or attaching to a report.

The findings are computed by counting, not generated by a language model — so a number
cannot be invented, and every claim can be checked against `evidence`. The set covers
volume movement, busiest department, largest category shift, response against target, and
the open backlog with its oldest item.

This is the deliberate opposite of the earlier `app/nlp/narrative.py` rule: a model may
reword these findings, never add one. On the static page there is no model in the loop at
all, which is the honest option when the page must work offline.

---

## 5. How it integrates

```
staff message
   │
   ├─ web/semantic.js      tokenise → project → cosine against Python's centroids
   │                       (+ nearest stored examples, tone, patient-data screen)
   ├─ web/app.js           priority signals → queue → lifecycle → drafted reply → record
   ├─ web/analytics.js     the record → counts, rates, response times, targets
   └─ web/ui.js            the record → ticket card, dashboard, weekly summary
```

Build and verify:

```bash
python scripts/build_app_bundle.py    # export idf + centroids + PHI rules from app/
python scripts/make_app_fixtures.py   # write what Python predicts, for comparison
python scripts/build_pages.py         # assemble docs/index.html
npm run check                         # parity (vs Python) + page journey (headless DOM)
python -m pytest tests -q             # the full suite, 161 tests
```

The classifier is not re-implemented by eye. `scripts/build_app_bundle.py` exports the IDF
weights and per-category centroids from the real model (`app/nlp/semantic.py`), and the PHI
rules as data, so the browser does only the arithmetic Python does at request time.
`scripts/check_app_parity.mjs` then replays 24 messages — including a typo, a non-English
message, a message with no usable vocabulary, and three carrying patient data — plus five
analytics windows, and fails on any disagreement in category, similarity, margin,
confidence, scores, PHI flags, or any count, share and time in the analytics.

Agreement has one documented exception: averaged minute values may differ by 0.01 where the
true mean lands on a rounding boundary, because the two languages accumulate floats in a
different order. Counts, shares and classifications must match exactly.

---

## What this module does not do

- It does not persist to a server. A browser store is per visitor; publishing tickets means
  exporting and importing them into the committed history (step 1).
- It does not call an LLM. The semantic layer is local TF-IDF; the drafted replies are
  templates chosen by category, priority and tone. The Python service has the optional LLM
  layer (`app/nlp/narrative.py`) for rephrasing, and the guardrail there is that it may only
  reword computed findings.
- It does not measure human response times unless someone marks a ticket. Response time is
  defined as creation → first response stamp, so an untouched ticket is reported as
  unmeasured, not as fast.
