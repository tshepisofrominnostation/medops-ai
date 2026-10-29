
"""Message parsing — extract sender information and issue location."""

import re


# Matches a sender written in an email-style header, for example:
# From: staff@hospital.org
# From: Jane Smith
FROM_RE = re.compile(
    r"^\s*From:\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Matches a signed message ending with a person's name and department,
# for example: — Jane Smith (Human Resources)
# This preserves the signature format your original parser supported.
SIGNED_RE = re.compile(
    r"[-—–]\s*([A-Z][A-Za-z.\-'\s]+?)\s*\((.+?)\)\s*$",
    re.MULTILINE,
)


def parse_sender(
    raw: str,
    override: str | None = None,
) -> tuple[str, str]:
    """Return (message_without_sender_header, sender_label).

    The sender is determined in this order:
    1. Use the explicitly supplied override, if provided.
    2. Extract a From: header, if present.
    3. Extract a supported signature at the end of the message.
    4. Use a default label if no sender is found.
    """

    # Remove unnecessary spaces and newlines around the message.
    raw = raw.strip()

    # An explicit sender supplied by the API takes precedence.
    if override:
        return _dequote(raw), override.strip()

    # Look for an email-style From: header anywhere in the message.
    from_match = FROM_RE.search(raw)

    if from_match:
        # Capture the sender value, such as staff@hospital.org.
        sender = from_match.group(1).strip()

        # Remove the From: line so the remaining message contains
        # the subject and actual request, rather than the sender header.
        body = FROM_RE.sub("", raw, count=1)
        body = re.sub(
            r"^\s*Subject:\s*.*$",
            "",
            body,
            count=1,
            flags=re.IGNORECASE | re.MULTILINE,
        ).strip()

        return _dequote(body), sender

    # If there is no From: header, try the existing signature format.
    signature_match = SIGNED_RE.search(raw)

    if signature_match:
        name = signature_match.group(1).strip()
        department = signature_match.group(2).strip()

        # Remove the signature from the message body.
        body = SIGNED_RE.sub("", raw).strip()

        # Return both the cleaned body and a readable sender label.
        return _dequote(body), f"{name} ({department})"

    # Use this fallback only when no supported sender format is found.
    return _dequote(raw), "Unspecified hospital staff"


def _dequote(text: str) -> str:
    """Remove wrapping quotes and clean up one known quote pattern."""

    # Remove a pair of double quotes surrounding the whole message.
    text = text.strip()

    if text.startswith('"'):
        text = text[1:]

    if text.endswith('"'):
        text = text[:-1]

    # Clean up a period followed by a closing quote and a space.
    # Unlike the previous 'or True' condition, this is unconditional
    # only for the specific text replacement itself.
    text = text.replace('." ', '. ')

    return text.strip()


def extract_location(message: str) -> str | None:
    """Extract a recognised hospital location, if one is mentioned."""

    # Recognise locations such as Bay 4, ICU, Ward A, or Room 12.
    location_pattern = (
        r"\b(Bay \d+|ICU|Theatre \d+|Ward \w+|"
        r"Room \d+|Bed \d+|Block [A-Z])\b"
    )

    match = re.search(location_pattern, message, re.IGNORECASE)

    # Return the matched location, or None when no location is found.
    return match.group(1) if match else None
