"""Quick CLI, no server needed.

    python -m app.cli "the aircon in theatre 2 is dead"      classify one message
    python -m app.cli import tickets.json [--dry-run] [--store PATH]
                                                            merge tickets exported
                                                            from the published console

Two stores exist on purpose: data/demo_tickets.json is the committed seed the published
page is built from, and data/tickets_processed.json is this machine's working store.
Pass --store to choose where an import lands; the result always names the file it wrote.
"""
import json
import sys
from pathlib import Path

from . import persistence
from .importer import import_file
from .pipeline import process_ticket


def _usage() -> None:
    print('Usage: python -m app.cli "your message" [- "Dr X (Ward)"]\n'
          '       python -m app.cli import <file.json> [--dry-run] [--store PATH]')


def main() -> None:
    if len(sys.argv) < 2:
        _usage()
        sys.exit(1)
    if sys.argv[1] == "import":
        paths = [a for a in sys.argv[2:] if not a.startswith("--")]
        if not paths:
            _usage()
            sys.exit(1)
        rest = sys.argv[2:]
        if "--store" in rest:
            store = rest[rest.index("--store") + 1]
            persistence.DB_PATH = Path(store).expanduser()
            paths = [p for p in paths if p != store]
        report = import_file(paths[0], dry_run="--dry-run" in rest)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    raw = " ".join(sys.argv[1:])
    ticket = process_ticket(raw)
    print(json.dumps(ticket.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
