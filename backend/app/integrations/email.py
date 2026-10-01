"""Transactional email via Resend's REST API (system sender).

Mail that should come from the Owner (editor briefs) goes through the Owner's
Gmail in M4; this module is for system notifications.
"""

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> Optional[str]:
    """Returns the provider message id, or None when no API key is configured (dev)."""
    if not settings.RESEND_API_KEY:
        logger.info("[email disabled] to=%s subject=%s", to, subject)
        return None
    resp = httpx.post(
        RESEND_URL,
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={"from": settings.EMAIL_FROM, "to": [to], "subject": subject, "html": html},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("id")
