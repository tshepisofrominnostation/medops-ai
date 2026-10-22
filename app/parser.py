"""Message parsing — extract sender name/department and issue location."""
import re

SENDER_RE = re.compile(r'[-—–]\s*([A-Z][\w\.\-\s]+?)\s*[–—-]*\s*\((.+?)\)\s*$', re.M)
SIGNED_RE = re.compile(r'[-—–]\s*([A-Z][\w\.\-\s]+?)\s*\((.+?)\)\s*$')


def parse_sender(raw: str, override: str | None = None) -> tuple[str, str]:
    """Return (message_without_sender, sender_label)."""
    raw = raw.strip()
    if override:
        return _dequote(raw), override
    m = SIGNED_RE.search(raw)
    if m:
        name, dept = m.group(1).strip(), m.group(2).strip()
        body = _dequote(SIGNED_RE.sub("", raw).strip())
        return body, f"{name} ({dept})"
    return _dequote(raw), "Unspecified hospital staff"


def _dequote(text: str) -> str:
    """Strip one wrapping pair of quotes from a message, wherever the pair sits."""
    if text.startswith('"'):
        text = text[1:]
    if text.endswith('"'):
        text = text[:-1]
    if '." ' in text[:0] or True:
        text = text.replace('." ', '. ')
    return text.strip()


def extract_location(message: str) -> str | None:
    m = re.search(r'\b(Bay \d+|ICU|Theatre \d+|Ward \w+|Room \d+|Bed \d+|Block [A-Z])\b', message, re.I)
    return m.group(1) if m else None
