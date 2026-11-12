"""FastAPI service - hardened intake, descriptive errors, reply drafting with fallback."""
import re
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .analytics import current_analytics
from .compliance import screen as screen_text
from .forecast import forecast_from_analytics
from .insights import build_insights
from .lifecycle import LifecycleError, STATUSES, update_ticket
from .nlp.semantic import cross_check
from .notify import notify_assignment
from .report import write_full_report, report_to_csv
from .models import TicketIn, TicketOut
from .pipeline import process_ticket
from .persistence import load_all
from .weekly_report import build_weekly_summary
from .reply_writer import ReplyWriter

MAX_MESSAGE = 2000
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

app = FastAPI(
    title="MedOps AI",
    description="Smart Ticket Classification Engine + Reply Writer for hospital operations.",
    version="1.2.0",
)
writer = ReplyWriter()


def validate_message(message) -> str | None:
    """Return a descriptive error, or None when the message is acceptable."""
    if not isinstance(message, str):
        return "message must be a string"
    if not message.strip():
        return "message must not be empty or whitespace"
    if len(message.strip()) < 5:
        return "message is too short to classify (minimum 5 characters)"
    if len(message) > MAX_MESSAGE:
        return f"message exceeds the {MAX_MESSAGE}-character limit"
    if CONTROL_CHARS.search(message):
        return "message contains control characters"
    return None


@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, exc: RequestValidationError):
    """Replace FastAPI's default 422 crash-report with a descriptive 400."""
    return JSONResponse(
        status_code=400,
        content={"error": "Bad Request", "detail": "Invalid request body.",
                 "fields": [
                     {"field": ".".join(str(p) for p in e["loc"][1:]) or "body",
                      "problem": e["msg"]}
                     for e in exc.errors()[:3]
                 ]},
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    """Any unforeseen failure returns a clean 500 - never a raw traceback."""
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error",
                 "detail": "The service could not process this request. "
                           "The ticket was not saved. Please retry."},
    )


@app.get("/health")
def health():
    """Liveness plus the capabilities actually available in this deployment."""
    from .nlp.semantic import get_model
    return {
        "status": "ok",
        "service": "MedOps AI classification engine",
        "version": app.version,
        "reply_writer": "llm" if writer.llm.configured else "template",
        "narrative": "llm" if writer.llm.configured else "deterministic",
        "semantic_classifier": {"loaded": bool(get_model().centroids),
                                "trained_on": get_model().trained_on},
        "statuses": list(STATUSES),
    }


@app.post("/tickets", response_model=TicketOut)
def create_ticket(payload: TicketIn):
    error = validate_message(payload.message)
    if error:
        raise HTTPException(status_code=400, detail=error)
    ticket = process_ticket(payload.message, payload.sender)
    notify_assignment(ticket.model_dump())
    return ticket


@app.post("/replies")
def draft_reply(payload: TicketIn):
    """Full loop: classify the request, then draft the department reply."""
    error = validate_message(payload.message)
    if error:
        raise HTTPException(status_code=400, detail=error)
    ticket = process_ticket(payload.message, payload.sender)
    try:
        reply = writer.draft(ticket)
    except ValidationError:
        raise HTTPException(status_code=503, detail="Reply drafting temporarily unavailable")
    # S3-2: screen the drafted reply before it can ever be sent
    body = getattr(reply, "reply_body", "") or ""
    return {"ticket": ticket, "reply": reply, "compliance": screen_text(body)}


@app.get("/analytics")
def analytics(start: Optional[str] = None, end: Optional[str] = None):
    """Ticket analytics for the dashboard (S2-2) and PDF report (S2-3).

    Optional inclusive ISO-date window: /analytics?start=2026-11-01&end=2026-11-06
    """
    return current_analytics(start=start, end=end)


@app.get("/forecast")
def forecast(horizon: int = 7):
    """S3-1: ticket surge forecast with a backtested MAE, not a bare number."""
    return forecast_from_analytics(current_analytics(), horizon=horizon)


@app.post("/compliance")
def compliance(payload: dict):
    """S3-2: screen any text for identifiers, clinical advice and promises."""
    text = (payload or {}).get("text", "")
    return screen_text(text)


# ---------------------------------------------------------------------------
# Week 3: working the queue
# ---------------------------------------------------------------------------

@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    """One ticket, with its lifecycle derived from the recorded timestamps."""
    from .lifecycle import response_minutes, resolution_minutes, status_of
    for rec in load_all():
        if rec.get("ticket_id") == ticket_id:
            return {**rec,
                    "status": status_of(rec),
                    "response_minutes": response_minutes(rec),
                    "resolution_minutes": resolution_minutes(rec)}
    raise HTTPException(status_code=404, detail=f"unknown ticket {ticket_id}")


