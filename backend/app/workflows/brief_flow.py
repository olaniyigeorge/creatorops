"""Editor workflow: brief_for_item (calendar item -> brief -> editor) and brief_followup.

Both are routine, so Medium autonomy proceeds on its own when the guardrails pass and
Low escalates. Emails are sent after the action is committed, at most once: executors
put the email in the action's result, and `_send_once` marks it sent before enqueuing.
"""

import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, ValidationError

from app.agents.comms import CommsAgent
from app.agents.pm import ProjectManagerAgent, clean
from app.comms import briefs as comms
from app.core.config import settings
from app.db.base import utcnow
from app.db.models import Action, Brief, BriefStatus, CalendarItem, Workspace
from app.db.repo import WorkspaceRepo
from app.gate.autonomy import ActionType, ProposedAction
from app.memory.service import workspace_context
from app.schemas.brief import BriefPayload, FollowUpPayload
from app.tasks import dispatch
from app.tasks.runner import register_workflow
from app.workflows.context import (
    Draft,
    Outcome,
    PayloadInvalid,
    WorkflowContext,
    register_executor,
    register_payload_validator,
)

ACTIVE = (BriefStatus.ASSIGNED.value, BriefStatus.IN_PROGRESS.value)
OPEN = (BriefStatus.DRAFT.value, *ACTIVE)  # not yet delivered


class BriefParams(BaseModel):
    calendar_item_id: uuid.UUID
    editor_id: Optional[uuid.UUID] = None
    due_at: Optional[datetime] = None


class FollowUpParams(BaseModel):
    brief_id: uuid.UUID


def get_pm_agent() -> ProjectManagerAgent:  # replaced in tests
    return ProjectManagerAgent()


def get_comms_agent() -> CommsAgent:  # replaced in tests
    return CommsAgent()


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Timestamps are stored in UTC; SQLite hands them back without tzinfo."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------- payload validation


def validate_brief_payload(payload: dict) -> dict:
    try:
        p = BriefPayload(**payload)
        p.body = clean(p.body)  # an admin edit cannot smuggle markup into emails
        return p.model_dump(mode="json")
    except (ValidationError, ValueError) as exc:
        raise PayloadInvalid(str(exc)) from exc


def validate_followup_payload(payload: dict) -> dict:
    try:
        return FollowUpPayload(**payload).model_dump(mode="json")
    except (ValidationError, ValueError) as exc:
        raise PayloadInvalid(str(exc)) from exc


# ---------------------------------------------------------------------- executors


def _email_dict(e) -> dict:
    return asdict(e)


def execute_assign_brief(db, action: Action, payload: dict) -> dict:
    payload = validate_brief_payload(payload)
    ws_id = action.workspace_id
    item = WorkspaceRepo(db, CalendarItem, ws_id).get(uuid.UUID(payload["calendar_item_id"]))
    if item is None:
        raise LookupError("Calendar item not found in this workspace")
    briefs = WorkspaceRepo(db, Brief, ws_id)
    if any(b.status in OPEN for b in briefs.list(calendar_item_id=item.id)):
        raise ValueError("This calendar item already has an open brief")

    editor = None
    if payload["editor_id"]:
        editor = comms.member_user(db, ws_id, uuid.UUID(payload["editor_id"]))
        if editor is None:
            raise ValueError("Editor is not a member of this workspace")
    due = payload["due_at"] and datetime.fromisoformat(payload["due_at"])
    brief = briefs.add(
        calendar_item_id=item.id,
        editor_id=editor.id if editor else None,
        due_at=due,
        status=BriefStatus.ASSIGNED.value if editor else BriefStatus.DRAFT.value,
        body_json=payload["body"],
    )
    item.status = "briefed"
    result = {"brief_id": str(brief.id), "assigned": editor is not None}
    if editor:
        workspace = db.get(Workspace, ws_id)
        title = item.idea_json.get("title", "video")
        result["emails"] = [_email_dict(comms.notify_brief_assigned(db, workspace, brief, title, editor))]
    return result


def execute_followup(db, action: Action, payload: dict) -> dict:
    payload = validate_followup_payload(payload)
    ws_id = action.workspace_id
    brief = WorkspaceRepo(db, Brief, ws_id).get(uuid.UUID(payload["brief_id"]))
    if brief is None:
        raise LookupError("Brief not found in this workspace")
    if brief.status not in ACTIVE:  # delivered while this waited for approval
        return {"skipped": f"brief is {brief.status}"}
    workspace = db.get(Workspace, ws_id)
    if payload["audience"] == "editor":
        editor = comms.member_user(db, ws_id, brief.editor_id) if brief.editor_id else None
        if editor is None:
            return {"skipped": "brief has no editor"}
        emails = [
            comms.notify_followup(
                db, workspace, brief, editor, "brief_followup", payload["subject"], payload["body"]
            )
        ]
    else:
        emails = comms.notify_owners(
            db, workspace, brief, "brief_overdue", payload["subject"], payload["body"]
        )
    brief.followup_count += 1
    brief.last_followup_at = utcnow()
    return {"brief_id": str(brief.id), "audience": payload["audience"], "emails": [_email_dict(e) for e in emails]}


