import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.gate.autonomy import AutonomyLevel


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    name: str


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceSettingsUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    autonomy: Optional[AutonomyLevel] = None
    guardrail_threshold: Optional[float] = Field(default=None, ge=0, le=1)
    publish_human_floor: Optional[int] = Field(default=None, ge=0)
    video_gen_enabled: Optional[bool] = None
    video_budget_usd: Optional[float] = Field(default=None, ge=0)
    brand_json: Optional[dict[str, Any]] = None
    rubric_json: Optional[dict[str, Any]] = None


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    autonomy: str
    guardrail_threshold: float
    publish_human_floor: int
    video_gen_enabled: bool
    video_budget_usd: float
    video_spent_usd: float
    brand_json: dict[str, Any]
    rubric_json: dict[str, Any]


class WorkspaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    role: str


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: str


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Literal["editor"] = "editor"  # ownership transfer is a separate, later feature


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    token: str  # shown once; emailed in M2


class InvitationAccept(BaseModel):
    token: str
