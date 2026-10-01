"""Single place that enqueues background work. Tests replace these functions;
TASKS_EAGER runs them inline for local development without Redis."""

import logging
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)


def enqueue_run(workspace_id: uuid.UUID, run_id: uuid.UUID) -> None:
    from app.tasks.runner import run_workflow

    if settings.TASKS_EAGER:
        run_workflow(str(workspace_id), str(run_id))
    else:
        run_workflow.delay(str(workspace_id), str(run_id))


def enqueue_email(to: str, subject: str, html: str) -> None:
    """Best effort: a broker outage must not fail the request that triggered the email."""
    from app.tasks.email_tasks import send_email_task

    try:
        if settings.TASKS_EAGER:
            send_email_task(to, subject, html)
        else:
            send_email_task.delay(to, subject, html)
    except Exception:
        logger.exception("Could not enqueue email to %s", to)
