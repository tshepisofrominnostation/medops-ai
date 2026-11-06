# Handover (S4-5)

Written because the supervisor moves on. Everything here is verified, not intended.

## Live now

- **Console:** https://tshepisofrominnostation.github.io/medops-console/
- **Source:** `churnsignal`-style static site, built from this repo by `make_site_data.py`
- **Business case:** 11 slides, PDF on the console and source in the public repo

## Run it locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --port 8000       # API
pytest -q                              # 67 tests
streamlit run dashboard.py             # Avuyile's dashboard
python -m app.report --out reports/    # weekly PDFs
```

## State of each sprint

| Sprint | Item | State |
|---|---|---|
| 1 | engine, replies, eval set, API hardening | done |
| 2 | analytics service, dashboard, weekly PDF, test gate, review | done |
| 3 | forecast, compliance screen, risk report, review | done |
| 4 | alerts, deploy config, docs, business case, handover | done except the Render account |

## The four open risks (from docs/RISK_REPORT.md)

1. **Compliance catches 0 of 6 semantic PHI phrasings.** Highest priority. A human
   must review every reply until this is fixed.
2. **The evaluation set is not independent.** Same author wrote the engine and the
   cases, so 20/20 is an upper bound.
3. **Undated tickets count in totals but vanish from the daily series.**
4. **The forecast is no better than a naive average on noisy volume.**

## What a successor should do first

1. Deploy the API on Render using `render.yaml`, then run `docs/DEPLOY.md` end to end.
2. Get 200-500 real, human-labelled messages and re-run `tests/evaluate.py`.
3. Replace the compliance regexes with an NER pass, then re-run the six-phrase probe.
4. Attach a Render disk before any pilot, or history resets on redeploy.
