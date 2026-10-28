"""Pipeline orchestration: ingest -> parse -> classify -> prioritise -> structure -> persist."""
from datetime import datetime, timezone

from .assigner import assign
from .classifier import classify
from .models import TicketOut
from .parser import parse_sender
from .persistence import append
from .prioritizer import prioritize
from .responder import generate_response
from .summarizer import summarize

def process_ticket(
    message: str, 
    sender_override: str | None = None, 
    include_response: bool = False, 
    tone: str = "plain"
) -> TicketOut:
    body, sender = parse_sender(message, sender_override)
    category, _conf = classify(body)
    priority = prioritize(body, sender)
    summary = summarize(body, sender, category, priority)
    assigned_to = assign(category, priority)
    record = {
        "ticket_id": "",  # assigned by the persistence layer (MED-###)
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "sender": sender,
        "category": category,
        "priority": priority,
        "summary": summary,
        "assigned_to": assigned_to,
    }
    
    if include_response:
        record["response"] = generate_response(category, priority, tone)
        
    record = append(record)
    return TicketOut(**record)