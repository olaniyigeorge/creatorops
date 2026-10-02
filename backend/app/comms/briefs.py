"""Editor-workflow notices: in-app notification plus the email to send.

Emails link to the in-app brief page. Everything model-written is HTML-escaped.
"""

import html
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.comms.notify import Email
from app.core.config import settings
from app.db.models import Brief, Membership, Notification, Role, User, Workspace
from app.db.repo import WorkspaceRepo


def _link(workspace: Workspace, brief: Brief) -> str:
    return f"/workspaces/{workspace.id}/briefs/{brief.id}"


def _email(to: str, subject: str, paragraphs: list[str], link: str, cta: str) -> Email:
    body = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs if p)
    return Email(
        to=to,
        subject=subject,
        html=f'{body}<p><a href="{html.escape(settings.CLIENT_DOMAIN + link)}">{html.escape(cta)}</a></p>',
    )


def notify_brief_assigned(
    db: Session, workspace: Workspace, brief: Brief, title: str, editor: User
) -> Email:
    link = _link(workspace, brief)
    subject = f"New brief: {title}"[:300]
    due = brief.due_at.strftime("%Y-%m-%d") if brief.due_at else "no deadline set"
    WorkspaceRepo(db, Notification, workspace.id).add(
        user_id=editor.id, kind="brief_assigned", title=subject, body=f"Due: {due}", link=link
    )
    return _email(
        editor.email,
        subject,
        [f"You have a new editing brief in {workspace.name}.", f"Video: {title}", f"Due: {due}"],
        link,
        "Open the brief",
    )


def notify_followup(
    db: Session,
    workspace: Workspace,
    brief: Brief,
    recipient: User,
    kind: str,
    subject: str,
    body: str,
) -> Email:
    link = _link(workspace, brief)
    WorkspaceRepo(db, Notification, workspace.id).add(
        user_id=recipient.id, kind=kind, title=subject[:300], body=body[:2000], link=link
    )
    return _email(recipient.email, subject, body.split("\n"), link, "Open the brief")


def notify_owners(
    db: Session, workspace: Workspace, brief: Brief, kind: str, title: str, body: str
) -> list[Email]:
    link = _link(workspace, brief)
    emails = []
    for owner in owners_of(db, workspace.id):
        WorkspaceRepo(db, Notification, workspace.id).add(
            user_id=owner.id, kind=kind, title=title[:300], body=body, link=link
        )
        emails.append(_email(owner.email, title, [body], link, "Open the brief"))
    return emails


def owners_of(db: Session, workspace_id) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.workspace_id == workspace_id,
                Membership.role == Role.OWNER.value,
            )
        )
    )


def member_user(db: Session, workspace_id, user_id) -> Optional[User]:
    """The user, but only if they belong to this workspace."""
    membership = next(iter(WorkspaceRepo(db, Membership, workspace_id).list(user_id=user_id)), None)
    return db.get(User, membership.user_id) if membership else None
