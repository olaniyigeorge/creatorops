"""Communication Agent (M2 slice): escalation notices to workspace owners.

Creates in-app notifications and returns the emails to send. Emails link to the
in-app approval page, never to a one-click approve/reject URL: mail scanners
prefetch links, and approving a publish must be a deliberate, logged-in act.
"""

import html
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Action, Approval, Membership, Notification, Role, User, Workspace
from app.db.repo import WorkspaceRepo


@dataclass
class Email:
    to: str
    subject: str
    html: str


def notify_approval_needed(
    db: Session, workspace: Workspace, action: Action, approval: Approval
) -> list[Email]:
    link = f"/workspaces/{workspace.id}/approvals/{approval.id}"
    title = f"Approval needed: {action.summary}"[:300]
    owners = list(
        db.scalars(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(
                Membership.workspace_id == workspace.id,
                Membership.role == Role.OWNER.value,
            )
        )
    )
    notifications = WorkspaceRepo(db, Notification, workspace.id)
    emails = []
    for owner in owners:
        notifications.add(
            user_id=owner.id,
            kind="approval_needed",
            title=title,
            body=action.gate_reason or "",
            link=link,
        )
        # Agent-generated text is untrusted: escape before putting it in HTML.
        emails.append(
            Email(
                to=owner.email,
                subject=title,
                html=(
                    f"<p>An action in <b>{html.escape(workspace.name)}</b> needs your approval.</p>"
                    f"<p><b>{html.escape(action.summary)}</b></p>"
                    f"<p>Why you are being asked: {html.escape(action.gate_reason or '')}</p>"
                    f'<p><a href="{html.escape(settings.CLIENT_DOMAIN + link)}">Review and decide</a></p>'
                ),
            )
        )
    return emails
