"""Quick CLI: python -m app.cli "message" — no server needed."""
import json
import sys

from .pipeline import process_ticket


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m app.cli "your message" [- "Dr X (Ward)"]')
        sys.exit(1)
    raw = " ".join(sys.argv[1:])
    ticket = process_ticket(raw)
    print(json.dumps(ticket.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
