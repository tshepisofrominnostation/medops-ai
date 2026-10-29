
"""Tests for sender extraction and message parsing."""

from app.parser import parse_sender


# Test 1: Extract a sender from an email-style From: header.
message = (
    "From: staff@hospital.org\n"
    "Subject: HR request\n\n"
    "I need assistance updating my employee details."
)

body, sender = parse_sender(message)

assert sender == "staff@hospital.org"
assert "From:" not in body
assert "I need assistance updating my employee details." in body

print("Test 1 passed: From: header extracted correctly.")


# Test 2: An explicitly supplied sender should take precedence.
body, sender = parse_sender(
    "I need assistance.",
    override="Jane Smith",
)

assert sender == "Jane Smith"

print("Test 2 passed: sender override works.")


# Test 3: A message without sender information uses the fallback.
body, sender = parse_sender("I need help with a printer.")

assert sender == "Unspecified hospital staff"

print("Test 3 passed: fallback sender works.")


print("\nAll parser tests passed.")
