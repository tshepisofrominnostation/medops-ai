# Deployment and smoke test (S4-2)

## What is already live

The public console: **https://tshepisofrominnostation.github.io/medops-console/**

It is a static site carrying real output from this pipeline (analytics, forecast,
department PDFs). It is not the API: there is no server, so it cannot classify a new
ticket. Classification runs in the private repo or on a deployed API.

## Deploying the API

`render.yaml` at the repo root is a Render Blueprint. Connecting the repo to Render
creates `medops-api` automatically.

**Not done yet, and why:** this needs the team's own Render account. No account
credentials are in this repository, and the SM did not create one. Everything else is
ready, so the deploy is a ten-minute job for whoever holds the account.

Manual alternative (no Blueprint):

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Smoke test checklist

Run in order against the deployed base URL. Each line is pass/fail.

| # | Call | Expect |
|---|------|--------|
| 1 | `GET /health` | `200`, status ok |
| 2 | `GET /analytics` | `200`, keys `total_tickets`, `by_day`, `rates` |
| 3 | `POST /tickets` `{"message":"The theatre aircon has failed and the room is unusable"}` | `200`, `category`, `priority`, `assigned_to` returned |
| 4 | same request twice | `GET /tickets` shows **one** new record (duplicate guard holds) |
| 5 | `POST /replies` with a clinical question | `200`, `reply.reply_body` ≥ 20 chars, `compliance.verdict` present |
| 6 | `GET /forecast?horizon=7` | `200`, 7 points, `backtest_mae` numeric |
| 7 | `POST /compliance` with `"ID 9001015800083"` | `verdict` is not `pass` |
| 8 | `POST /tickets` with a 2-character message | `400` validation error |
| 9 | Cold start after 15 min idle | first call succeeds within 90 s |

Two known gaps to record on the checklist, not to hide:

- **Persistence resets on free tier.** `MEDOPS_DB_PATH` must point at a mounted disk
  or every redeploy wipes the history.
- **Compliance is regex-only.** It caught 0 of 6 semantically identifying phrasings in
  the risk report. A human reviewer is mandatory before any reply leaves the building.

## Option A — Streamlit Community Cloud (the UI link, no card, ~3 minutes)

The console runs in **single-service mode**: with `MEDOPS_API_URL` unset it calls
`app.main:app` in-process, so the UI needs no separate API host. That is the cheapest
way to give the team a working link.

1. <https://share.streamlit.io> -> **Create app** -> **Deploy a public app from GitHub**
2. Repository `tshepisofrominnostation/medops-ai`, branch `main`, main file `console.py`
3. Optional: in **Advanced settings -> Secrets**, add
   ```toml
   MEDOPS_DB_PATH = "data/tickets_processed.json"
   ```
   Leave it out and the app starts empty and offers a **Load demo history** button
   instead, which is the safer default for a public link.
4. **Deploy**. First build takes 3 to 6 minutes (pandas, streamlit, weasyprint).

### What single-service mode does and does not give you

| | |
|---|---|
| Works | every Week 3 task: intake, queue, insights, CSV/JSON reports |
| Works | the full 150-test engine on every request, real classification and real drafting |
| Does **not** persist | the store is the container's filesystem. Tickets added today are gone after a restart or a sleep |
| Does **not** produce PDF | WeasyPrint needs system libraries Streamlit Cloud does not ship. The UI detects this and says so; CSV and JSON carry the same numbers |
| Does **not** survive load | one visitor at a time is all it is sized for |

The Kaggle-style honesty line for the pitch: *"the link is a live demonstration of the
engine, not the production deployment; production runs the API with a persistent disk."*

## Option B — Render (API + persistent store)

Use this when the store must survive restarts.

---

## Deploying the API as a container (added 13 Nov, #17)

`render.yaml` targets one vendor. The `Dockerfile` does not: it runs anywhere a
container runs. What is still missing is an account with billing details, which is an
owner decision, not an engineering one.

**Run it locally in one line** (verified: builds nothing, runs the real service):

```bash
docker build -t medops-api .
docker run -p 8000:8000 medops-api
curl -s localhost:8000/health
```

Environment it honours:

| Variable | Purpose | Default |
|---|---|---|
| `PORT` | port uvicorn binds | 8000 |
| `MEDOPS_DB_PATH` | ticket store | in-image data dir |
| `MEDOPS_DECISION_LOG` | append-only decision log | `data/decisions.jsonl` |
| `MEDOPS_ALERTS`, `MEDOPS_WEBHOOK_URL`, `MEDOPS_SMTP_*` | assignment alerts | off, dry-run |

**Publishing the image without a new account.** `docs/ci/api-image.yml` is a GitHub
Actions workflow that builds the image, starts the container, calls `/health`,
`/tickets`, `/replies` (with a tone), `/forecast/compare`, `/governance/bias-audit`
and `/report.csv`, then publishes to `ghcr.io/tshepisofrominnostation/medops-ai/api`.

It is **not installed at `.github/workflows/api-image.yml`** because the token available
to this work does not carry the `workflow` scope, and GitHub rightly refuses to let a
token without it create workflow files. To install it, either:

- **Web UI (no token change):** GitHub → Add file → Create new file → name it
  `.github/workflows/api-image.yml` → paste the contents of `docs/ci/api-image.yml` →
  commit. It runs on the next push to `main`.
- **Token change:** issue a PAT with `workflow` scope, then
  `git mv docs/ci/api-image.yml .github/workflows/api-image.yml`.

After that the image is public at:

```bash
docker run -p 8000:8000 ghcr.io/tshepisofrominnostation/medops-ai/api:latest
```

**Still needed for a public URL** (pick one, all need an account):

| Host | Free tier fits? | What it needs from the owner |
|---|---|---|
| Render | yes, sleeps when idle | account; the existing `render.yaml` works |
| Koyeb / Fly.io | small free allowance | account, card on some plans |
| Hugging Face Spaces (Docker) | yes, public | account; paste the Dockerfile |
| Any VPS | no free tier | server + card |

Until one of these exists, `https://tshepisofrominnostation.github.io/medops-ai/` runs the
same engine in the browser, which is why the console is complete without the API.
