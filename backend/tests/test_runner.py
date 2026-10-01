import uuid

import pytest

from app.db import models as m
from app.db.repo import WorkspaceRepo
from app.tasks.runner import WORKFLOWS, execute_run, register_workflow


def _ws(db):
    w = m.Workspace(name="w")
    db.add(w)
    db.commit()
    return w


def test_noop_run_succeeds_and_persists_state(db):
    ws = _ws(db)
    run = WorkspaceRepo(db, m.Run, ws.id).add(workflow="noop")
    out = execute_run(db, ws.id, run.id)
    assert out.status == "succeeded" and out.state_json == {"ok": True} and out.finished_at


def test_unknown_workflow_fails_with_error(db):
    ws = _ws(db)
    run = WorkspaceRepo(db, m.Run, ws.id).add(workflow="missing")
    out = execute_run(db, ws.id, run.id)
    assert out.status == "failed" and "Unknown workflow" in out.error


def test_workflow_exception_is_recorded_not_raised(db):
    ws = _ws(db)
    register_workflow("boom", lambda ctx: 1 / 0)
    try:
        run = WorkspaceRepo(db, m.Run, ws.id).add(workflow="boom")
        out = execute_run(db, ws.id, run.id)
        assert out.status == "failed" and "ZeroDivisionError" in out.error
    finally:
        WORKFLOWS.pop("boom")


def test_cannot_execute_another_workspaces_run(db):
    a, b = _ws(db), _ws(db)
    run = WorkspaceRepo(db, m.Run, a.id).add(workflow="noop")
    with pytest.raises(LookupError):
        execute_run(db, b.id, run.id)
    assert db.get(m.Run, run.id).status == "pending"


def test_finished_run_is_not_rerun_on_redelivery(db):
    ws = _ws(db)
    calls = []
    register_workflow("once", lambda ctx: calls.append(1) or {"n": len(calls)})
    try:
        run = WorkspaceRepo(db, m.Run, ws.id).add(workflow="once")
        execute_run(db, ws.id, run.id)
        out = execute_run(db, ws.id, run.id)  # at-least-once delivery
        assert calls == [1] and out.status == "succeeded"
    finally:
        WORKFLOWS.pop("once")


def test_claim_is_exclusive_and_stale_runs_are_reclaimable(db):
    from datetime import timedelta

    from app.db.base import utcnow
    from app.tasks.runner import _claim

    ws = _ws(db)
    run = WorkspaceRepo(db, m.Run, ws.id).add(workflow="noop")
    db.commit()
    assert _claim(db, ws.id, run.id) is True
    assert _claim(db, ws.id, run.id) is False  # already running: second worker backs off

    db.get(m.Run, run.id).started_at = utcnow() - timedelta(hours=1)  # worker died
    db.commit()
    assert _claim(db, ws.id, run.id) is True
