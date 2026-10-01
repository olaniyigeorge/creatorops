from celery import Celery

from app.core.config import settings

celery_app = Celery("creatorops", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,  # a worker killed mid-run (e.g. Render restart) re-queues the task
    task_reject_on_worker_lost=True,
    timezone="UTC",
)

from app.tasks import email_tasks, runner  # noqa: E402,F401  (registers tasks)
