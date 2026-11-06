"""Semantic PHI detector (closes risk R4 in docs/RISK_REPORT.md).

The regex screen in app/compliance.py catches *formatted* identifiers (ID numbers,
phones, emails). It cannot see a sentence like "Mr Dlamini in bed 12 has been
waiting", which is identifiable health information with no formatted pattern.

This module detects *composition*: an identifier is rarely dangerous alone, but a
person reference combined with a location, relationship, or health context is.
Each hit returns a reason and a severity so a reviewer sees why it was flagged.

Scope and limits (stated, not hidden)
  - Heuristic and rule-based, not a trained NER model. It will miss unusual names
    and non-English text, and it will over-flag some benign sentences.
  - Over-flagging is the chosen failure mode: the cost of a false alarm is a human
    reading one reply; the cost of a miss is a POPIA exposure.
  - It is a floor, not a guarantee. Human review of drafted replies stays required.
"""
import re

# Patient-style honorifics identify a likely patient or relative: hard block.
PATIENT_HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Mx|Baby|Mnr|Mev)\.?"
# Staff honorifics usually name a clinician, who is not a patient. Flag for review
# only, because blocking every "Dr Naidoo has been notified" would make replies unusable.
STAFF_HONORIFIC = r"(?:Dr|Prof|Sr|Sister|Nurse)\.?"
NAME = r"[A-Z][a-z]{2,}(?:[-'][A-Z][a-z]+)?"

# Words that look like names but are not people (sentence starts, wards, systems).
NOT_NAMES = {
    "The", "This", "That", "These", "Those", "There", "Your", "Our", "Please", "Thank",
    "Thanks", "Ticket", "Ward", "Room", "Bay", "Theatre", "Block", "Emergency", "Hospital",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December", "Finance", "Operations", "Maternity",
    "Biomedical", "Engineering", "Medical", "Duty", "Officer", "Manager", "Team", "Admin",
    "Dear", "Regards", "Kind", "Best", "Hello", "Hi", "Reference", "Thank", "Escalation",
}

PATTERNS = [
    # (rule, regex, severity, why)
    ("named_person",
     rf"\b{PATIENT_HONORIFIC}\s+{NAME}\b",
     "block", "Honorific plus surname names a specific person"),
    ("named_staff",
     rf"\b{STAFF_HONORIFIC}\s+{NAME}\b",
     "review", "Names a staff member; confirm this is not a patient"),
    ("bed_or_room_location",
     r"\b(?:in\s+)?(?:bed|cubicle|cot)\s*(?:no\.?|number|#)?\s*\d{1,3}\b",
     "block", "Bed or cubicle number can single out a patient"),
    ("relative_reference",
     r"\b(?:the\s+)?(?:lady|man|woman|gentleman|girl|boy|child|baby|patient|mother|father|"
     r"husband|wife|son|daughter|sister|brother|grandmother|grandfather)\s+"
     r"(?:from|in|of|whose|who|with|admitted|on)\b[^.]{0,60}",
     "block", "Describes an individual by relationship, place or history"),
    ("pronoun_medical_history",
     r"\b(?:he|she|they|his|her|their)\b[^.]{0,25}\b(?:is|was|has|had|been|on|started|attempted|"
     r"diagnosed|admitted)\b[^.]{0,40}\b(?:arv|antiretroviral|hiv|tb|tuberculosis|cancer|chemo|"
     r"dialysis|psychiatric|suicid|overdose|pregnan|abortion|std|sti|regimen|medication|"
     r"treatment|diagnos)\w*",
     "block", "Pronoun linked to a medical condition or treatment"),
    ("sensitive_condition_with_person",
     r"\b(?:patient|person|someone|individual)\b[^.]{0,40}\b(?:attempted\s+suicide|suicid\w*|"
     r"overdos\w*|hiv|aids|arv|tb|cancer|abortion|psychiatric|rape|assault)\b",
     "block", "Special personal information about an individual (POPIA s26)"),
    ("partial_account_number",
     r"\b(?:ending|ends)\s+(?:in\s+|with\s+)?\d{3,6}\b",
     "block", "Partial account or card number"),
    ("dated_visit",
     r"\b(?:since|on|last)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
     r"[^.]{0,30}\b(?:waiting|admitted|discharged|arrived|booked)\b",
     "review", "Dated patient movement"),
    ("age_and_gender",
     r"\b\d{1,3}[- ]year[- ]old\s+(?:man|woman|male|female|boy|girl|patient)\b",
     "review", "Age plus gender narrows identity"),
]

_COMPILED = [(n, re.compile(p, re.IGNORECASE if n not in ("named_person", "named_staff") else 0), s, w)
             for n, p, s, w in PATTERNS]


def _clean_name_hit(rule: str, text: str) -> bool:
    """Reject 'Dear Team'-style false hits for the name rule."""
    if rule not in ("named_person", "named_staff"):
        return True
    tail = text.split()[-1].strip(".,;:")
    return tail not in NOT_NAMES


def detect(text: str) -> dict:
    """Return every semantic-PHI hit with the reason and span."""
    body = text or ""
    hits = []
    for rule, rx, severity, why in _COMPILED:
        for m in rx.finditer(body):
            if not _clean_name_hit(rule, m.group(0)):
                continue
            hits.append({"rule": rule, "severity": severity, "why": why,
                         "match": m.group(0)[:80], "span": [m.start(), m.end()],
                         "layer": "semantic"})
    return {"flags": hits,
            "blocked": any(h["severity"] == "block" for h in hits),
            "review": any(h["severity"] == "review" for h in hits)}
