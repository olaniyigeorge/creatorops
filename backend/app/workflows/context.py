"""Gate execution for workflows.

Workflows are re-entrant functions. Every side effect goes through `ctx.propose`,
which is keyed by `step_key`:

  first call      guardrails -> autonomy decision -> run / escalate / block
  after approval  the stored action is executed (with any admin edits)
  re-entry        completed steps return their stored outcome without re-running

Escalation raises `RunPaused`; the runner parks the run until an admin decides,
then re-enters the workflow, which flows past the decided step.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.comms.notify import notify_approval_needed
from app.db.models import Action, ActionStatus, Approval, Run, Workspace
from app.db.repo import WorkspaceRepo
from app.gate.autonomy import ActionType, ProposedAction, Verdict, decide
from app.gate import guardrails
from app.gate.guardrails import GuardrailVerdict, Rubric
from app.tasks import dispatch

logger = logging.getLogger(__name__)

# Executors perform the real side effect. Registered by the module that owns it
# (publishing, video, ...). Signature: (db, action, payload) -> result dict.
Executor = Callable[[Session, Action, dict], dict]
EXECUTORS: dict[ActionType, Executor] = {}


# Actions with real-world effect must have an executor. Without one the step fails
# loudly instead of being recorded as "executed" when nothing happened.
REQUIRES_EXECUTOR = {ActionType.PUBLISH_VIDEO, ActionType.GENERATE_VIDEO}


# Validators check (and normalise) a proposal payload. They run when an admin edits a
# proposal before approving it, and again inside executors (defence in depth).
PayloadValidator = Callable[[dict], dict]
PAYLOAD_VALIDATORS: dict[ActionType, PayloadValidator] = {}


class PayloadInvalid(ValueError):
    pass


def register_payload_validator(action_type: ActionType, fn: PayloadValidator) -> None:
    PAYLOAD_VALIDATORS[action_type] = fn


def validate_payload(action_type: ActionType, payload: dict) -> dict:
    validator = PAYLOAD_VALIDATORS.get(action_type)
    return validator(payload) if validator else payload


def register_executor(action_type: ActionType, fn: Executor) -> None:
    EXECUTORS[action_type] = fn


# PROCEED is recorded as APPROVED ("approved by policy") and becomes EXECUTED on success.
_INITIAL_STATUS = {
    Verdict.PROCEED: ActionStatus.APPROVED,
    Verdict.ESCALATE: ActionStatus.AWAITING_APPROVAL,
    Verdict.BLOCKED: ActionStatus.BLOCKED,
}


class RunPaused(Exception):
    def __init__(self, approval_id: uuid.UUID):
        super().__init__(f"Waiting for approval {approval_id}")
        self.approval_id = approval_id


@dataclass
class Draft:
    action: ProposedAction
    content: Optional[str] = None  # text rated by the guardrails; None skips rating


class Outcome(BaseModel):
    status: Literal["executed", "rejected", "blocked"]
    action_id: uuid.UUID
    result: dict[str, Any] = {}
    note: Optional[str] = None  # admin's note when rejected: feed it back to the agent
    reason: str = ""


class WorkflowContext:
    def __init__(
        self,
        db: Session,
        run: Run,
        rate: Optional[Callable[[str, Rubric], GuardrailVerdict]] = None,
    ):
        self.db = db
        self.run = run
        # Resolved at call time so tests (and future judge swaps) can replace the judge.
        self.rate = rate or (lambda content, rubric: guardrails.rate(content, rubric))
        self.workspace_id = run.workspace_id
        self.params: dict = dict(run.params_json or {})
        self.actions = WorkspaceRepo(db, Action, run.workspace_id)

    # ------------------------------------------------------------------ public

    def propose(
        self,
        step_key: str,
        generate: Callable[[Optional[str]], Draft],
        max_retries: int = 2,
    ) -> Outcome:
        existing = next(
            iter(self.actions.list(run_id=self.run.id, step_key=step_key)), None
        )
        if existing is not None:
            return self._resume(existing)

        workspace = self.db.get(Workspace, self.workspace_id)
        policy = workspace.to_policy()
        rubric = Rubric(**(workspace.rubric_json or {}))

        feedback: Optional[str] = None
        for attempt in range(max_retries + 1):
            draft = generate(feedback)
            verdict, guardrail_failed = self._score(draft, rubric)
            retries_left = 0 if guardrail_failed else max_retries - attempt
            decision = decide(draft.action, policy, verdict.score, retries_left)
            if decision.verdict is not Verdict.RETRY:
                break
            feedback = verdict.feedback or "; ".join(verdict.violations) or None

        action = self.actions.add(
            run_id=self.run.id,
            step_key=step_key,
            type=draft.action.type.value,
            summary=draft.action.summary,
            payload_json=draft.action.payload,
            estimated_cost_usd=draft.action.estimated_cost_usd,
            guardrail_score=verdict.score,
            guardrail_feedback=verdict.feedback or None,
            verdict=decision.verdict.value,
            gate_reason=decision.reason,
            status=_INITIAL_STATUS[decision.verdict].value,
        )
        # The gate's decision is an audit record: durable before any side effect,
        # so an executor crash cannot erase it (or make a retry re-run `generate`).
        self.db.commit()

        if decision.verdict is Verdict.PROCEED:
            return self._execute(action, action.payload_json)
        if decision.verdict is Verdict.BLOCKED:
            self.db.commit()
            return Outcome(
                status="blocked", action_id=action.id, reason=decision.reason
            )
        return self._escalate(workspace, action)

    # ---------------------------------------------------------------- internals

    def _score(self, draft: Draft, rubric: Rubric) -> tuple[GuardrailVerdict, bool]:
        if draft.content is None:
            return GuardrailVerdict(score=1.0), False
        try:
            return self.rate(draft.content, rubric), False
        except Exception:
            # Fail closed: an unavailable judge must never wave content through.
            logger.exception("Guardrail judge failed; escalating")
            return (
                GuardrailVerdict(
                    score=0.0,
                    violations=["guardrail_unavailable"],
                    feedback="Guardrail judge unavailable",
                ),
                True,
            )

    def _escalate(self, workspace: Workspace, action: Action) -> Outcome:
        approval = WorkspaceRepo(self.db, Approval, self.workspace_id).add(
            action_id=action.id
        )
        emails = notify_approval_needed(self.db, workspace, action, approval)
        self.db.commit()  # durable before anyone is emailed or the run is parked
        for e in emails:
            dispatch.enqueue_email(e.to, e.subject, e.html)
        raise RunPaused(approval.id)

    def _execute(self, action: Action, payload: dict) -> Outcome:
        action_type = ActionType(action.type)
        executor = EXECUTORS.get(action_type)
        reserved = 0.0
        try:
            if executor is None and action_type in REQUIRES_EXECUTOR:
                raise NotImplementedError(f"No executor registered for {action_type.value}")

            if action_type is ActionType.GENERATE_VIDEO:
                reserved = action.estimated_cost_usd or 0.0
                if not self._reserve_video_budget(reserved):
                    reserved = 0.0
                    action.status = ActionStatus.BLOCKED.value
                    action.gate_reason = "Video budget exhausted before execution"
                    self.db.commit()
                    return Outcome(
                        status="blocked", action_id=action.id, reason=action.gate_reason
                    )
                self.db.commit()  # reservation is durable before the (possibly external) job starts

            result = executor(self.db, action, payload) if executor else {}
        except Exception as exc:
            self.db.rollback()
            if reserved:
                self._adjust_video_spend(-reserved)  # the generation never happened: give it back
            action = self.actions.get(action.id)
            action.status = ActionStatus.FAILED.value
            action.result_json = {"error": f"{type(exc).__name__}: {exc}"}
            self.db.commit()
            raise
        action.status = ActionStatus.EXECUTED.value
        action.result_json = result
        self._account_for(action)
        self.db.commit()
        return Outcome(
            status="executed",
            action_id=action.id,
            result=result,
            reason=action.gate_reason or "",
        )

    def _reserve_video_budget(self, cost: float) -> bool:
        """Check-and-spend in one statement: two concurrent generations cannot both pass."""
        result = self.db.execute(
            update(Workspace)
            .where(
                Workspace.id == self.workspace_id,
                Workspace.video_gen_enabled.is_(True),
                Workspace.video_budget_usd - Workspace.video_spent_usd >= cost,
            )
            .values(video_spent_usd=Workspace.video_spent_usd + cost)
        )
        return result.rowcount == 1

    def _adjust_video_spend(self, delta: float) -> None:
        self.db.execute(
            update(Workspace)
            .where(Workspace.id == self.workspace_id)
            .values(video_spent_usd=Workspace.video_spent_usd + delta)
        )
        self.db.commit()

    def _account_for(self, action: Action) -> None:
        """Counters that feed back into the gate. Atomic SQL, so concurrent runs don't lose updates."""
        if action.type == ActionType.PUBLISH_VIDEO.value:
            self.db.execute(
                update(Workspace)
                .where(Workspace.id == self.workspace_id)
                .values(publishes_so_far=Workspace.publishes_so_far + 1)
            )

    def _resume(self, action: Action) -> Outcome:
        s = action.status
        if s == ActionStatus.EXECUTED.value:
            return Outcome(
                status="executed",
                action_id=action.id,
                result=action.result_json or {},
                reason=action.gate_reason or "",
            )
        approval = next(
            iter(WorkspaceRepo(self.db, Approval, self.workspace_id).list(action_id=action.id)),
            None,
        )
        if s == ActionStatus.APPROVED.value:
            payload = (approval.edited_payload_json if approval else None) or action.payload_json
            return self._execute(action, payload)
        if s == ActionStatus.REJECTED.value:
            return Outcome(
                status="rejected",
                action_id=action.id,
                note=approval.decision_note if approval else None,
                reason=action.gate_reason or "",
            )
        if s == ActionStatus.BLOCKED.value:
            return Outcome(
                status="blocked", action_id=action.id, reason=action.gate_reason or ""
            )
        if s == ActionStatus.AWAITING_APPROVAL.value:
            raise RunPaused(approval.id)
        raise RuntimeError(f"Step '{action.step_key}' previously failed")
