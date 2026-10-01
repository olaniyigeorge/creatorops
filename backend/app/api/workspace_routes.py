from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import WorkspaceContext, current_user, owner_ctx, workspace_ctx
from app.api.schemas import (
    InvitationAccept,
    InvitationCreate,
    InvitationOut,
    MemberOut,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceSettingsUpdate,
    WorkspaceSummary,
)
from app.auth.security import hash_token, new_invitation_token
from app.core.config import settings
from app.db.base import utcnow
from app.db.models import Invitation, Membership, Role, User, Workspace
from app.db.repo import WorkspaceRepo
from app.db.session import get_db

router = APIRouter(tags=["workspaces"])


@router.post("/workspaces", response_model=WorkspaceOut, status_code=201)
def create_workspace(
    body: WorkspaceCreate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ws = Workspace(name=body.name)
    db.add(ws)
    db.flush()
    WorkspaceRepo(db, Membership, ws.id).add(user_id=user.id, role=Role.OWNER.value)
    db.commit()
    return ws


@router.get("/workspaces", response_model=list[WorkspaceSummary])
def list_my_workspaces(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    rows = db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    return [WorkspaceSummary(id=w.id, name=w.name, role=r) for w, r in rows]


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(ctx: WorkspaceContext = Depends(workspace_ctx)):
    return ctx.workspace


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    body: WorkspaceSettingsUpdate, ctx: WorkspaceContext = Depends(owner_ctx)
):
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        setattr(ctx.workspace, key, getattr(value, "value", value))
    ctx.db.commit()
    return ctx.workspace


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(ctx: WorkspaceContext = Depends(workspace_ctx)):
    members = WorkspaceRepo(ctx.db, Membership, ctx.workspace.id).list()
    users = {
        u.id: u
        for u in ctx.db.scalars(
            select(User).where(User.id.in_([m.user_id for m in members]))
        )
    }
    return [
        MemberOut(
            user_id=m.user_id,
            email=users[m.user_id].email,
            name=users[m.user_id].name,
            role=m.role,
        )
        for m in members
    ]


@router.post(
    "/workspaces/{workspace_id}/invitations",
    response_model=InvitationOut,
    status_code=201,
)
def invite(body: InvitationCreate, ctx: WorkspaceContext = Depends(owner_ctx)):
    email = body.email.lower()
    existing = ctx.db.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == ctx.workspace.id, User.email == email)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Already a member")
    token, token_hash = new_invitation_token()
    inv = WorkspaceRepo(ctx.db, Invitation, ctx.workspace.id).add(
        email=email,
        role=body.role,
        token_hash=token_hash,
        invited_by=ctx.user.id,
        expires_at=utcnow() + timedelta(days=settings.INVITATION_TTL_DAYS),
    )
    ctx.db.commit()
    return InvitationOut(
        id=inv.id, email=inv.email, role=inv.role, expires_at=inv.expires_at, token=token
    )


@router.post("/invitations/accept", response_model=WorkspaceSummary)
def accept_invitation(
    body: InvitationAccept,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    # Lookup by token hash is the one sanctioned cross-workspace query: the
    # unguessable token is the credential, and it resolves to a single workspace.
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(body.token)))
    expires = inv.expires_at if inv else None
    if expires is not None and expires.tzinfo is None:  # SQLite drops tzinfo
        expires = expires.replace(tzinfo=utcnow().tzinfo)
    if inv is None or inv.accepted_at is not None or expires < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")
    if inv.email != user.email.lower():
        raise HTTPException(status_code=403, detail="Invitation was sent to a different email")

    WorkspaceRepo(db, Membership, inv.workspace_id).add(user_id=user.id, role=inv.role)
    inv.accepted_at = utcnow()
    db.commit()
    ws = db.get(Workspace, inv.workspace_id)
    return WorkspaceSummary(id=ws.id, name=ws.name, role=inv.role)
