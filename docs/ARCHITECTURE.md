# Architecture (S4-3)

One message in, one routed request out, with every step testable on its own.

```
message
  → parser        normalise, strip signatures and quoted history
  → classifier    category (7 hospital areas) + confidence
  → prioritizer   High / Medium / Low from clinical and operational signals
  → assigner      department + duty owner
  → reply_writer  template engine, or LLM when a key is present
  → compliance    identifier and clinical-advice screen  (S3-2)
  → persistence   append-only JSON store                 (duplicate-guarded)
      ├→ analytics    totals, rates, by-day              (S2-1)
      ├→ forecast     moving average + trend, backtested MAE (S3-1)
      ├→ report       per-department weekly PDF          (S2-3)
      └→ notify       assignment alert, dry-run default  (S4-1)
```

## Module map

| Module | Responsibility |
|---|---|
| `app/parser.py` | text normalisation |
| `app/classifier.py` | category + confidence |
| `app/prioritizer.py` | priority rules |
| `app/assigner.py` | routing to department |
| `app/reply_writer.py` | reply drafting with safety guardrails |
| `app/tone_detector.py` | sender register |
| `app/compliance.py` | response screening (regex only; see risk report) |
| `app/persistence.py` | storage and duplicate guard |
| `app/analytics.py` | aggregations |
| `app/forecast.py` | volume forecast + backtest error |
| `app/report.py` | weekly PDF generation |
| `app/notify.py` | assignment alerts (dry-run default) |
| `app/main.py` | FastAPI surface |

## Design decisions worth defending

**Rules before models.** The classifier is deterministic and auditable. In a clinical
setting an unexplainable misroute is worse than a slightly less accurate one. A model
can replace it later behind the same interface.

**The reply writer cannot give medical advice.** Safety flags plus banned phrases run
before any text is returned; the template engine is the default and the LLM path is
opt-in.

**Every claim carries its measurement.** The forecast publishes backtest MAE. The
evaluation set publishes its 20/20. The compliance screen publishes its misses. Where
a number is unknown, the document says so.

**Notifications never block triage.** `notify.py` is dry-run by default and swallows
transport errors: a dead webhook must not cost a patient a routed ticket.

## Test surface

67 tests: engine, reply writer, API robustness, analytics, the S2-4 synthetic-history
gate, forecast, compliance, report and notify. Run `pytest -q`.
