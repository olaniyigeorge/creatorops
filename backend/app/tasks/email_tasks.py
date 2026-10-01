import httpx

from app.integrations.email import send_email
from app.tasks import celery_app


@celery_app.task(
    name="send_email",
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    max_retries=5,
)
def send_email_task(to: str, subject: str, html: str) -> None:
    send_email(to, subject, html)
