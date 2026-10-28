# MedOps AI — Smart Ticket Classification Engine

**Live demo:** https://tshepisofrominnostation.github.io/medops-ai/ (browser console running the same rules; the FastAPI backend below is the production engine)

Intelligent hospital operations platform (Sprint 1, Week 1): a FastAPI backend that ingests raw operational requests from hospital staff, classifies them into the correct department, assigns dynamic priority, and returns a strict structured JSON ticket that is persisted to a local database.

## Architecture

```
Hospital staff (message + sender)
        |
        v
   POST /tickets (FastAPI)          python -m app.cli "..."
        |                                   |
        +----------------+------------------+
                         v
                 app/parser.py        parse sender (name + department), de-quote, extract location
                         v
                 app/classifier.py   weighted keyword scoring -> one of 4 categories + confidence
                         v
                 app/prioritizer.py   clinical/safety/urgency scoring -> High | Medium | Low
                         v
                 app/summarizer.py    one-sentence summary (deterministic template)
                 app/assigner.py      routing table -> owning team/role
                         v
                 app/persistence.py   append to data/tickets_processed.json (MED-### sequence)
                         v
                 strict JSON output (7 keys)
```

Modular by design: every stage is an independent module with a single responsibility, so the rule-based classifier can be swapped for an LLM engine without touching the pipeline, API, or persistence layers.

## Classification logic

**Categories (exactly one per ticket):** IT & Medical Tech, HR, Finance, Operations.

Each category holds a weighted keyword lexicon. The score is the sum of matched keyword weights (repeat mentions count), and the winner takes the ticket. Zero matches route to Operations (operations catch-all, confidence 0.0). Clinical equipment (ventilators, telemetry, patient monitors, ECG, dialysis) scores into IT & Medical Tech because in a hospital, clinical equipment faults are engineering faults.

**Dynamic priority:** additive scoring over the message plus sender context:
- Clinical context (Emergency, ICU, Theatre, telemetry, patient monitoring): +3
- Clinical equipment named: +3
- Safety hazard (fire, flood, gas leak, outage): +4
- Urgency language (down, not working, alarm, keeps disconnecting): +2
- Routine admin language (invoice, query, leave request, routine): -2
- High: score >= 5, Medium: 2-4, Low: < 2

So a patient-monitoring terminal dropping off the network in the Emergency Ward routes to IT & Medical Tech with High priority and the biomedical on-call team, while a medical-aid invoice query routes to Finance with Low priority — automatically.

## Output contract

```json
{
  "ticket_id": "MED-001",
  "timestamp": "2026-10-22T14:46:59+02:00",
  "sender": "Dr. S. Khumalo (Emergency Ward)",
  "category": "IT & Medical Tech",
  "priority": "High",
  "summary": "The patient monitoring terminal in Bay 3 keeps disconnecting ... classified as IT & Medical Tech with High priority.",
  "assigned_to": "IT & Biomedical Engineering on-call"
}
```

Every processed ticket is appended to `data/tickets_processed.json`.

## Setup

```bash
git clone https://github.com/tshepisofrominnostation/medops-ai
cd medops-ai
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# API server
uvicorn app.main:app --reload
# then: POST http://localhost:8000/tickets {"message": "..."}

# or one-shot CLI, no server
python -m app.cli '"The aircon in Theatre 2 is not working." - Dr. Naidoo (Theatre 2)'

# tests (includes the graded emergency scenario)
pytest tests/ -q
```

## Live demo and parity

`docs/` holds a static console (GitHub Pages) with `engine.js`, a JavaScript port of the Python engine. The two were parity-tested on 12 scenarios across all four departments: identical category, priority, assignee and sender parsing on every case.

## Test coverage

Eight tests including the exact Week 1 validation scenario (Dr. S. Khumalo's telemetry failure must route to IT & Medical Tech at High priority), schema strictness (exactly the seven required keys), the four category routes, priority bands, and persistence/sequencing.

## Sprint 1 scope note

Rule-based classification is deliberate: deterministic, testable, no API cost, and no patient-identifying text leaves the hospital network. The `classify()` interface already returns confidence, matching the planned LLM-assisted engine for Sprint 2.

## Team
Tshepiso Freddy Thosago (Scrum Master / Developer), Xoliswa-Dee, Anastacia202, Avuyile-Plaatjie. Sprint plan and board: SPRINT_PLAN.md and the Issues/Milestones tabs.

Author: Tshepiso Freddy Thosago · CAPACITI / Clickatell AI Bootcamp

## Reply Writer (feature/reply-writer-agent)

Each classified ticket gets a drafted department reply through `app/reply_writer.py`:

- **TemplateReplyEngine** - deterministic, offline drafting with tone control:
  High priority -> `concise-professional` (<= 65 words, one immediate action, an
  escalation path); Medium/Low -> `warm-administrative` (acknowledge, inform,
  reassure, a one-or-two-working-day timeframe).
- **LLMReplyEngine** (optional) - OpenAI-compatible provider with JSON-mode
  structured output. Configure via `MEDOPS_LLM_BASE_URL`, `MEDOPS_LLM_API_KEY`,
  `MEDOPS_LLM_MODEL`, `MEDOPS_LLM_TIMEOUT`. On timeout, HTTP error, malformed
  JSON, tone-contract violation or any safety breach it returns None and the
  facade falls back to the template engine - drafting never fails.
- **Medical-advice guardrail** - no reply may contain diagnosis, medication,
  dosage or treatment language (`MEDICAL_ADVICE_BAN`). LLM output is scanned
  before acceptance; violations are rejected and routed to the fallback.
- Structured output via the `DraftedReply` Pydantic model (ticket_id, tone,
  reply_body, safety_flags, generated_by, model).

`POST /replies` runs the full loop: classify the request, draft the reply.

## Evaluation harness

`tests/data/evaluation_set.json` holds 20 realistic hospital requests with
hand-written ground truth (category, priority, tone, required phrases, banned
phrases, model answer). Measure the engine:

    python -m tests.evaluate

Targets: category >= 95%, priority >= 90%, tone 100%, phrase coverage >= 90%,
safety 100%. Current run: 100% on every metric (2026-10-28).

## API robustness

Bad input returns descriptive `400 Bad Request` responses, never a 500:
empty or whitespace messages, too-short text, oversized text (> 2000 chars),
control characters, malformed JSON bodies and missing fields all get clear
error details (`app/main.py`). Unexpected failures fall back to a clean
JSON 500. Tests: `tests/test_api_robustness.py`.
