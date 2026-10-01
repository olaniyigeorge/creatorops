"""Persisted workflow execution. Workflows register by name; the Celery task is a
thin wrapper around `execute_run` so the logic is testable without a broker."""

import uuid
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import Run, RunStatus
from app.db.repo import WorkspaceRepo
from app.db.session import SessionLocal
from app.tasks import celery_app

# A workflow takes the Run and returns the new state_json.
Workflow = Callable[[Run, Session], dict[str, Any]]
WORKFLOWS: dict[str, Workflow] = {"noop": lambda run, db: {"ok": True}}


def register_workflow(name: str, fn: Workflow) -> None:
    WORKFLOWS[name] = fn


def execute_run(db: Session, workspace_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    run = WorkspaceRepo(db, Run, workspace_id).get(run_id)
    if run is None:
        raise LookupError(f"Run {run_id} not found in workspace {workspace_id}")

    run.status = RunStatus.RUNNING.value
    db.commit()
    try:
        workflow = WORKFLOWS.get(run.workflow)
        if workflow is None:
            raise ValueError(f"Unknown workflow '{run.workflow}'")
        run.state_json = workflow(run, db)
        run.status = RunStatus.SUCCEEDED.value
    except Exception as exc:
        db.rollback()
        run = WorkspaceRepo(db, Run, workspace_id).get(run_id)
        run.status = RunStatus.FAILED.value
        run.error = f"{type(exc).__name__}: {exc}"
    run.finished_at = utcnow()
    db.commit()
    return run


@celery_app.task(name="run_workflow")
def run_workflow(workspace_id: str, run_id: str) -> str:
    db = SessionLocal()
    try:
        return execute_run(db, uuid.UUID(workspace_id), uuid.UUID(run_id)).status
    finally:
        db.close()
