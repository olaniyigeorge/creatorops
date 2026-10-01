"""strategy_onboarding: niche selection, then the 30-day content calendar.

Both steps are high-stakes (Medium autonomy escalates them). If the admin rejects a
proposal, their note has already been written to workspace memory by the approval
route, so the next attempt's prompt contains it; the workflow just tries again,
up to MAX_ATTEMPTS.
"""

from typing import Optional

from pydantic import ValidationError

from app.agents.strategy import ESTIMATES_NOTE, StrategyAgent, rank_options
from app.core.config import settings
from app.db.models import CalendarItem, Workspace
from app.db.repo import WorkspaceRepo
from app.gate.autonomy import ActionType, ProposedAction
from app.integrations import youtube
from app.memory.service import add_memory, workspace_context
from app.schemas.profile import ChannelProfile
from app.schemas.strategy import CalendarPayload, NichePayload
from app.tasks.runner import register_workflow
from app.workflows.context import (
    Draft,
    PayloadInvalid,
    WorkflowContext,
    register_executor,
    register_payload_validator,
)

MAX_ATTEMPTS = 3


# Indirection points that tests replace.
def get_agent() -> StrategyAgent:
    return StrategyAgent()


def fetch_signals(profile: ChannelProfile) -> youtube.MarketSignals:
    return youtube.collect_signals_sync(
        settings.YOUTUBE_API_KEY, profile.region_code, profile.competitors
    )


# ------------------------------------------------------------- payload validation


def validate_niche_payload(payload: dict) -> dict:
    try:
        p = NichePayload(**payload)
    except ValidationError as exc:
        raise PayloadInvalid(str(exc)) from exc
    if p.selected not in {o.get("name") for o in p.options}:
        raise PayloadInvalid(f"'{p.selected}' is not one of the proposed options")
    return p.model_dump()


def validate_calendar_payload(payload: dict) -> dict:
    try:
        return CalendarPayload(**payload).model_dump(mode="json")
    except ValidationError as exc:
        raise PayloadInvalid(str(exc)) from exc


# ---------------------------------------------------------------------- executors


def apply_niche(db, action, payload: dict) -> dict:
    p = validate_niche_payload(payload)
    chosen = next(o for o in p["options"] if o["name"] == p["selected"])
    ws = db.get(Workspace, action.workspace_id)
    ws.brand_json = {
        **(ws.brand_json or {}),
        "niche": {
            "name": chosen["name"],
            "rationale": chosen.get("rationale", ""),
            "keywords": chosen.get("keywords", []),
            "score": chosen.get("score"),
        },
    }
    if action.verdict == "proceed":  # no human decision exists, so record it here
        add_memory(db, ws.id, "decision", f"Niche selected automatically: {chosen['name']}")
    return {"niche": chosen["name"]}


def apply_calendar(db, action, payload: dict) -> dict:
    p = validate_calendar_payload(payload)
    repo = WorkspaceRepo(db, CalendarItem, action.workspace_id)
    # A new plan replaces the old *unstarted* one; items already in progress are kept.
    for old in repo.list(status="planned"):
        repo.delete(old.id)
    from datetime import datetime

    for item in p["items"]:
        repo.add(
            idea_json={k: item[k] for k in ("title", "hook", "keywords", "format")},
            scheduled_for=datetime.fromisoformat(item["scheduled_for"]),
            status="planned",
        )
    return {"created": len(p["items"]), "niche": p["niche"]}


# --------------------------------------------------------------------- the workflow


def strategy_onboarding(ctx: WorkflowContext) -> dict:
    db = ctx.db
    ws = db.get(Workspace, ctx.workspace_id)
    if not (ws.brand_json or {}).get("onboarded"):
        raise ValueError("Complete onboarding before running the strategy workflow")
    profile = ChannelProfile(
        **{k: v for k, v in ws.brand_json.items() if k in ChannelProfile.model_fields}
    )
    agent = get_agent()
    memo: dict = {}

    def signals() -> youtube.MarketSignals:  # fetched at most once per execution
        if "s" not in memo:
            memo["s"] = fetch_signals(profile)
        return memo["s"]

    def context() -> str:
        return workspace_context(db, db.get(Workspace, ctx.workspace_id))

    # ---- step 1: niche
    niche: Optional[str] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):

        def gen_niche(feedback: Optional[str]) -> Draft:
            sig = signals()
            ranked = rank_options(
                agent.propose_niches(context(), sig.summary(), profile.goal, feedback).options,
                profile.goal,
            )
            payload = NichePayload(
                selected=ranked[0]["name"],
                options=ranked,
                evidence=sig.summary(),
                estimates_note=ESTIMATES_NOTE,
            ).model_dump()
            text = "; ".join(f"{o['name']}: {o['rationale']}" for o in ranked)
            return Draft(
                ProposedAction(
                    type=ActionType.SET_STRATEGY,
                    summary=f"Select niche: {ranked[0]['name']}",
                    payload=payload,
                ),
                content=text,
            )

        out = ctx.propose(f"niche:{attempt}", gen_niche)
        if out.status == "executed":
            niche = out.result["niche"]
            break
        if out.status == "blocked":
            return {"stopped": "blocked", "step": "niche", "reason": out.reason}
    if niche is None:
        return {"stopped": "niche_rejected", "attempts": MAX_ATTEMPTS}

    # ---- step 2: calendar
    for attempt in range(1, MAX_ATTEMPTS + 1):

        def gen_calendar(feedback: Optional[str]) -> Draft:
            entries = agent.propose_calendar(
                context(), signals().summary(), niche, profile.videos_per_week, feedback
            )
            payload = CalendarPayload(niche=niche, items=entries).model_dump(mode="json")
            text = "; ".join(f"{e.title} - {e.hook}" for e in entries)
            return Draft(
                ProposedAction(
                    type=ActionType.SET_CALENDAR,
                    summary=f"Plan {len(entries)} videos for '{niche}'",
                    payload=payload,
                ),
                content=text,
            )

        out = ctx.propose(f"calendar:{attempt}", gen_calendar)
        if out.status == "executed":
            return {"niche": niche, "calendar_items": out.result["created"]}
        if out.status == "blocked":
            return {"stopped": "blocked", "step": "calendar", "reason": out.reason}
    return {"stopped": "calendar_rejected", "niche": niche, "attempts": MAX_ATTEMPTS}


register_executor(ActionType.SET_STRATEGY, apply_niche)
register_executor(ActionType.SET_CALENDAR, apply_calendar)
register_payload_validator(ActionType.SET_STRATEGY, validate_niche_payload)
register_payload_validator(ActionType.SET_CALENDAR, validate_calendar_payload)
register_workflow("strategy_onboarding", strategy_onboarding)
