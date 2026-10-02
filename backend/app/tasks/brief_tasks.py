"""Deadline tracking: a periodic scan starts a `brief_followup` run for each late brief."""

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.db.models import Brief, Run, RunStatus
from app.db.repo import WorkspaceRepo
from app.db.session import SessionLocal
from app.tasks import celery_app, dispatch
from app.workflows.brief_flow import ACTIVE, aware

logger = logging.getLogger(__name__)
_IN_FLIGHT = (RunStatus.PENDING.value, RunStatus.RUNNING.value, RunStatus.WAITING_APPROVAL.value)


def scan_overdue_briefs(db: Session) -> list[tuple[uuid.UUID, uuid.UUID]]:
    """Create a follow-up run per late brief. Returns (workspace_id, run_id) pairs to enqueue.

    The one cross-workspace query is the list of workspaces that have active briefs;
    everything after that goes through that workspace's repository.
    """
    now = utcnow()
    min_gap = timedelta(hours=settings.BRIEF_FOLLOWUP_INTERVAL_HOURS)
    created = []
    workspace_ids = db.scalars(select(Brief.workspace_id).where(Brief.status.in_(ACTIVE)).distinct())
    for ws_id in list(workspace_ids):
        runs = WorkspaceRepo(db, Run, ws_id)
        in_flight = {
            r.params_json.get("brief_id")
            for r in runs.list(workflow="brief_followup")
            if r.status in _IN_FLIGHT
        }
        for brief in WorkspaceRepo(db, Brief, ws_id).list():
            due, last = aware(brief.due_at), aware(brief.last_followup_at)
            if (
                brief.status not in ACTIVE
                or brief.editor_id is None
                or due is None
                or due > now
                or brief.followup_count > settings.BRIEF_MAX_FOLLOWUPS  # owner already told
                or (last is not None and now - last < min_gap)
                or str(brief.id) in in_flight
            ):
                continue
            run = runs.add(workflow="brief_followup", params_json={"brief_id": str(brief.id)})
            created.append((ws_id, run.id))
    db.commit()
    return created


@celery_app.task(name="scan_overdue_briefs")
def scan_overdue_briefs_task() -> int:
    db = SessionLocal()
    try:
        created = scan_overdue_briefs(db)
    finally:
        db.close()
    for ws_id, run_id in created:
        dispatch.enqueue_run(ws_id, run_id)
    return len(created)
