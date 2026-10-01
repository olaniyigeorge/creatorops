"""creative_for_item: titles, description, tags and thumbnail for one calendar item.

Routine, so Medium autonomy proceeds on its own when the guardrails pass; Low
escalates. The optional thumbnail image step runs only when image generation is on.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ValidationError

from app.agents.creative import CreativeAgent, enforce_limits
from app.core.config import settings
from app.db.models import Asset, CalendarItem, Workspace
from app.db.repo import WorkspaceRepo
from app.gate.autonomy import ActionType, ProposedAction
from app.image.base import get_image_provider
from app.integrations.storage import get_asset_store
from app.memory.service import workspace_context
from app.schemas.strategy import CreativePackage, CreativePayload, ThumbnailPayload
from app.tasks.runner import register_workflow
from app.workflows.context import (
    Draft,
    PayloadInvalid,
    WorkflowContext,
    register_executor,
    register_payload_validator,
)


class CreativeParams(BaseModel):
    calendar_item_id: uuid.UUID


def get_agent() -> CreativeAgent:  # replaced in tests
    return CreativeAgent()


# ------------------------------------------------------------- payload validation


def validate_creative_action_payload(payload: dict) -> dict:
    try:
        if payload.get("kind") == "thumbnail":
            return ThumbnailPayload(**payload).model_dump(mode="json")
        p = CreativePayload(**payload)
        p.package = enforce_limits(p.package)  # an admin edit cannot break YouTube's limits
        return p.model_dump(mode="json")
    except (ValidationError, ValueError) as exc:
        raise PayloadInvalid(str(exc)) from exc


# ---------------------------------------------------------------------- executors


def _item(db, workspace_id, item_id: str) -> CalendarItem:
    item = WorkspaceRepo(db, CalendarItem, workspace_id).get(uuid.UUID(item_id))
    if item is None:
        raise LookupError(f"Calendar item {item_id} not found in this workspace")
    return item


def execute_creative(db, action, payload: dict) -> dict:
    payload = validate_creative_action_payload(payload)
    item = _item(db, action.workspace_id, payload["calendar_item_id"])
    if payload["kind"] == "thumbnail":
        data = get_image_provider().generate(payload["prompt"])
        stored = get_asset_store().upload_bytes(data, action.workspace_id, "thumbnail")
        asset = WorkspaceRepo(db, Asset, action.workspace_id).add(
            kind="thumbnail",
            public_id=stored.public_id,
            source="ai",
            metadata_json={"calendar_item_id": str(item.id), "prompt": payload["prompt"]},
        )
        item.idea_json = {**item.idea_json, "thumbnail_asset_id": str(asset.id)}
        return {"asset_id": str(asset.id), "public_id": stored.public_id}

    pkg = payload["package"]
    item.idea_json = {**item.idea_json, "creative": pkg}
    item.status = "creative_ready"
    return {"calendar_item_id": str(item.id), "title": pkg["titles"][0]["title"]}


# --------------------------------------------------------------------- the workflow


def creative_for_item(ctx: WorkflowContext) -> dict:
    db = ctx.db
    params = CreativeParams(**ctx.params)
    item = _item(db, ctx.workspace_id, str(params.calendar_item_id))
    agent = get_agent()

    def gen_creative(feedback: Optional[str]) -> Draft:
        ws = db.get(Workspace, ctx.workspace_id)
        pkg = agent.generate(workspace_context(db, ws), item.idea_json, feedback)
        payload = CreativePayload(calendar_item_id=str(item.id), package=pkg).model_dump(mode="json")
        content = "\n".join(
            [t.title for t in pkg.titles] + [pkg.description, ", ".join(pkg.tags)]
        )
        return Draft(
            ProposedAction(
                type=ActionType.GENERATE_CREATIVE,
                summary=f"Creative for: {item.idea_json.get('title', 'video')}",
                payload=payload,
            ),
            content=content,
        )

    out = ctx.propose("creative", gen_creative)
    if out.status != "executed":
        return {"creative": out.status, "note": out.note, "reason": out.reason}
    result = {"creative": "ready", "title": out.result["title"]}

    if settings.IMAGE_GEN_ENABLED:
        db.refresh(item)
        concepts = (item.idea_json.get("creative") or {}).get("thumbnail_concepts") or []
        if concepts:
            thumb = ctx.propose(
                "thumbnail",
                lambda fb: Draft(
                    ProposedAction(
                        type=ActionType.GENERATE_CREATIVE,
                        summary=f"Thumbnail for: {item.idea_json.get('title', 'video')}",
                        payload=ThumbnailPayload(
                            calendar_item_id=str(item.id), prompt=concepts[0]
                        ).model_dump(mode="json"),
                    ),
                    content=concepts[0],
                ),
            )
            result["thumbnail"] = thumb.status
    return result


register_executor(ActionType.GENERATE_CREATIVE, execute_creative)
register_payload_validator(ActionType.GENERATE_CREATIVE, validate_creative_action_payload)
register_workflow("creative_for_item", creative_for_item, CreativeParams)
