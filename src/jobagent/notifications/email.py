"""Handles the rare case where a listing asks candidates to apply by
emailing a hiring contact directly rather than through a web form
(pipeline step SEND EMAIL IF APPROPRIATE). Most listings resolve to a form
via jobagent.application.runner; this is only used when the description
itself names an application email address and no application form exists.
"""
from __future__ import annotations

import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

_EMAIL_APPLY_PATTERN = re.compile(
    r"(?:apply|send(?:ing)?|email)[^.\n]{0,40}?(?:to|at)?\s*[:\-]?\s*([\w.+-]+@[\w-]+\.[\w.-]+)",
    re.IGNORECASE,
)
_GENERIC_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class EmailError(RuntimeError):
    pass


def find_email_apply_address(description: str) -> Optional[str]:
    """Looks for an explicit 'apply by emailing X@Y' style instruction.
    Deliberately conservative — a bare email address appearing anywhere in
    the description (e.g. a generic 'contact us' footer) is not enough; it
    must be introduced with apply/send/email language."""
    match = _EMAIL_APPLY_PATTERN.search(description)
    return match.group(1) if match else None


def send_application_email(to_address: str, subject: str, body: str, attachments: list[Path]) -> None:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    from_email = os.environ.get("SMTP_FROM_EMAIL")
    if not all([host, username, password, from_email]):
        raise EmailError(
            "SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD/SMTP_FROM_EMAIL must be set "
            "(see .env.example) to send application emails."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_email
    message["To"] = to_address
    message.set_content(body)
    for path in attachments:
        message.add_attachment(
            path.read_bytes(), maintype="application", subtype="octet-stream", filename=path.name
        )

    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)
