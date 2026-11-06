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
from .notify import notify_assignment
from .report import write_report
from .models import TicketIn, TicketOut
from .pipeline import process_ticket
from .persistence import load_all
from .reply_writer import ReplyWriter

MAX_MESSAGE = 2000
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

app = FastAPI(
    title="MedOps AI",
    description="Smart Ticket Classification Engine + Reply Writer for hospital operations.",
    version="1.1.0",
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
    return {"status": "ok", "service": "MedOps AI classification engine",
            "reply_writer": "llm" if writer.llm.configured else "template",
            "version": app.version}


@app.post("/tickets", response_model=TicketOut)
def create_ticket(payload: TicketIn):
    error = validate_message(payload.message)
    if error:
        raise HTTPException(status_code=400, detail=error)
    ticket = process_ticket(payload.message, payload.sender)
    alert = notify_assignment(ticket.model_dump())
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


@app.get("/tickets")
def list_tickets():
    return load_all()


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


@app.get("/report.pdf")
def report_pdf(department: Optional[str] = None):
    """S2-3: one-click PDF summary, optionally scoped to one department."""
    from fastapi.responses import FileResponse
    import tempfile, pathlib
    out = pathlib.Path(tempfile.mkdtemp()) / "summary.pdf"
    info = write_report(load_all(), str(out), department)
    if not info["pdf"]:
        raise HTTPException(status_code=503, detail="PDF engine unavailable; HTML written instead")
    name = f"medops-summary-{(department or 'all').lower().replace(' ', '-')}.pdf"
    return FileResponse(info["pdf"], media_type="application/pdf", filename=name)
