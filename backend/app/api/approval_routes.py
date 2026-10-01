import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update

from app.api.deps import WorkspaceContext, owner_ctx
from app.api.schemas import ActionOut, ApprovalDecision, ApprovalOut
from app.db.base import utcnow
from app.db.models import (
    Action,
    ActionStatus,
    Approval,
    Run,
    RunStatus,
)
from app.db.repo import WorkspaceRepo
from app.gate.autonomy import ActionType
from app.memory.service import add_memory
from app.tasks import dispatch
from app.workflows.context import PayloadInvalid, validate_payload

# Approvals are owner-only: editors can see run activity but never decide.
router = APIRouter(tags=["approvals"])


def _out(ctx: WorkspaceContext, approval: Approval) -> ApprovalOut:
    action = WorkspaceRepo(ctx.db, Action, ctx.workspace.id).get(approval.action_id)
    return ApprovalOut(
        id=approval.id,
        status=approval.status,
        decision_note=approval.decision_note,
        decided_at=approval.decided_at,
        created_at=approval.created_at,
        action=ActionOut.model_validate(action),
        payload=approval.edited_payload_json or action.payload_json,
        guardrail_feedback=action.guardrail_feedback,
    )


def _get(ctx: WorkspaceContext, approval_id: str) -> Approval:
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Approval not found")
    approval = WorkspaceRepo(ctx.db, Approval, ctx.workspace.id).get(aid)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


@router.get("/workspaces/{workspace_id}/approvals", response_model=list[ApprovalOut])
def list_approvals(status: Optional[str] = None, ctx: WorkspaceContext = Depends(owner_ctx)):
    filters = {"status": status} if status else {}
    rows = WorkspaceRepo(ctx.db, Approval, ctx.workspace.id).list(**filters)
    rows.sort(key=lambda a: a.created_at, reverse=True)
    return [_out(ctx, a) for a in rows]


@router.get("/workspaces/{workspace_id}/approvals/{approval_id}", response_model=ApprovalOut)
def get_approval(approval_id: str, ctx: WorkspaceContext = Depends(owner_ctx)):
    return _out(ctx, _get(ctx, approval_id))


@router.post(
    "/workspaces/{workspace_id}/approvals/{approval_id}/decision",
    response_model=ApprovalOut,
)
def decide(
    approval_id: str,
    body: ApprovalDecision,
    ctx: WorkspaceContext = Depends(owner_ctx),
):
    approval = _get(ctx, approval_id)
    approved = body.decision == "approve"
    if body.edited_payload is not None and not approved:
        raise HTTPException(status_code=422, detail="Edits only apply to an approval")

    if body.edited_payload is not None:
        action = WorkspaceRepo(ctx.db, Action, ctx.workspace.id).get(approval.action_id)
        try:
            body.edited_payload = validate_payload(ActionType(action.type), body.edited_payload)
        except PayloadInvalid as exc:
            raise HTTPException(status_code=422, detail=f"Edited proposal is invalid: {exc}")

    # Conditional update: of two concurrent decisions, exactly one wins.
    claimed = ctx.db.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.workspace_id == ctx.workspace.id,
            Approval.status == "pending",
        )
        .values(
            status="approved" if approved else "rejected",
            decided_by=ctx.user.id,
            decided_at=utcnow(),
            decision_note=body.note,
            edited_payload_json=body.edited_payload,
        )
    )
    if claimed.rowcount != 1:
        ctx.db.rollback()
        raise HTTPException(status_code=409, detail="Already decided")

    action = WorkspaceRepo(ctx.db, Action, ctx.workspace.id).get(approval.action_id)
    action.status = (ActionStatus.APPROVED if approved else ActionStatus.REJECTED).value

    # The decision becomes workspace memory: this is how the agent learns preferences.
    verb = "approved" if approved else "rejected"
    text = f"Admin {verb}: {action.summary}"
    if body.note:
        text += f". Guidance: {body.note}"
    if body.edited_payload is not None:
        text += " (admin edited the proposal before approving)"
    add_memory(
        ctx.db,
        ctx.workspace.id,
        kind="preference" if body.note else "decision",
        text=text,
        source_approval_id=approval.id,
    )

    # Re-enter the parked run (only if it is actually parked on this approval).
    resumed = ctx.db.execute(
        update(Run)
        .where(
            Run.id == action.run_id,
            Run.workspace_id == ctx.workspace.id,
            Run.status == RunStatus.WAITING_APPROVAL.value,
        )
        .values(status=RunStatus.PENDING.value)
    ).rowcount
    ctx.db.commit()
    if resumed:
        dispatch.enqueue_run(ctx.workspace.id, action.run_id)

    ctx.db.refresh(approval)
    return _out(ctx, approval)
