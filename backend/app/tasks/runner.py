"""Persisted, re-entrant workflow execution.

Workflows register by name and receive a `WorkflowContext`. A run is claimed
atomically (so a redelivered task cannot run it twice), parked as
WAITING_APPROVAL when a step escalates, and re-entered after the admin decides.
"""

import logging
import uuid
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import utcnow
from app.db.models import Run, RunStatus
from app.db.repo import WorkspaceRepo
from app.db.session import SessionLocal
from app.tasks import celery_app
from app.workflows.context import RunPaused, WorkflowContext

logger = logging.getLogger(__name__)

Workflow = Callable[[WorkflowContext], dict[str, Any]]
WORKFLOWS: dict[str, Workflow] = {"noop": lambda ctx: {"ok": True}}


# Optional pydantic model per workflow, used to validate run params at the API.
PARAMS_MODELS: dict[str, type] = {}


def register_workflow(name: str, fn: Workflow, params_model: type | None = None) -> None:
    WORKFLOWS[name] = fn
    if params_model is not None:
        PARAMS_MODELS[name] = params_model


def _claim(db: Session, workspace_id: uuid.UUID, run_id: uuid.UUID) -> bool:
    """Atomically move PENDING (or a stale RUNNING) to RUNNING. False = someone else has it."""
    now = utcnow()
    stale = now - timedelta(minutes=settings.RUN_STALE_MINUTES)
    result = db.execute(
        update(Run)
        .where(
            Run.id == run_id,
            Run.workspace_id == workspace_id,
            or_(
                Run.status == RunStatus.PENDING.value,
                (Run.status == RunStatus.RUNNING.value) & (Run.started_at < stale),
            ),
        )
        .values(status=RunStatus.RUNNING.value, started_at=now)
    )
    db.commit()
    return result.rowcount == 1


def execute_run(
    db: Session, workspace_id: uuid.UUID, run_id: uuid.UUID, rate=None
) -> Run:
    run = WorkspaceRepo(db, Run, workspace_id).get(run_id)
    if run is None:
        raise LookupError(f"Run {run_id} not found in workspace {workspace_id}")
    if not _claim(db, workspace_id, run_id):
        logger.info("Run %s not claimable (status=%s); skipping", run_id, run.status)
        db.refresh(run)
        return run
    db.refresh(run)

    kwargs = {"rate": rate} if rate else {}
    ctx = WorkflowContext(db, run, **kwargs)
    try:
        workflow = WORKFLOWS.get(run.workflow)
        if workflow is None:
            raise ValueError(f"Unknown workflow '{run.workflow}'")
        state = workflow(ctx)
        run = WorkspaceRepo(db, Run, workspace_id).get(run_id)
        run.state_json = state
        run.status = RunStatus.SUCCEEDED.value
        run.finished_at = utcnow()
    except RunPaused:
        db.rollback()
        run = WorkspaceRepo(db, Run, workspace_id).get(run_id)
        run.status = RunStatus.WAITING_APPROVAL.value
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


# Register built-in workflows (imported last: they import from this module).
from app.workflows import brief_flow, creative_flow, strategy_flow  # noqa: E402,F401