def _send_once(ctx: WorkflowContext, outcome: Outcome) -> None:
    action = ctx.actions.get(outcome.action_id)
    result = dict(action.result_json or {})
    if result.get("emails") and not result.get("emailed"):
        action.result_json = {**result, "emailed": True}
        ctx.db.commit()  # marked before enqueuing: at most once, never a duplicate on re-entry
        for e in result["emails"]:
            dispatch.enqueue_email(e["to"], e["subject"], e["html"])


# --------------------------------------------------------------------- workflows


def _item(db, workspace_id, item_id) -> CalendarItem:
    item = WorkspaceRepo(db, CalendarItem, workspace_id).get(item_id)
    if item is None:
        raise LookupError(f"Calendar item {item_id} not found in this workspace")
    return item


def default_due(item: CalendarItem) -> datetime:
    now = utcnow()
    scheduled = aware(item.scheduled_for)
    if scheduled is None:
        return now + timedelta(days=7)
    return max(scheduled - timedelta(days=settings.BRIEF_LEAD_DAYS), now + timedelta(days=1))


def brief_for_item(ctx: WorkflowContext) -> dict:
    db = ctx.db
    params = BriefParams(**ctx.params)
    item = _item(db, ctx.workspace_id, params.calendar_item_id)
    if params.editor_id and comms.member_user(db, ctx.workspace_id, params.editor_id) is None:
        raise ValueError("Editor is not a member of this workspace")
    due = aware(params.due_at) or default_due(item)
    agent = get_pm_agent()

    def gen(feedback: Optional[str]) -> Draft:
        ws = db.get(Workspace, ctx.workspace_id)
        body = agent.write_brief(workspace_context(db, ws), item.idea_json, due.date().isoformat(), feedback)
        payload = BriefPayload(
            calendar_item_id=str(item.id), editor_id=params.editor_id, due_at=due, body=body
        ).model_dump(mode="json")
        text = "\n".join(
            [body.objective]
            + [f"{s.heading}: {s.notes}" for s in body.outline]
            + body.shot_list
            + [body.editor_notes]
        )
        return Draft(
            ProposedAction(
                type=ActionType.ASSIGN_BRIEF,
                summary=f"Brief for: {item.idea_json.get('title', 'video')}",
                payload=payload,
            ),
            content=text,
        )

    out = ctx.propose("brief", gen)
    if out.status != "executed":
        return {"brief": out.status, "note": out.note, "reason": out.reason}
    _send_once(ctx, out)
    return {"brief": "assigned" if out.result.get("assigned") else "draft", "brief_id": out.result["brief_id"]}


def brief_followup(ctx: WorkflowContext) -> dict:
    db = ctx.db
    params = FollowUpParams(**ctx.params)
    brief = WorkspaceRepo(db, Brief, ctx.workspace_id).get(params.brief_id)
    if brief is None:
        raise LookupError(f"Brief {params.brief_id} not found in this workspace")
    due, now = aware(brief.due_at), utcnow()
    # Re-entry (after an approval, or a crash after sending) must reach the stored step
    # even though the brief has moved on, so these checks only guard a fresh run.
    if not ctx.actions.list(run_id=ctx.run.id, step_key="followup"):
        if brief.status not in ACTIVE or brief.editor_id is None or due is None or due > now:
            return {"followup": "skipped", "reason": "brief is not overdue"}
        if brief.followup_count > settings.BRIEF_MAX_FOLLOWUPS:
            return {"followup": "skipped", "reason": "owner already told"}
    audience = "editor" if brief.followup_count < settings.BRIEF_MAX_FOLLOWUPS else "owner"
    item = _item(db, ctx.workspace_id, brief.calendar_item_id)
    title = item.idea_json.get("title", "video")
    agent = get_comms_agent()

    def gen(feedback: Optional[str]) -> Draft:
        ws = db.get(Workspace, ctx.workspace_id)
        draft = agent.follow_up(
            workspace_context(db, ws), audience, title, due.date().isoformat(),
            max((now - due).days, 0), brief.status, brief.followup_count, feedback,
        )
        return Draft(
            ProposedAction(
                type=ActionType.SEND_STATUS_EMAIL,
                summary=f"{'Follow up with editor' if audience == 'editor' else 'Tell owner brief is overdue'}: {title}",
                payload=FollowUpPayload(
                    brief_id=str(brief.id), audience=audience, subject=draft.subject, body=draft.body
                ).model_dump(mode="json"),
            ),
            content=f"{draft.subject}\n{draft.body}",
        )

    out = ctx.propose("followup", gen)
    if out.status != "executed" or out.result.get("skipped"):
        # Rejected or skipped: do not let the next scan nag again straight away.
        brief = WorkspaceRepo(db, Brief, ctx.workspace_id).get(params.brief_id)
        brief.last_followup_at = utcnow()
        db.commit()
        return {"followup": out.status if out.status != "executed" else "skipped", "note": out.note}
    _send_once(ctx, out)
    return {"followup": "sent", "audience": audience}


register_executor(ActionType.ASSIGN_BRIEF, execute_assign_brief)
register_payload_validator(ActionType.ASSIGN_BRIEF, validate_brief_payload)
register_executor(ActionType.SEND_STATUS_EMAIL, execute_followup)
register_payload_validator(ActionType.SEND_STATUS_EMAIL, validate_followup_payload)
register_workflow("brief_for_item", brief_for_item, BriefParams)
register_workflow("brief_followup", brief_followup, FollowUpParams)
