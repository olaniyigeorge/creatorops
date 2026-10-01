import pytest

from app.gate.autonomy import (
    ActionType as A,
    AutonomyLevel as L,
    ProposedAction,
    Verdict as V,
    WorkspacePolicy,
    decide,
)


def act(t, cost=None):
    return ProposedAction(type=t, summary="x", estimated_cost_usd=cost)


def pol(level, **kw):
    return WorkspacePolicy(autonomy=level, publish_human_floor=0, **kw)


@pytest.mark.parametrize("t", list(A))
def test_low_escalates_everything_except_blocked(t):
    p = pol(L.LOW, video_gen_enabled=True, video_budget_usd_remaining=100)
    assert decide(act(t), p, 1.0).verdict is V.ESCALATE


def test_medium_routine_proceeds_high_stakes_escalates():
    p = pol(L.MEDIUM)
    assert decide(act(A.GENERATE_CREATIVE), p, 1.0).verdict is V.PROCEED
    for t in (A.SET_STRATEGY, A.SET_CALENDAR, A.PUBLISH_VIDEO):
        assert decide(act(t), p, 1.0).verdict is V.ESCALATE


def test_high_proceeds():
    assert decide(act(A.SET_CALENDAR), pol(L.HIGH), 1.0).verdict is V.PROCEED


def test_publish_floor_applies_even_at_high():
    p = WorkspacePolicy(autonomy=L.HIGH, publish_human_floor=3, publishes_so_far=2)
    assert decide(act(A.PUBLISH_VIDEO), p, 1.0).verdict is V.ESCALATE
    p.publishes_so_far = 3
    assert decide(act(A.PUBLISH_VIDEO), p, 1.0).verdict is V.PROCEED


def test_guardrail_retry_then_escalate():
    p = pol(L.HIGH)
    assert decide(act(A.GENERATE_CREATIVE), p, 0.2, retries_left=2).verdict is V.RETRY
    assert decide(act(A.GENERATE_CREATIVE), p, 0.2, retries_left=0).verdict is V.ESCALATE


def test_video_gen_blocked_when_disabled_or_over_budget():
    assert decide(act(A.GENERATE_VIDEO, 1), pol(L.HIGH), 1.0).verdict is V.BLOCKED
    p = pol(L.HIGH, video_gen_enabled=True, video_budget_usd_remaining=5)
    assert decide(act(A.GENERATE_VIDEO, 10), p, 1.0).verdict is V.BLOCKED
    assert decide(act(A.GENERATE_VIDEO, 3), p, 1.0).verdict is V.PROCEED


def test_video_gen_needs_admin_below_high():
    p = pol(L.MEDIUM, video_gen_enabled=True, video_budget_usd_remaining=100)
    assert decide(act(A.GENERATE_VIDEO, 3), p, 1.0).verdict is V.ESCALATE
