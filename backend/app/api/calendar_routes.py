import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from app.api.deps import WorkspaceContext, workspace_ctx
from app.db.models import CalendarItem
from app.db.repo import WorkspaceRepo

router = APIRouter(tags=["calendar"])


class CalendarItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    idea_json: dict[str, Any]
    scheduled_for: Optional[datetime]
    status: str

    @field_validator("scheduled_for", mode="after")
    @classmethod
    def _always_utc(cls, v):
        # Timestamps are stored in UTC; some backends hand them back without tzinfo.
        return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


@router.get("/workspaces/{workspace_id}/calendar", response_model=list[CalendarItemOut])
def list_calendar(ctx: WorkspaceContext = Depends(workspace_ctx)):
    items = WorkspaceRepo(ctx.db, CalendarItem, ctx.workspace.id).list()
    return sorted(items, key=lambda i: (i.scheduled_for is None, i.scheduled_for))


@router.get("/workspaces/{workspace_id}/calendar/{item_id}", response_model=CalendarItemOut)
def get_calendar_item(item_id: str, ctx: WorkspaceContext = Depends(workspace_ctx)):
    try:
        iid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Calendar item not found")
    item = WorkspaceRepo(ctx.db, CalendarItem, ctx.workspace.id).get(iid)
    if item is None:
        raise HTTPException(status_code=404, detail="Calendar item not found")
    return item
