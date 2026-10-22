"""One-sentence summary generation (deterministic template)."""
import re
from .models import Category, Priority


def summarize(message: str, sender: str, category: Category, priority: Priority) -> str:
    core = re.sub(r"\s+", " ", message.strip().rstrip("."))
    words = core.split()
    if len(words) > 22:
        core = " ".join(words[:22]) + "..."
    dept = sender.split("(")[-1].rstrip(")") if "(" in sender else "hospital staff"
    return f"{core}. Reported by {dept}; classified as {category} with {priority} priority."
