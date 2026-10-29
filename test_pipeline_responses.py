
"""Check that the ticket pipeline generates responses in all tones."""

from app.pipeline import process_ticket

# A sample hospital staff request for the pipeline to process.
message = (
    "From: staff@hospital.org\n"
    "Subject: HR request\n\n"
    "I need assistance updating my employee details."
)

# Try the same request with each supported communication tone.
for tone in ("formal", "friendly", "urgent"):

    # Process the ticket and ask the pipeline to use this tone.
    # Note: each call may save a separate ticket to your data file.
    ticket = process_ticket(message, tone=tone)

    # Display the main fields so you can inspect the result.
    print(f"\n--- {tone.upper()} ---")
    print("Ticket ID:", ticket.ticket_id)
    print("Category:", ticket.category)
    print("Priority:", ticket.priority)
    print("Assigned to:", ticket.assigned_to)
    print("Tone:", ticket.tone)
    print("Response:", ticket.response)

    # Confirm that a response was generated and the selected tone
    # was retained in the returned ticket.
    assert ticket.response
    assert ticket.tone == tone

print("\nAll three tone checks passed.")

