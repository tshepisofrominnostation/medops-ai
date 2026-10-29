
from app.response_generator import generate_response

for tone in ("formal", "friendly", "urgent"):
    response = generate_response(
        category="HR",
        priority="High",
        tone=tone,
    )

    print(f"\n--- {tone.upper()} ---")
    print(response)
