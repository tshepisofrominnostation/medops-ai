
"""FastAPI application for hospital ticket intake and response generation."""

from fastapi import FastAPI

# Import the request and response models.
from .models import TicketIn, TicketOut

# Import the pipeline that processes tickets and detects tone automatically.
from .pipeline import process_ticket

# Import the function that retrieves saved tickets.
from .persistence import load_all


# Create the FastAPI application.
app = FastAPI(
    title="MedOps AI",
    description=(
        "Smart Ticket Classification Engine for hospital operations. "
        "It classifies, prioritises, and generates responses to requests "
        "with automatically detected tone."
    ),
    version="0.2.0",
)


@app.post(
    "/tickets",
    response_model=TicketOut,
    response_model_by_alias=False,
)
def create_ticket(payload: TicketIn) -> TicketOut:
    """
    Process a hospital request and return a completed ticket.

    The system automatically detects the message tone.
    The requester does not need to select a tone manually.
    """

    # Pass the message and optional sender to the pipeline.
    # The pipeline handles classification, priority, tone detection,
    # response generation, and persistence.
    return process_ticket(
        message=payload.message,
        sender_override=payload.sender,
    )


@app.get("/tickets")
def list_tickets() -> list[dict]:
    """Return all processed tickets stored in the local database."""

    return load_all()


@app.get("/health")
def health() -> dict:
    """Check whether the MedOps AI API is running."""

    return {
        "status": "ok",
        "service": "MedOps AI classification and response engine",
    }
