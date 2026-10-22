"""FastAPI application — hospital staff intake endpoint."""
from fastapi import FastAPI

from .models import TicketIn, TicketOut
from .pipeline import process_ticket
from .persistence import load_all

app = FastAPI(
    title="MedOps AI",
    description="Smart Ticket Classification Engine for hospital operations: ingest, classify, prioritise, structure, persist.",
    version="0.1.0",
)


@app.post("/tickets", response_model=TicketOut, response_model_by_alias=False)
def create_ticket(payload: TicketIn) -> TicketOut:
    """Ingest a raw operational request and return the structured classified ticket."""
    return process_ticket(payload.message, payload.sender)


@app.get("/tickets")
def list_tickets() -> list[dict]:
    """All processed tickets (the local database contents)."""
    return load_all()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "MedOps AI classification engine"}
