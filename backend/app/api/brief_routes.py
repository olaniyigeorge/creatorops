import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.api.deps import WorkspaceContext, owner_ctx, workspace_ctx
from app.comms import briefs as comms
from app.db.base import utcnow
from app.db.models import Brief, BriefStatus, CalendarItem
from app.db.repo import WorkspaceRepo
from app.tasks import dispatch
from app.workflows.brief_flow import OPEN, aware

router = APIRouter(tags=["briefs"])

S = BriefStatus
# What the assigned editor may do. Owners may move a brief to any state.
EDITOR_TRANSITIONS = {
    S.ASSIGNED.value: {S.IN_PROGRESS.value, S.SUBMITTED.value},
    S.IN_PROGRESS.value: {S.SUBMITTED.value},
}


class BriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    calendar_item_id: uuid.UUID
    title: str = ""
    editor_id: Optional[uuid.UUID]
    due_at: Optional[datetime]
    status: str
    overdue: bool = False
    followup_count: int
    body_json: dict[str, Any]
    submitted_at: Optional[datetime]
    created_at: datetime


class BriefUpdate(BaseModel):
    editor_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None


class StatusUpdate(BaseModel):
    status: BriefStatus


def _out(db, ws_id, b: Brief) -> BriefOut:
    item = WorkspaceRepo(db, CalendarItem, ws_id).get(b.calendar_item_id)
    due = aware(b.due_at)
    out = BriefOut.model_validate(b)
    return out.model_copy(
        update={
            "title": (item.idea_json.get("title", "") if item else ""),
            "due_at": due,
            "overdue": bool(due and due < utcnow() and b.status in (S.ASSIGNED.value, S.IN_PROGRESS.value)),
        }
    )


def _visible(ctx: WorkspaceContext, brief_id: str) -> Brief:
    """Owners see every brief; an editor sees only their own. Others get 404."""
    try:
        bid = uuid.UUID(brief_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Brief not found")
    brief = WorkspaceRepo(ctx.db, Brief, ctx.workspace.id).get(bid)
    if brief is None or (not ctx.is_owner and brief.editor_id != ctx.user.id):
        raise HTTPException(status_code=404, detail="Brief not found")
    return brief


@router.get("/workspaces/{workspace_id}/briefs", response_model=list[BriefOut])
def list_briefs(ctx: WorkspaceContext = Depends(workspace_ctx)):
    briefs = WorkspaceRepo(ctx.db, Brief, ctx.workspace.id).list()
    if not ctx.is_owner:
        briefs = [b for b in briefs if b.editor_id == ctx.user.id]
    briefs.sort(key=lambda b: (aware(b.due_at) is None, aware(b.due_at)))
    return [_out(ctx.db, ctx.workspace.id, b) for b in briefs]


@router.get("/workspaces/{workspace_id}/briefs/{brief_id}", response_model=BriefOut)
def get_brief(brief_id: str, ctx: WorkspaceContext = Depends(workspace_ctx)):
    return _out(ctx.db, ctx.workspace.id, _visible(ctx, brief_id))


@router.patch("/workspaces/{workspace_id}/briefs/{brief_id}", response_model=BriefOut)
def update_brief(brief_id: str, body: BriefUpdate, ctx: WorkspaceContext = Depends(owner_ctx)):
    """Owner: reassign the editor and/or move the deadline. A new editor restarts follow-ups."""
    brief = _visible(ctx, brief_id)
    if brief.status not in OPEN:
        raise HTTPException(status_code=409, detail=f"Brief is {brief.status}")
    emails = []
    fields = body.model_dump(exclude_unset=True)
    if fields.get("editor_id") and fields["editor_id"] != brief.editor_id:
        editor = comms.member_user(ctx.db, ctx.workspace.id, fields["editor_id"])
        if editor is None:
            raise HTTPException(status_code=422, detail="Editor is not a member of this workspace")
        brief.editor_id = editor.id
        brief.status = S.ASSIGNED.value
        brief.followup_count = 0
        brief.last_followup_at = None
        item = WorkspaceRepo(ctx.db, CalendarItem, ctx.workspace.id).get(brief.calendar_item_id)
        emails.append(
            comms.notify_brief_assigned(
                ctx.db, ctx.workspace, brief, item.idea_json.get("title", "video"), editor
            )
        )
    if fields.get("due_at"):
        brief.due_at = fields["due_at"]
        brief.followup_count = 0  # a new date is a fresh deadline
        brief.last_followup_at = None
    ctx.db.commit()
    for e in emails:
        dispatch.enqueue_email(e.to, e.subject, e.html)
    return _out(ctx.db, ctx.workspace.id, brief)


@router.post("/workspaces/{workspace_id}/briefs/{brief_id}/status", response_model=BriefOut)
def set_status(brief_id: str, body: StatusUpdate, ctx: WorkspaceContext = Depends(workspace_ctx)):
    brief = _visible(ctx, brief_id)
    new = body.status.value
    if not ctx.is_owner and new not in EDITOR_TRANSITIONS.get(brief.status, set()):
        raise HTTPException(status_code=409, detail=f"Cannot move a brief from {brief.status} to {new}")
    brief.status = new
    emails = []
    if new == S.SUBMITTED.value:
        brief.submitted_at = utcnow()
        item = WorkspaceRepo(ctx.db, CalendarItem, ctx.workspace.id).get(brief.calendar_item_id)
        title = item.idea_json.get("title", "video")
        emails = comms.notify_owners(
            ctx.db, ctx.workspace, brief, "brief_submitted",
            f"Editor delivered: {title}", f"{ctx.user.name or ctx.user.email} marked this brief as delivered.",
        )
    ctx.db.commit()
    for e in emails:
        dispatch.enqueue_email(e.to, e.subject, e.html)
    return _out(ctx.db, ctx.workspace.id, brief)
