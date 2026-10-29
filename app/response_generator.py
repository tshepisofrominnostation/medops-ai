
"""Category-specific response templates with priority and tone control."""

# literal restrivts the tone to these three specific string values
from typing import Literal

from .models import Category, Priority

# Using Tone helps other files understand which values are valid.
Tone = Literal["formal", "friendly", "urgent"]


# Words and phrases that may indicate urgency in an incoming message.
URGENT_INDICATORS = (
    "urgent",
    "urgently",
    "immediately",
    "emergency",
    "critical",
    "life-threatening",
    "not working",
    "will not start",
    "down",
    "danger",
    "unsafe",
    "asap",
)

# Words and phrases that may indicate a friendly or conversational tone.
FRIENDLY_INDICATORS = (
    "hi",
    "hello",
    "hey",
    "please help",
    "could you please",
    "thank you",
    "thanks",
    "i would appreciate",
)

def detect_tone(message: str) -> Tone:
    """
    Detect the likely tone of an incoming message.

    This initial implementation uses keyword rules.
    It is not an AI language model and may need refinement.
    """

    # Convert the message to lowercase for case-insensitive matching.
    text = message.lower()

    # Urgency takes precedence because it can be important in
    # hospital operations. Ticket priority is still assessed separately.
    if any(indicator in text for indicator in URGENT_INDICATORS):
        return "urgent"

    # Check for friendly or conversational language.
    if any(indicator in text for indicator in FRIENDLY_INDICATORS):
        return "friendly"

    # Use formal as the default when no other tone is detected.
    return "formal"


CATEGORY_GUIDANCE: dict[Category, str] = {
    "IT & Medical Tech": (
        "The IT and Medical Technology Support team will review the issue."
    ),
    "HR": "The Human Resources team will review your request.",
    "Finance": "The Finance team will review your request.",
    "Operations": "The Operations team will review your request.",
}

PRIORITY_GUIDANCE: dict[Priority, str] = {
    "High": (
        "This request has been marked high priority. "
        "The responsible team should assess it promptly."
    ),
    "Medium": (
        "This request has been recorded for review. "
        "The responsible team will provide an update as information becomes available."
    ),
    "Low": (
        "This request has been recorded for routine review. "
        "The responsible team will provide an update when available."
    ),
}

TONE_OPENINGS: dict[Tone, str] ={
    "formal": "Thank you for submittinng your request.",
    "friendly": "Hi! Thanks for leting us know. We're to help.",
    "urgent": "Attention: Your request requires prompt view.",
}

TONE_CLOSING: dict[Tone, str] = {
    "formal": (
        "Please follow the established procedures for your deparment"
    ),
    "friendly": (
        "Thank you for your patience. Please let us know if you have"
        "any additional information to share."
    ),
    "urgent": (
        "Please contact the appropriate on-call team if immediate "
        "attention is required. Follow your organisation's safety "
        "procedures where applicable."
    ),
}


def generate_response(
    category: Category,
    priority: Priority,
    tone: Tone,
) -> str:
    """
    Generate a response using the detected tone, ticket category,
    and ticket priority.
    """

    # Get the appropriate guidance for the category and priority.
    category_message = CATEGORY_GUIDANCE[category]
    priority_message = PRIORITY_GUIDANCE[priority]

    # Select an opening and closing based on the detected tone.
    if tone == "formal":
        opening = "Thank you for submitting your request."
        closing = (
            "Please refer to the established procedures "
            "for your department."
        )

    elif tone == "friendly":
        opening = (
            "Hi! Thanks for letting us know. "
            "We're here to help."
        )
        closing = (
            "Thanks for your patience. Please let us know "
            "if you have any additional information to share."
        )

    else:  # The detected tone is urgent.
        opening = "Attention: Your request requires prompt review."
        closing = (
            "Please contact the appropriate on-call team if "
            "immediate attention is required. Follow your "
            "organisation's safety procedures where applicable."
        )

    # Combine the selected wording with category and priority guidance.
    return (
        f"{opening} {category_message} "
        f"{priority_message} {closing}"
    )
