# MedOps AI — user manual

Two ways to use the same system. Both run the same engine, which is why the numbers match.

| What | Where |
|---|---|
| Console (interface) | https://tshepisofrominnostation.github.io/medops-ai/ |
| API (service) | https://medops-api.onrender.com |
| API documentation | https://medops-api.onrender.com/docs |
| Source | https://github.com/tshepisofrominnostation/medops-ai |

---

## 1. Using the console

Open the console link. Nothing to install, no login.

### Choosing who you are

The selector at the bottom of the left rail changes which views you see:

- **Staff** — submit a request, see the one you submitted. No queue.
- **Operations** — triage queue, operations dashboard, workload forecast, weekly report.
- **Governance** — bias audit and decision log, read-only.

> This hides views; it does not enforce access. There is no sign-in, so anyone can switch. Real permissions belong in the API once it has authentication.

### Logging a request (Triage queue)

1. Paste the message the way it arrives, e.g. *"The ventilator in ICU will not start, alarm is going, patients waiting."*
2. Press **Classify and draft reply**.
3. You get the ticket (category, priority, assigned team), a drafted reply, and a **compliance verdict** under the reply.

The verdict is one of:

| Verdict | Meaning |
|---|---|
| **Screen clean** | No known patient-data pattern in the draft. A person still approves the send. |
| **Needs review** | Something matched that a human must look at before sending. |
| **Blocked** | Patient data found in the draft. Do not send. |

### Changing the tone of a reply

Under every drafted reply are three buttons: **Formal**, **Friendly**, **Urgent**.

The tone changes how it sounds, never what it promises. The ticket number, the assigned team and the response window stay identical in all three. That is deliberate: a friendlier message must not quietly become a faster promise.

### Switching to the live API

Bottom of the rail: tick **Live API**.

- The dot shows status: grey means in-browser engine, amber means waking, green means connected, red means unreachable.
- With it on, tickets are sent to the deployed service and the result carries an **API** badge and the round-trip time.
- Free instances sleep when idle. The first call can take 30 to 60 seconds. If it fails, the in-browser engine still works, so you are never stuck.

### Reading the other views

**Operations** — volume by department, category mix, first-response time against target, and the tickets in the window.

**Workload forecast** — projected tickets for the next 7 days, the error margin next to it, and a comparison of three methods. It currently reports that a plain average is as good as the smarter methods. That is the finding, not a bug: the page shows the error so the projection cannot be misread as certainty.

**AI governance** — the bias audit (same need, different wording), the decision log (which signals fired, never the message text), and a plain-language transparency note. Bias is **detected and flagged for a human, not corrected automatically**.

**Weekly report** — counted facts and findings labelled act / watch / unknown.

### Buttons in the ticket log

- **Reset to sample history** — restores the 103 sample tickets.
- **Download CSV** — exports what is stored.
- **Clear my tickets** — removes your local tickets.

Your tickets live in this browser only.

---

## 2. Using the API

### Interactive documentation

Open https://medops-api.onrender.com/docs. Every endpoint can be run from that page. This is the simplest way to demonstrate the API without writing code.

> The service sleeps when idle. If the page is slow, wait a minute and reload.

### From a terminal

```bash
BASE=https://medops-api.onrender.com

curl $BASE/health

curl -X POST $BASE/tickets -H 'Content-Type: application/json' \
  -d '{"message":"Dialysis machine 4 is not working, patients waiting"}'

curl -X POST $BASE/replies -H 'Content-Type: application/json' \
  -d '{"message":"Invoice double-charged by MedSupply","tone":"formal"}'

curl $BASE/analytics
curl $BASE/forecast/compare
curl $BASE/governance/bias-audit
curl -o weekly.pdf $BASE/report/weekly.pdf
```

### Endpoints by purpose

| Purpose | Endpoints |
|---|---|
| Intake | `POST /tickets`, `GET /tickets`, `GET /tickets/{id}` |
| Replies | `POST /replies` (optional `tone`), `POST /check/category` |
| Analytics | `GET /analytics`, `GET /insights` |
| Reporting | `GET /report`, `/report.csv`, `/report.pdf`, `/report/weekly.json`, `/report/weekly.pdf` |
| Forecast | `GET /forecast`, `GET /forecast/compare` |
| Governance | `POST /compliance`, `GET /governance/bias-audit`, `GET /governance/transparency` |
| Lifecycle | `POST /tickets/{id}/status` |
| Health | `GET /health` |

### Connecting from your own system

Allowed browser origin: `https://tshepisofrominnostation.github.io`. Server-to-server calls need no CORS.

Outbound alerts are off by default. To enable:

```
MEDOPS_ALERTS=1
MEDOPS_WEBHOOK_URL=https://hooks.slack.com/services/...
MEDOPS_SMTP_HOST / MEDOPS_SMTP_PORT / MEDOPS_SMTP_USER / MEDOPS_SMTP_PASS / MEDOPS_SMTP_FROM
```

---

## 3. Running it yourself

```bash
git clone https://github.com/tshepisofrominnostation/medops-ai
cd medops-ai
pip install -r requirements.txt
uvicorn app.main:app --reload          # API on http://127.0.0.1:8000
python scripts/build_pages.py --out docs   # console, open docs/index.html
```

Docker:

```bash
docker build -t medops-api .
docker run -p 8000:8000 medops-api
```

Environment the service reads:

| Variable | Purpose | Default |
|---|---|---|
| `PORT` | port uvicorn binds | 8000 |
| `MEDOPS_DB_PATH` | ticket store | `data/tickets_processed.json` |
| `MEDOPS_DECISION_LOG` | append-only decision log | `data/decisions.jsonl` |
| `MEDOPS_ALERTS` | enable assignment alerts | `0` |

Checks:

```bash
python -m pytest -q                      # 231 passed, 1 skipped
node scripts/check_app_parity.mjs        # console vs service
node scripts/check_governance_parity.mjs # 1458 values identical
```

---

## 4. Known limits

State these plainly if anyone asks what it cannot do.

1. **No authentication.** Anyone with the API link can post a ticket.
2. **Patient-data screening is pattern-based.** The risk report records 0 of 6 semantic rephrasings caught. Human review is mandatory, not optional.
3. **Bias is detected, not fixed.** 4 of 6 matched pairs are prioritised differently depending on wording, all against Afrikaans, isiZulu or plain English. Fixing it needs native-language test pairs and multilingual keywords.
4. **The forecast is not better than a plain average** on this history, and the page says so.
5. **Free tier forgets.** Tickets reset on redeploy and the service sleeps after 15 minutes idle.
6. **Role views are a prototype**, not access control.
7. **No load testing.** Single-user throughput is all that is known.
