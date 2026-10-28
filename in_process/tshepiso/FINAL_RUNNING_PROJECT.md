# Final Running Project — Tshepiso (Sprint 1)

**The full Sprint 1 loop, running in one file:** classify → prioritise → draft the reply,
with the same rules as the FastAPI backend (parity-tested 20/20 on the evaluation set).

## Try it
- **Live UI (no setup):** open `final-running-project.html` — hosted link in the PR
  description and in the pinned team chat. Or open the file in any browser from this folder.
- **Backend (production engine):**
  ```
  pip install -r requirements.txt
  uvicorn app.main:app          # POST /tickets, POST /replies
  python -m pytest tests/       # 25 tests
  python -m tests.evaluate      # 20-case scorecard
  ```
- **Full source zip (pre-merge):**
  https://base44.app/api/apps/6a37c12b561889870147c07a/files/mp/public/6a37c12b561889870147c07a/bf48c80b4_medops-reply-writer-agent.zip

## What's inside (mirrors PR #21)
- Weighted classifier + dynamic priority (staffing-criticality, clinical-context phrases)
- Reply writer: template + LLM engines, tone control, medical-advice guardrail,
  structured output, LLM-timeout fallback
- API hardening: descriptive 400s, clean 500s
- Evaluation: 20 hand-labelled cases — category/priority/tone 100%, safety 100%

## Status
- PR #21 (backend + harness) and PR #22 (in_process) open, all four reviewers assigned.
- This UI is my in-process demo for team review — NOT the official console.
  If approved, the next step is porting these rules into docs/engine.js together.