@app.post("/tickets/{ticket_id}/status")
def set_status(ticket_id: str, payload: dict):
    """Move a ticket through its lifecycle. This is what makes response time measurable.

    Body: {"status": "In Progress" | "Resolved" | "Open", "at": "optional ISO-8601"}
    """
    payload = payload or {}
    status = payload.get("status")
    if not status:
        raise HTTPException(status_code=400,
                            detail=f"status is required; one of: {', '.join(STATUSES)}")
    try:
        updated = update_ticket(ticket_id, status, payload.get("at"))
    except LifecycleError as e:
        detail = str(e)
        raise HTTPException(status_code=404 if detail.startswith("unknown ticket") else 400,
                            detail=detail)
    from .lifecycle import response_minutes, resolution_minutes, status_of, sla_met
    return {**updated, "status": status_of(updated),
            "response_minutes": response_minutes(updated),
            "resolution_minutes": resolution_minutes(updated),
            "sla_met": sla_met(updated)}


@app.get("/tickets")
def list_tickets(status: Optional[str] = None, category: Optional[str] = None,
                 priority: Optional[str] = None, limit: int = 200):
    """The queue, newest first, filterable. `status` accepts Open/In Progress/Resolved."""
    from .lifecycle import response_minutes, status_of
    rows = load_all()
    if status:
        rows = [r for r in rows if status_of(r).lower() == status.lower()]
    if category:
        rows = [r for r in rows if r.get("category", "").lower() == category.lower()]
    if priority:
        rows = [r for r in rows if r.get("priority", "").lower() == priority.lower()]
    rows = sorted(rows, key=lambda r: r.get("timestamp", ""), reverse=True)[:max(1, min(limit, 1000))]
    return [{**r, "status": status_of(r), "response_minutes": response_minutes(r)} for r in rows]


@app.get("/insights")
def insights(department: Optional[str] = None, end: Optional[str] = None):
    """Week 3 deliverable: findings for one week, with the narrative written over them."""
    from .nlp.narrative import write_narrative
    ins = build_insights(load_all(), department=department, end=end)
    return {**ins, "narrative": write_narrative(ins)}


@app.post("/check/category")
def check_category(payload: dict):
    """The semantic second opinion for one message, as used on every ticket."""
    message = (payload or {}).get("message", "")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message is required")
    from .classifier import classify
    return cross_check(message, classify(message)[0])


# ---------------------------------------------------------------------------
# Week 4: reporting
# ---------------------------------------------------------------------------

def _report_scope(department: Optional[str], end: Optional[str]) -> dict:
    import tempfile
    out = tempfile.mkdtemp(prefix="medops-report-")
    return write_full_report(load_all(), out, department, end)


@app.get("/report")
def report_json(department: Optional[str] = None, end: Optional[str] = None):
    """Week 4: the full report as data (scope, findings, narrative, forecast, ethics)."""
    import json as _json
    from pathlib import Path
    info = _report_scope(department, end)
    return _json.loads(Path(info["json"]).read_text(encoding="utf-8"))


@app.get("/report.csv")
def report_csv(department: Optional[str] = None, end: Optional[str] = None):
    """Week 4: spreadsheet export of the same numbers."""
    from fastapi.responses import PlainTextResponse
    import json as _json
    from pathlib import Path
    info = _report_scope(department, end)
    data = _json.loads(Path(info["json"]).read_text(encoding="utf-8"))
    name = f"medops-weekly-{(department or 'all').lower().replace(' ', '-')}.csv"
    return PlainTextResponse(report_to_csv(data), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _validated_window(start: Optional[str], end: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Dates arrive from a URL: reject anything that is not exactly YYYY-MM-DD."""
    from datetime import date as _date
    for label, value in (("start", start), ("end", end)):
        if value is None:
            continue
        try:
            if _date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid {label} date. Use YYYY-MM-DD.")
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date.")
    return start, end


@app.get("/report/weekly.json")
def weekly_report_json(start: Optional[str] = None, end: Optional[str] = None):
    """S2-3: the weekly operations summary as data (SLA, departments, category mix)."""
    start, end = _validated_window(start, end)
    summary = build_weekly_summary(load_all(), start=start, end=end)
    return {
        "period": summary["period"],
        "generated_at": summary["generated_at"],
        "analytics": summary["analytics"],
        "departments": summary["departments"],
        "sla": summary["sla"],
    }


@app.get("/report/weekly.pdf")
def weekly_report_pdf(start: Optional[str] = None, end: Optional[str] = None):
    """S2-3: one-page weekly PDF — SLA compliance, queues, category mix."""
    from fastapi.responses import Response

    from .weekly_report import generate_weekly_pdf

    start, end = _validated_window(start, end)
    try:
        payload = generate_weekly_pdf(load_all(), start=start, end=end)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"{exc}; use /report/weekly.json") from exc
    period = build_weekly_summary(load_all(), start=start, end=end)["period"]
    name = f"medops-weekly-{period['start'] or 'all'}.pdf"
    return Response(content=payload, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/report.pdf")
def report_pdf(department: Optional[str] = None, end: Optional[str] = None):
    """Week 4: one-click executive PDF for a department (or all departments)."""
    from fastapi.responses import FileResponse
    info = _report_scope(department, end)
    if not info["pdf"]:
        raise HTTPException(status_code=503, detail="PDF engine unavailable; use /report (JSON)")
    name = f"medops-weekly-{(department or 'all').lower().replace(' ', '-')}.pdf"
    return FileResponse(info["pdf"], media_type="application/pdf", filename=name)
