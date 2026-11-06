import json
import random
from datetime import date, timedelta
from pathlib import Path

CATEGORIES = ["IT & Medical Tech", "HR", "Finance", "Operations"]
PRIORITIES = ["High", "Medium", "Low"]


def generate(n=200, seed=42):
    rng = random.Random(seed)
    start = date(2026, 10, 1)
    tickets = []
    for i in range(1, n + 1):
        category = rng.choice(CATEGORIES)
        day = start + timedelta(days=rng.randint(0, 29))
        tickets.append({
            "ticket_id": f"SYN-{i:03d}",
            "category": category,
            "priority": rng.choice(PRIORITIES),
            "assigned_to": category,
            "created_date": f"{day.isoformat()}T09:00:00",
        })
    return tickets


if __name__ == "__main__":
    out = Path(__file__).parent / "data" / "synthetic_tickets.json"
    out.write_text(json.dumps(generate(), indent=2))
    print(f"Wrote {out}")