"""Assignment alerts (S4-1).

When a ticket is assigned, the owning team should hear about it without anyone
opening a dashboard. Transports are pluggable and default to dry-run, so the
platform never silently sends email in a test or demo.

Configuration (environment):
  MEDOPS_ALERTS=1            turn alerts on (default off)
  MEDOPS_WEBHOOK_URL=...     POST JSON to a webhook (Slack/Teams compatible text)
  MEDOPS_SMTP_HOST/PORT/USER/PASSWORD/FROM, MEDOPS_ALERT_TO=ops@example.com
                             send email via SMTP when the host is set
  MEDOPS_ALERT_ROUTES='{"HR Duty Officer": {"webhook": "https://...", "email": "hr@x.org"}}'
                             optional per-team destinations, keyed by assigned_to;
                             teams not listed fall back to the defaults above
The alert carries the full ticket JSON (S4-1 Definition of Done).
Anything unconfigured is recorded to the alert log instead of failing.
"""
import json
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

ALERT_LOG = Path(os.environ.get("MEDOPS_ALERT_LOG", "data/alerts.log"))


def alerts_enabled() -> bool:
    return os.environ.get("MEDOPS_ALERTS", "0") == "1"


def _message_for(record: dict) -> str:
    return (f"[{record.get('priority', 'Normal')}] {record.get('category', 'General')} "
            f"-> {record.get('assigned_to', 'unassigned')} | {record.get('ticket_id', '')} "
            f"| {record.get('summary', '')}")


def _log(record: dict, transport: str, detail: str = "") -> None:
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ticket_id": record.get("ticket_id"),
        "transport": transport,
        "detail": detail,
        "message": _message_for(record),
    }
    with ALERT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def _route_for(record: dict) -> dict:
    """Per-team destination from MEDOPS_ALERT_ROUTES, or {} to use the defaults."""
    try:
        routes = json.loads(os.environ.get("MEDOPS_ALERT_ROUTES", "") or "{}")
    except ValueError:
        return {}
    route = routes.get(record.get("assigned_to"), {})
    return route if isinstance(route, dict) else {}


def _send_webhook(url: str, record: dict) -> str:
    import urllib.request
    payload = json.dumps({"text": _message_for(record), "ticket": record},
                         default=str).encode()
    req = urllib.request.Request(url, data=payload,
                                headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:
        return f"webhook {resp.status}"


def _send_email(record: dict, to: Optional[str] = None) -> str:
    host = os.environ["MEDOPS_SMTP_HOST"]
    port = int(os.environ.get("MEDOPS_SMTP_PORT", "587"))
    msg = EmailMessage()
    msg["Subject"] = f"MedOps AI alert: {record.get('priority', '')} {record.get('category', '')}"
    msg["From"] = os.environ.get("MEDOPS_SMTP_FROM", "medops@localhost")
    msg["To"] = to or os.environ.get("MEDOPS_ALERT_TO", "ops@localhost")
    msg.set_content(_message_for(record) + "\n\nTicket JSON:\n"
                    + json.dumps(record, indent=2, default=str))
    with smtplib.SMTP(host, port, timeout=10) as smtp:
        if os.environ.get("MEDOPS_SMTP_USER"):
            smtp.starttls()
            smtp.login(os.environ["MEDOPS_SMTP_USER"], os.environ.get("MEDOPS_SMTP_PASSWORD", ""))
        smtp.send_message(msg)
    return f"email via {host}"


def notify_assignment(record: dict, force: bool = False) -> dict:
    """Alert the assigned team. Never raises: alerting must not break triage."""
    if not alerts_enabled() and not force:
        _log(record, "dry-run", "alerts disabled (set MEDOPS_ALERTS=1)")
        return {"sent": False, "transport": "dry-run", "reason": "alerts disabled"}

    try:
        route = _route_for(record)
        webhook = route.get("webhook") or os.environ.get("MEDOPS_WEBHOOK_URL")
        if webhook:
            detail = _send_webhook(webhook, record)
            _log(record, "webhook", detail)
            return {"sent": True, "transport": "webhook", "detail": detail}
        if os.environ.get("MEDOPS_SMTP_HOST"):
            detail = _send_email(record, route.get("email"))
            _log(record, "email", detail)
            return {"sent": True, "transport": "email", "detail": detail}
        _log(record, "dry-run", "no transport configured")
        return {"sent": False, "transport": "dry-run", "reason": "no transport configured"}
    except Exception as exc:                      # noqa: BLE001 - alerting is best-effort
        _log(record, "error", str(exc)[:200])
        return {"sent": False, "transport": "error", "reason": str(exc)[:200]}
