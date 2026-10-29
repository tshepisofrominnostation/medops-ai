
"""Coordinate the complete ticket-processing workflow.

The pipeline receives a message, extracts its details, classifies
and prioritises it, generates a response, and saves the ticket.
"""

# Used to record when the ticket was processed.
from datetime import datetime, timezone

# Import the existing modules responsible for each processing step.
from .assigner import assign
from .classifier import classify
from .models import TicketOut
from .parser import parse_sender
from .persistence import append
from .prioritizer import prioritize
from .response_generator import detect_tone, generate_response
from .summarizer import summarize


def process_ticket(
    message: str,
    sender_override: str | None = None,
) -> TicketOut:
    """Process a message and return the completed ticket.

    Args:
        message: The original message submitted by the requester.
        sender_override: An optional sender value supplied separately.

    Returns:
        A TicketOut object containing the processed ticket details
        and the generated response.
    """

    # Step 1: Extract the message body and identify the sender.
    # If sender_override is provided, the parser can use it instead
    # of relying only on sender information in the message.
    body, sender = parse_sender(message, sender_override)

    # Step 2: Predict the ticket category from the message body.
    # The confidence value is not needed by this pipeline at present,
    # so it is stored in _conf to show that it is intentionally unused.
    category, _conf = classify(body)

    # Step 3: Decide how urgent the ticket is.
    priority = prioritize(body, sender)

    # Step 4: Create a short summary for the operations team.
    summary = summarize(body, sender, category, priority)

    # Step 5: Choose the team responsible for handling the ticket.
    assigned_to = assign(category, priority)

    # Step 6: Detect the tone of the incoming message atumatically.
    # The requester does need to select a tone manually.
    detected_tone = detect_tone(body)

    # Generate a response using the ticket category, priority,
    response = generate_response(
        category=category,
        priority=priority,
        tone=detected_tone
    )

    # Step 7: Collect the processed information into a dictionary.
    # The persistence layer will assign the actual ticket ID.
    record = {
        "ticket_id": "",
        # Record the current time with its local timezone offset.
        "timestamp": datetime.now(timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds"),
        "sender": sender,
        "category": category,
        "priority": priority,
        "summary": summary,
        "assigned_to": assigned_to,
        # Save the generated message and the tone used.
        "response": response,
        "tone": detected_tone,
    }

    # Step 8: Save the ticket and retrieve the completed record.
    # The persistence layer may fill in fields such as ticket_id.
    record = append(record)

    # Step 9: Validate the saved record against the TicketOut schema
    # and return it to the caller.
    return TicketOut(**record)
