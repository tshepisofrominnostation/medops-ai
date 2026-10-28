"""Response generator v1 with category templates and tone control."""

TEMPLATES = {
    "High": {
        "formal": "Your high-priority request has been acknowledged. On-call engineering has been notified, and an engineer will arrive or respond within the 15-minute SLA ETA.",
        "plain": "High-priority ticket received! On-call team is on it, expect a response within 15 minutes."
    },
    "Medium": {
        "formal": "Your request has been logged and queued for standard processing. We will address this during normal operating hours.",
        "plain": "Got your request. It's logged and queued for processing."
    },
    "Low": {
        "formal": "Your feedback/request has been recorded for review during routine maintenance cycles.",
        "plain": "Recorded! Thanks for letting us know."
    }
}

def generate_response(category: str, priority: str, tone: str = "plain") -> str:
    """Generate a template response based on priority/category and tone."""
    priority_dict = TEMPLATES.get(priority, TEMPLATES["Medium"])
    return priority_dict.get(tone, priority_dict["plain"])