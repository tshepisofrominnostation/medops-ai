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
