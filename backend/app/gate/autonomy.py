"""Autonomy policy: decides whether an agent action runs or escalates to the admin.

Pure logic, no I/O, so it is exhaustively unit-testable. The guardrail verdict
(`guardrails.py`) is an input; this module only applies the admin's trust setting.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AutonomyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionType(str, Enum):
    RESEARCH = "research"
    GENERATE_CREATIVE = "generate_creative"  # titles, descriptions, thumbnails
    SEND_STATUS_EMAIL = "send_status_email"
    ASSIGN_BRIEF = "assign_brief"
    SET_STRATEGY = "set_strategy"  # niche / strategy selection
    SET_CALENDAR = "set_calendar"
    PUBLISH_VIDEO = "publish_video"
    GENERATE_VIDEO = "generate_video"  # AI video gen (Veo etc.): costly, optional


class Stakes(str, Enum):
    ROUTINE = "routine"
    HIGH = "high"


# Which action types are high-stakes under Medium autonomy.
ACTION_STAKES = {
    ActionType.SET_STRATEGY: Stakes.HIGH,
    ActionType.SET_CALENDAR: Stakes.HIGH,
    ActionType.PUBLISH_VIDEO: Stakes.HIGH,
    ActionType.GENERATE_VIDEO: Stakes.HIGH,
}


class ProposedAction(BaseModel):
    type: ActionType
    summary: str
    payload: dict = Field(default_factory=dict)
    estimated_cost_usd: Optional[float] = None


class WorkspacePolicy(BaseModel):
    autonomy: AutonomyLevel = AutonomyLevel.LOW
    guardrail_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    # First N publishes always need a human, even at High autonomy.
    publish_human_floor: int = 3
    publishes_so_far: int = 0
    # AI video gen spends real money: hard budget, and admin-triggered below High.
    video_gen_enabled: bool = False
    video_budget_usd_remaining: float = 0.0


class Verdict(str, Enum):
    PROCEED = "proceed"
    ESCALATE = "escalate"
    RETRY = "retry"  # guardrail failed; regenerate with feedback
    BLOCKED = "blocked"  # not allowed at all (feature disabled, over budget)


class GateDecision(BaseModel):
    verdict: Verdict
    reason: str


def decide(
    action: ProposedAction,
    policy: WorkspacePolicy,
    guardrail_score: float,
    retries_left: int = 0,
) -> GateDecision:
    # Hard blocks first: these never depend on trust level.
    if action.type is ActionType.GENERATE_VIDEO:
        if not policy.video_gen_enabled:
            return GateDecision(verdict=Verdict.BLOCKED, reason="Video generation is disabled for this workspace")
        cost = action.estimated_cost_usd or 0.0
        if cost > policy.video_budget_usd_remaining:
            return GateDecision(verdict=Verdict.BLOCKED, reason="Estimated cost exceeds remaining video budget")

    if guardrail_score < policy.guardrail_threshold:
        if retries_left > 0:
            return GateDecision(verdict=Verdict.RETRY, reason=f"Guardrail score {guardrail_score:.2f} below threshold")
        return GateDecision(verdict=Verdict.ESCALATE, reason="Guardrail failed after retries")

    if action.type is ActionType.PUBLISH_VIDEO and policy.publishes_so_far < policy.publish_human_floor:
        return GateDecision(verdict=Verdict.ESCALATE, reason="Publish human-approval floor not yet reached")

    if action.type is ActionType.GENERATE_VIDEO and policy.autonomy is not AutonomyLevel.HIGH:
        return GateDecision(verdict=Verdict.ESCALATE, reason="Admin must trigger AI video generation")

    if policy.autonomy is AutonomyLevel.LOW:
        return GateDecision(verdict=Verdict.ESCALATE, reason="Low autonomy: all actions need approval")

    if policy.autonomy is AutonomyLevel.MEDIUM:
        if ACTION_STAKES.get(action.type, Stakes.ROUTINE) is Stakes.HIGH:
            return GateDecision(verdict=Verdict.ESCALATE, reason="High-stakes action under Medium autonomy")
        return GateDecision(verdict=Verdict.PROCEED, reason="Routine action under Medium autonomy")

    return GateDecision(verdict=Verdict.PROCEED, reason="High autonomy")
