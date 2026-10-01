from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import WorkspaceContext, owner_ctx, workspace_ctx
from app.schemas.profile import ChannelProfile

router = APIRouter(tags=["onboarding"])

# Keys under brand_json that the agents (not onboarding) own; resubmitting the
# questionnaire must not wipe them.
_AGENT_KEYS = ("niche",)


@router.put("/workspaces/{workspace_id}/onboarding", response_model=ChannelProfile)
def submit_onboarding(profile: ChannelProfile, ctx: WorkspaceContext = Depends(owner_ctx)):
    ws = ctx.workspace
    kept = {k: v for k, v in (ws.brand_json or {}).items() if k in _AGENT_KEYS}
    ws.brand_json = {**kept, **profile.model_dump(), "onboarded": True}
    # The guardrail rubric is derived from the answers, so what the owner said about
    # tone and forbidden topics is what every generated asset is judged against.
    ws.rubric_json = {
        "brand_voice": f"{profile.tone}. {profile.brand_voice}".strip(),
        "banned_topics": profile.banned_topics,
        "extra_rules": profile.extra_rules,
    }
    ctx.db.commit()
    return profile


@router.get("/workspaces/{workspace_id}/onboarding", response_model=ChannelProfile)
def get_onboarding(ctx: WorkspaceContext = Depends(workspace_ctx)):
    brand = ctx.workspace.brand_json or {}
    if not brand.get("onboarded"):
        raise HTTPException(status_code=404, detail="Onboarding not completed")
    return ChannelProfile(**{k: v for k, v in brand.items() if k in ChannelProfile.model_fields})
