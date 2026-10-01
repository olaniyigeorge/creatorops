"""WorkflowContext.propose: guardrails -> autonomy -> execute / escalate / block -> resume."""

import pytest

from app.db import models as m
from app.db.repo import WorkspaceRepo
from app.gate.autonomy import ActionType as A, ProposedAction
from app.gate.guardrails import GuardrailVerdict
from app.tasks import dispatch
from app.workflows import context as wfc
from app.workflows.context import Draft, RunPaused, WorkflowContext
from tests.conftest import make_user


@pytest.fixture
def emails(monkeypatch):
    sent = []
    monkeypatch.setattr(dispatch, "enqueue_email", lambda to, subject, html: sent.append((to, subject, html)))
    return sent


@pytest.fixture
def executed(monkeypatch):
    calls = []
    monkeypatch.setattr(
        wfc, "EXECUTORS",
        {t: (lambda db, action, payload, _t=t: calls.append((_t, payload)) or {"done": payload}) for t in A},
    )
    return calls


def setup(db, autonomy="low", **ws_kwargs):
    ws = m.Workspace(name="Acme <b>", autonomy=autonomy, **ws_kwargs)
    db.add(ws)
    db.flush()
    owner = make_user(db, "owner@x.co")
    WorkspaceRepo(db, m.Membership, ws.id).add(user_id=owner.id, role="owner")
    editor = make_user(db, "editor@x.co")
    WorkspaceRepo(db, m.Membership, ws.id).add(user_id=editor.id, role="editor")
    run = WorkspaceRepo(db, m.Run, ws.id).add(workflow="t")
    db.commit()
    return ws, run, owner


def draft(t=A.GENERATE_CREATIVE, content=None, summary="do it", **kw):
    return lambda feedback: Draft(ProposedAction(type=t, summary=summary, payload={"x": 1}, **kw), content)


def test_high_autonomy_executes_immediately(db, executed, emails):
    ws, run, _ = setup(db, "high")
    out = WorkflowContext(db, run).propose("s1", draft())
    assert out.status == "executed" and out.result == {"done": {"x": 1}}
    assert len(executed) == 1 and not emails
    assert db.query(m.Action).one().status == "executed"


def test_low_autonomy_escalates_notifies_owner_only_and_pauses(db, executed, emails):
    ws, run, owner = setup(db, "low")
    with pytest.raises(RunPaused):
        WorkflowContext(db, run).propose("s1", draft(summary="Pick <script>niche</script>"))
    assert not executed  # nothing runs before approval
    action, approval = db.query(m.Action).one(), db.query(m.Approval).one()
    assert action.status == "awaiting_approval" and approval.status == "pending"
    notes = db.query(m.Notification).all()
    assert [n.user_id for n in notes] == [owner.id]  # editor is not notified
    assert notes[0].link == f"/workspaces/{ws.id}/approvals/{approval.id}"
    assert [e[0] for e in emails] == ["owner@x.co"]
    assert "<script>" not in emails[0][2] and "&lt;script&gt;" in emails[0][2]  # escaped
    assert "<b>" not in emails[0][2].split("<b>Acme")[0]  # workspace name escaped too
    assert "Acme &lt;b&gt;" in emails[0][2]


def test_reentry_while_pending_does_not_duplicate(db, executed, emails):
    ws, run, _ = setup(db, "low")
    ctx = WorkflowContext(db, run)
    for _ in range(3):
        with pytest.raises(RunPaused):
            ctx.propose("s1", draft())
    assert db.query(m.Approval).count() == 1 and len(emails) == 1 and db.query(m.Action).count() == 1


def test_generate_is_not_called_again_once_action_exists(db, executed, emails):
    ws, run, _ = setup(db, "low")
    calls = []

    def gen(fb):
        calls.append(fb)
        return draft()(fb)

    for _ in range(2):
        with pytest.raises(RunPaused):
            WorkflowContext(db, run).propose("s1", gen)
    assert len(calls) == 1  # no repeated LLM spend on re-entry


def _approve(db, edited=None, note=None):
    a = db.query(m.Approval).one()
    a.status, a.edited_payload_json, a.decision_note = "approved", edited, note
    db.query(m.Action).one().status = "approved"
    db.commit()


def test_approved_action_executes_once_with_admin_edits(db, executed, emails):
    ws, run, _ = setup(db, "low")
    with pytest.raises(RunPaused):
        WorkflowContext(db, run).propose("s1", draft())
    _approve(db, edited={"x": 99})

    out = WorkflowContext(db, run).propose("s1", draft())
    assert out.status == "executed" and executed == [(A.GENERATE_CREATIVE, {"x": 99})]
    again = WorkflowContext(db, run).propose("s1", draft())
    assert again.status == "executed" and len(executed) == 1  # not re-executed


def test_rejected_action_returns_note_and_never_executes(db, executed, emails):
    ws, run, _ = setup(db, "low")
    with pytest.raises(RunPaused):
        WorkflowContext(db, run).propose("s1", draft())
    a = db.query(m.Approval).one()
    a.status, a.decision_note = "rejected", "too clickbaity"
    db.query(m.Action).one().status = "rejected"
    db.commit()
    out = WorkflowContext(db, run).propose("s1", draft())
    assert out.status == "rejected" and out.note == "too clickbaity" and not executed


