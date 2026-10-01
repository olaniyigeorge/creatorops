import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, created_at, pk
from app.gate.autonomy import AutonomyLevel, WorkspacePolicy


class Role(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"  # used from M2
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    google_sub: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = created_at()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at()

    # Autonomy and safety policy (consumed by app.gate.autonomy)
    autonomy: Mapped[str] = mapped_column(String(16), default=AutonomyLevel.LOW.value)
    guardrail_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    publish_human_floor: Mapped[int] = mapped_column(Integer, default=3)
    publishes_so_far: Mapped[int] = mapped_column(Integer, default=0)
    video_gen_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    video_budget_usd: Mapped[float] = mapped_column(Float, default=0.0)
    video_spent_usd: Mapped[float] = mapped_column(Float, default=0.0)

    brand_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rubric_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    def to_policy(self) -> WorkspacePolicy:
        return WorkspacePolicy(
            autonomy=AutonomyLevel(self.autonomy),
            guardrail_threshold=self.guardrail_threshold,
            publish_human_floor=self.publish_human_floor,
            publishes_so_far=self.publishes_so_far,
            video_gen_enabled=self.video_gen_enabled,
            video_budget_usd_remaining=max(
                0.0, self.video_budget_usd - self.video_spent_usd
            ),
        )


class Membership(TenantMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id"),)

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = created_at()


class Invitation(TenantMixin, Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 hex
    invited_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Channel(TenantMixin, Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = pk()
    youtube_channel_id: Mapped[Optional[str]] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200), default="")
    oauth_token_ref: Mapped[Optional[str]] = mapped_column(Text)  # encrypted, Phase 2
    created_at: Mapped[datetime] = created_at()


class Run(TenantMixin, Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = pk()
    workflow: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default=RunStatus.PENDING.value)
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    video_job_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Action(TenantMixin, Base):
    __tablename__ = "actions"

    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    guardrail_score: Mapped[Optional[float]] = mapped_column(Float)
    verdict: Mapped[Optional[str]] = mapped_column(String(16))
    created_at: Mapped[datetime] = created_at()


class Approval(TenantMixin, Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = pk()
    action_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("actions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id"))
    decision_note: Mapped[Optional[str]] = mapped_column(Text)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class CalendarItem(TenantMixin, Base):
    __tablename__ = "calendar_items"

    id: Mapped[uuid.UUID] = pk()
    idea_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    scheduled_for: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    created_at: Mapped[datetime] = created_at()


class Brief(TenantMixin, Base):
    __tablename__ = "briefs"

    id: Mapped[uuid.UUID] = pk()
    calendar_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("calendar_items.id", ondelete="CASCADE"), index=True
    )
    editor_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id"))
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    body_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = created_at()


class Asset(TenantMixin, Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[str] = mapped_column(String(24))  # thumbnail | video | image
    public_id: Mapped[str] = mapped_column(String(512))  # Cloudinary public_id
    source: Mapped[str] = mapped_column(String(16))  # ai | editor
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = created_at()


class MemoryItem(TenantMixin, Base):
    __tablename__ = "memory_items"

    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[str] = mapped_column(String(32))  # brand_guideline | preference | decision | performance_insight
    text: Mapped[str] = mapped_column(Text)
    source_approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("approvals.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = created_at()
