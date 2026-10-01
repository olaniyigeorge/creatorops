import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import WorkspaceContext, workspace_ctx
from app.api.schemas import NotificationOut
from app.db.base import utcnow
from app.db.models import Notification
from app.db.repo import WorkspaceRepo

router = APIRouter(tags=["notifications"])


@router.get(
    "/workspaces/{workspace_id}/notifications", response_model=list[NotificationOut]
)
def list_notifications(unread: bool = False, ctx: WorkspaceContext = Depends(workspace_ctx)):
    # Always scoped to the caller: notifications are per-user, not per-workspace.
    rows = WorkspaceRepo(ctx.db, Notification, ctx.workspace.id).list(user_id=ctx.user.id)
    if unread:
        rows = [n for n in rows if n.read_at is None]
    return sorted(rows, key=lambda n: n.created_at, reverse=True)


@router.post(
    "/workspaces/{workspace_id}/notifications/{notification_id}/read",
    response_model=NotificationOut,
)
def mark_read(notification_id: str, ctx: WorkspaceContext = Depends(workspace_ctx)):
    try:
        nid = uuid.UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Notification not found")
    n = WorkspaceRepo(ctx.db, Notification, ctx.workspace.id).get(nid)
    if n is None or n.user_id != ctx.user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.read_at = n.read_at or utcnow()
    ctx.db.commit()
    return n