def test_guardrail_retry_feeds_feedback_back_to_generator(db, executed, emails):
    ws, run, _ = setup(db, "high")
    scores = iter([GuardrailVerdict(score=0.2, feedback="too salesy"), GuardrailVerdict(score=0.95)])
    feedbacks = []

    def gen(fb):
        feedbacks.append(fb)
        return Draft(ProposedAction(type=A.GENERATE_CREATIVE, summary="t"), content="text")

    out = WorkflowContext(db, run, rate=lambda c, r: next(scores)).propose("s1", gen)
    assert out.status == "executed" and feedbacks == [None, "too salesy"]
    assert db.query(m.Action).one().guardrail_score == 0.95


def test_guardrail_failing_after_retries_escalates(db, executed, emails):
    ws, run, _ = setup(db, "high")
    n = []
    with pytest.raises(RunPaused):
        WorkflowContext(db, run, rate=lambda c, r: GuardrailVerdict(score=0.1)).propose(
            "s1", lambda fb: n.append(fb) or Draft(ProposedAction(type=A.GENERATE_CREATIVE, summary="t"), "x"),
            max_retries=2,
        )
    assert len(n) == 3 and not executed  # initial + 2 retries, then a human decides


def test_guardrail_outage_fails_closed(db, executed, emails):
    ws, run, _ = setup(db, "high")

    def boom(c, r):
        raise TimeoutError("judge down")

    n = []
    with pytest.raises(RunPaused):
        WorkflowContext(db, run, rate=boom).propose(
            "s1", lambda fb: n.append(1) or Draft(ProposedAction(type=A.GENERATE_CREATIVE, summary="t"), "x")
        )
    assert not executed and len(n) == 1  # no pointless regeneration against a dead judge


def test_blocked_video_gen_returns_without_approval(db, executed, emails):
    ws, run, _ = setup(db, "high")  # video_gen_enabled defaults to False
    out = WorkflowContext(db, run).propose("v", draft(A.GENERATE_VIDEO, estimated_cost_usd=3))
    assert out.status == "blocked" and not executed and db.query(m.Approval).count() == 0
    assert WorkflowContext(db, run).propose("v", draft(A.GENERATE_VIDEO)).status == "blocked"


def test_publish_and_video_spend_feed_back_into_the_gate(db, executed, emails):
    ws, run, _ = setup(db, "high", publish_human_floor=0, video_gen_enabled=True, video_budget_usd=10)
    ctx = WorkflowContext(db, run)
    ctx.propose("p", draft(A.PUBLISH_VIDEO))
    ctx.propose("v", draft(A.GENERATE_VIDEO, estimated_cost_usd=4))
    db.refresh(ws)
    assert ws.publishes_so_far == 1 and ws.video_spent_usd == 4
    # remaining budget is now 6: a 7 USD generation is blocked
    assert ctx.propose("v2", draft(A.GENERATE_VIDEO, estimated_cost_usd=7)).status == "blocked"


def test_executor_failure_marks_action_failed_and_stays_failed(db, monkeypatch, emails):
    ws, run, _ = setup(db, "high")

    def bad(db_, action, payload):
        raise RuntimeError("youtube 500")

    monkeypatch.setattr(wfc, "EXECUTORS", {A.GENERATE_CREATIVE: bad})
    with pytest.raises(RuntimeError, match="youtube 500"):
        WorkflowContext(db, run).propose("s1", draft())
    assert db.query(m.Action).one().status == "failed"
    with pytest.raises(RuntimeError, match="previously failed"):
        WorkflowContext(db, run).propose("s1", draft())


def test_concurrent_video_generations_cannot_overspend(db, executed, emails):
    """Both pass the propose-time check (7 <= 10); only one may pass the atomic reservation."""
    ws, run, _ = setup(db, "high", video_gen_enabled=True, video_budget_usd=10)
    run2 = WorkspaceRepo(db, m.Run, ws.id).add(workflow="t")
    db.commit()
    first = WorkflowContext(db, run).propose("v", draft(A.GENERATE_VIDEO, estimated_cost_usd=7))
    assert first.status == "executed"
    # Simulate run2 having decided against a stale snapshot taken before run1 spent:
    ctx2 = WorkflowContext(db, run2)
    action = ctx2.actions.add(
        run_id=run2.id, step_key="v", type="generate_video", summary="s", payload_json={},
        estimated_cost_usd=7, verdict="proceed", status="approved",
    )
    out = ctx2._execute(action, {})
    assert out.status == "blocked" and "exhausted" in out.reason
    db.refresh(ws)
    assert ws.video_spent_usd == 7  # not 14
    assert len(executed) == 1       # the second generation never ran


def test_failed_video_generation_gives_the_budget_back(db, monkeypatch, emails):
    ws, run, _ = setup(db, "high", video_gen_enabled=True, video_budget_usd=10)

    def boom(db_, action, payload):
        raise RuntimeError("veo quota")

    monkeypatch.setattr(wfc, "EXECUTORS", {A.GENERATE_VIDEO: boom})
    with pytest.raises(RuntimeError):
        WorkflowContext(db, run).propose("v", draft(A.GENERATE_VIDEO, estimated_cost_usd=7))
    db.refresh(ws)
    assert ws.video_spent_usd == 0 and db.query(m.Action).one().status == "failed"


def test_side_effect_without_executor_fails_loudly_not_silently(db, monkeypatch, emails):
    ws, run, _ = setup(db, "high", publish_human_floor=0)
    monkeypatch.setattr(wfc, "EXECUTORS", {})
    with pytest.raises(NotImplementedError, match="publish_video"):
        WorkflowContext(db, run).propose("p", draft(A.PUBLISH_VIDEO))
    db.refresh(ws)
    assert db.query(m.Action).one().status == "failed" and ws.publishes_so_far == 0
