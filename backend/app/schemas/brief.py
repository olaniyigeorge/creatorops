"""Pydantic contracts for the editor workflow. LLM output is validated against these."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OutlineSection(BaseModel):
    heading: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=1500)


class BriefDraft(BaseModel):
    """What the Project Manager agent writes for an editor."""

    objective: str = Field(min_length=1, max_length=1000)
    outline: list[OutlineSection] = Field(min_length=1, max_length=12)
    shot_list: list[str] = Field(default_factory=list, max_length=20)
    references: list[str] = Field(default_factory=list, max_length=10)
    deliverables: list[str] = Field(default_factory=list, max_length=10)
    editor_notes: str = Field(default="", max_length=2000)


class BriefPayload(BaseModel):
    """What an approval of ASSIGN_BRIEF executes. Admins may edit the body, editor and deadline."""

    calendar_item_id: str
    editor_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None
    body: BriefDraft

    @field_validator("due_at", mode="after")
    @classmethod
    def _utc(cls, v):
        return v if v is None or v.tzinfo else v.replace(tzinfo=timezone.utc)


class FollowUpDraft(BaseModel):
    """What the Communication agent writes to a late editor (or to the owner)."""

    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)


class FollowUpPayload(BaseModel):
    brief_id: str
    audience: str = Field(pattern="^(editor|owner)$")
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)
