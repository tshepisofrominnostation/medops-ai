"""Pydantic models — the strict ticket contract."""
from typing import Literal, Optional
from pydantic import BaseModel, Field

Priority = Literal["High", "Medium", "Low"]
Category = Literal["IT & Medical Tech", "HR", "Finance", "Operations"]


class TicketIn(BaseModel):
    """Raw intake: the unstructured message from hospital staff."""
    message: str = Field(..., description="Raw operational request text (validated in main.validate_message)")
    sender: Optional[str] = Field(None, description="Optional sender override, e.g. 'Dr. X (ICU)'")


class TicketOut(BaseModel):
    """The strict output schema required by the ops dashboard."""
    ticket_id: str = Field(..., pattern=r"^MED-\d{3,}$")
    timestamp: str = Field(..., description="ISO 8601 with timezone")
    sender: str
    category: Category
    priority: Priority
    summary: str
    assigned_to: str
