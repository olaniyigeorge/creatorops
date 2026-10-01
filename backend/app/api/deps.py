import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import decode_session_token
from app.core.config import settings
from app.db.models import Membership, Role, User, Workspace
from app.db.session import get_db


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    user_id = decode_session_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@dataclass
class WorkspaceContext:
    user: User
    workspace: Workspace
    membership: Membership
    db: Session

    @property
    def is_owner(self) -> bool:
        return self.membership.role == Role.OWNER.value


def workspace_ctx(
    workspace_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> WorkspaceContext:
    membership = db.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user.id
        )
    )
    # 404, not 403: do not reveal that a workspace exists to non-members.
    if membership is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace = db.get(Workspace, workspace_id)
    return WorkspaceContext(user=user, workspace=workspace, membership=membership, db=db)


def owner_ctx(ctx: WorkspaceContext = Depends(workspace_ctx)) -> WorkspaceContext:
    if not ctx.is_owner:
        raise HTTPException(status_code=403, detail="Owner role required")
    return ctx
