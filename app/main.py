"""FastAPI service - hardened intake, descriptive errors, reply drafting with fallback."""
import re

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

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
    return process_ticket(payload.message, payload.sender)


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
    return {"ticket": ticket, "reply": reply}


@app.get("/tickets")
def list_tickets():
    return load_all()
