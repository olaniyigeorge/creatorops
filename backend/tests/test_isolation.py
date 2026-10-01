"""Tenant isolation: every tenant model is invisible and untouchable across workspaces."""

import uuid
from datetime import datetime, timezone

import pytest

from app.db import models as m
from app.db.models import Workspace
from app.db.repo import CrossTenantReference, WorkspaceRepo, tenant_models
from tests.conftest import make_user


def _ws(db, name):
    w = Workspace(name=name)
    db.add(w)
    db.commit()
    return w


def _run(db, ws):
    return WorkspaceRepo(db, m.Run, ws.id).add(workflow="noop")


def _action(db, ws):
    return WorkspaceRepo(db, m.Action, ws.id).add(
        run_id=_run(db, ws).id, step_key="s", status="executed", type="research", summary="s"
    )


def _calendar_item(db, ws):
    return WorkspaceRepo(db, m.CalendarItem, ws.id).add(idea_json={})


# One factory per tenant model. A new tenant model without one fails
# `test_every_tenant_model_has_an_isolation_factory`.
FACTORIES = {
    m.Membership: lambda db, ws: WorkspaceRepo(db, m.Membership, ws.id).add(
        user_id=make_user(db).id, role="editor"
    ),
    m.Invitation: lambda db, ws: WorkspaceRepo(db, m.Invitation, ws.id).add(
        email="a@b.co",
        role="editor",
        token_hash=uuid.uuid4().hex,
        invited_by=make_user(db).id,
        expires_at=datetime.now(timezone.utc),
    ),
    m.Channel: lambda db, ws: WorkspaceRepo(db, m.Channel, ws.id).add(title="c"),
    m.Run: _run,
    m.Action: _action,
    m.Approval: lambda db, ws: WorkspaceRepo(db, m.Approval, ws.id).add(
        action_id=_action(db, ws).id
    ),
    m.CalendarItem: _calendar_item,
    m.Brief: lambda db, ws: WorkspaceRepo(db, m.Brief, ws.id).add(
        calendar_item_id=_calendar_item(db, ws).id
    ),
    m.Asset: lambda db, ws: WorkspaceRepo(db, m.Asset, ws.id).add(
        kind="video", public_id="p", source="ai"
    ),
    m.Notification: lambda db, ws: WorkspaceRepo(db, m.Notification, ws.id).add(
        user_id=make_user(db).id, kind="approval_needed", title="t"
    ),
    m.MemoryItem: lambda db, ws: WorkspaceRepo(db, m.MemoryItem, ws.id).add(
        kind="preference", text="t"
    ),
}


def test_every_tenant_model_has_an_isolation_factory():
    assert set(tenant_models()) == set(FACTORIES)


@pytest.mark.parametrize("model", list(FACTORIES), ids=lambda c: c.__name__)
def test_rows_are_invisible_and_undeletable_from_another_workspace(db, model):
    a, b = _ws(db, "A"), _ws(db, "B")
    row = FACTORIES[model](db, a)
    db.commit()

    repo_a, repo_b = WorkspaceRepo(db, model, a.id), WorkspaceRepo(db, model, b.id)
    assert repo_a.get(row.id) is not None
    assert repo_b.get(row.id) is None
    assert row.id not in [r.id for r in repo_b.list()]
    assert repo_b.delete(row.id) is False
    assert repo_a.get(row.id) is not None  # still there


def test_cannot_reference_another_workspaces_row(db):
    a, b = _ws(db, "A"), _ws(db, "B")
    item_in_a = _calendar_item(db, a)
    with pytest.raises(CrossTenantReference):
        WorkspaceRepo(db, m.Brief, b.id).add(calendar_item_id=item_in_a.id)
    # same workspace is fine
    WorkspaceRepo(db, m.Brief, a.id).add(calendar_item_id=item_in_a.id)


def test_repo_rejects_non_tenant_models_and_workspace_override(db):
    a = _ws(db, "A")
    with pytest.raises(TypeError):
        WorkspaceRepo(db, m.User, a.id)
    with pytest.raises(ValueError):
        WorkspaceRepo(db, m.Run, a.id).add(workflow="x", workspace_id=uuid.uuid4())
    with pytest.raises(ValueError):
        WorkspaceRepo(db, m.Run, None)


def test_deleting_a_workspace_cascades_its_data(db):
    a = _ws(db, "A")
    FACTORIES[m.Brief](db, a)
    db.commit()
    db.delete(a)
    db.commit()
    assert db.query(m.Brief).count() == 0
    assert db.query(m.CalendarItem).count() == 0


def test_workspace_policy_mapping(db):
    w = Workspace(
        name="p", autonomy="medium", video_gen_enabled=True,
        video_budget_usd=10, video_spent_usd=4, publishes_so_far=2,
    )
    db.add(w)
    db.commit()  # column defaults (threshold, floor) are applied on insert
    p = w.to_policy()
    assert p.autonomy.value == "medium"
    assert p.video_budget_usd_remaining == 6
    assert p.publishes_so_far == 2
