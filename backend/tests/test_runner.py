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
    register_workflow("boom", lambda run, db: 1 / 0)
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
