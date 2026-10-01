"""End to end over HTTP: start run -> escalate -> notify -> decide -> run resumes."""

import pytest
from sqlalchemy.orm import sessionmaker

from app.db import models as m
from app.gate.autonomy import ActionType as A, ProposedAction
from app.tasks import dispatch
from app.tasks.runner import WORKFLOWS, execute_run, register_workflow
from app.workflows import context as wfc
from app.workflows.context import Draft
from tests.conftest import login, make_client_for, make_user

EXECUTED = []


def e2e_workflow(ctx):
    """strategy (always high-stakes) then a routine creative step."""
    niche = ctx.propose(
        "niche",
        lambda fb: Draft(ProposedAction(type=A.SET_STRATEGY, summary="Pick niche: retro gaming", payload={"niche": "retro gaming"})),
    )
    if niche.status == "rejected":
        return {"rejected": True, "guidance": niche.note}
    ctx.propose("titles", lambda fb: Draft(ProposedAction(type=A.GENERATE_CREATIVE, summary="Draft titles")))
    return {"niche": niche.result["selected"]}


@pytest.fixture(autouse=True)
def harness(engine, monkeypatch):
    EXECUTED.clear()
    register_workflow("e2e", e2e_workflow)
    monkeypatch.setattr(
        wfc, "EXECUTORS",
        {
            A.SET_STRATEGY: lambda db, a, p: EXECUTED.append(p) or {"selected": p["niche"]},
            A.GENERATE_CREATIVE: lambda db, a, p: {"titles": ["t1"]},
        },
    )
    monkeypatch.setattr(wfc, "PAYLOAD_VALIDATORS", {})  # this file uses ad-hoc payload shapes
    maker = sessionmaker(bind=engine, expire_on_commit=False)

    def inline_run(workspace_id, run_id):  # stands in for the Celery worker
        s = maker()
        try:
            execute_run(s, workspace_id, run_id)
        finally:
            s.close()

    emails = []
    monkeypatch.setattr(dispatch, "enqueue_run", inline_run)
    monkeypatch.setattr(dispatch, "enqueue_email", lambda to, subject, html: emails.append((to, subject)))
    yield emails
    WORKFLOWS.pop("e2e", None)


def make_ws(client, db, autonomy="medium"):
    owner = make_user(db, "owner@x.co")
    login(client, owner)
    ws = client.post("/workspaces", json={"name": "Acme"}).json()
    client.patch(f"/workspaces/{ws['id']}", json={"autonomy": autonomy})
    return ws["id"], owner


def start(client, wid):
    r = client.post(f"/workspaces/{wid}/runs", json={"workflow": "e2e"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_escalation_then_approval_with_edits_resumes_run(client, db, harness):
    wid, owner = make_ws(client, db)
    rid = start(client, wid)

    run = client.get(f"/workspaces/{wid}/runs/{rid}").json()
    assert run["status"] == "waiting_approval" and not EXECUTED
    assert [a["status"] for a in run["actions"]] == ["awaiting_approval"]

    pending = client.get(f"/workspaces/{wid}/approvals?status=pending").json()
    assert len(pending) == 1 and pending[0]["payload"] == {"niche": "retro gaming"}
    assert harness == [("owner@x.co", "Approval needed: Pick niche: retro gaming")]
    notes = client.get(f"/workspaces/{wid}/notifications?unread=true").json()
    assert len(notes) == 1 and notes[0]["link"] == f"/workspaces/{wid}/approvals/{pending[0]['id']}"

    r = client.post(
        f"/workspaces/{wid}/approvals/{pending[0]['id']}/decision",
        json={"decision": "approve", "edited_payload": {"niche": "retro gaming repair"}},
    )
    assert r.status_code == 200 and r.json()["status"] == "approved"

    run = client.get(f"/workspaces/{wid}/runs/{rid}").json()
    assert run["status"] == "succeeded"
    assert EXECUTED == [{"niche": "retro gaming repair"}]  # the admin's edit, executed once
    assert [a["status"] for a in run["actions"]] == ["executed", "executed"]

    mem = db.query(m.MemoryItem).one()
    assert mem.kind == "decision" and "edited" in mem.text and mem.source_approval_id


def test_rejection_with_note_resumes_run_and_is_remembered(client, db):
    wid, _ = make_ws(client, db)
    rid = start(client, wid)
    aid = client.get(f"/workspaces/{wid}/approvals").json()[0]["id"]
    r = client.post(f"/workspaces/{wid}/approvals/{aid}/decision", json={"decision": "reject", "note": "avoid gaming niches"})
    assert r.status_code == 200

    run = client.get(f"/workspaces/{wid}/runs/{rid}").json()
    assert run["status"] == "succeeded" and not EXECUTED
    state = db.query(m.Run).one().state_json
    assert state == {"rejected": True, "guidance": "avoid gaming niches"}
    mem = db.query(m.MemoryItem).one()
    assert mem.kind == "preference" and "avoid gaming niches" in mem.text


def test_double_decision_is_rejected(client, db):
    wid, _ = make_ws(client, db)
    start(client, wid)
    aid = client.get(f"/workspaces/{wid}/approvals").json()[0]["id"]
    url = f"/workspaces/{wid}/approvals/{aid}/decision"
    assert client.post(url, json={"decision": "approve"}).status_code == 200
    assert client.post(url, json={"decision": "reject"}).status_code == 409
    assert len(EXECUTED) == 1 and db.query(m.MemoryItem).count() == 1


def test_edits_only_allowed_when_approving(client, db):
    wid, _ = make_ws(client, db)
    start(client, wid)
    aid = client.get(f"/workspaces/{wid}/approvals").json()[0]["id"]
    r = client.post(f"/workspaces/{wid}/approvals/{aid}/decision", json={"decision": "reject", "edited_payload": {"a": 1}})
    assert r.status_code == 422


def test_high_autonomy_runs_through_without_approval(client, db, harness):
    wid, _ = make_ws(client, db, autonomy="high")
    rid = start(client, wid)
    assert client.get(f"/workspaces/{wid}/runs/{rid}").json()["status"] == "succeeded"
    assert client.get(f"/workspaces/{wid}/approvals").json() == [] and not harness


def test_editors_see_activity_but_cannot_start_or_decide(client, engine, db):
    wid, owner = make_ws(client, db)
    rid = start(client, wid)
    aid = client.get(f"/workspaces/{wid}/approvals").json()[0]["id"]
    token = client.post(f"/workspaces/{wid}/invitations", json={"email": "ed@x.co"}).json()["token"]
    ed = make_client_for(engine, make_user(db, "ed@x.co"))
    ed.post("/invitations/accept", json={"token": token})

    assert ed.get(f"/workspaces/{wid}/runs").status_code == 200
    assert ed.get(f"/workspaces/{wid}/runs/{rid}").status_code == 200
    assert ed.post(f"/workspaces/{wid}/runs", json={"workflow": "e2e"}).status_code == 403
    assert ed.get(f"/workspaces/{wid}/approvals").status_code == 403
    assert ed.post(f"/workspaces/{wid}/approvals/{aid}/decision", json={"decision": "approve"}).status_code == 403
    assert ed.get(f"/workspaces/{wid}/notifications").json() == []  # only owners are notified


def test_other_workspaces_cannot_touch_approvals_or_runs(client, engine, db):
    wid, _ = make_ws(client, db)
    rid = start(client, wid)
    aid = client.get(f"/workspaces/{wid}/approvals").json()[0]["id"]

    other = make_client_for(engine, make_user(db, "other@x.co"))
    other_wid = other.post("/workspaces", json={"name": "Other"}).json()["id"]
    # right ids, wrong workspace -> 404 either way
    for path, method in [
        (f"/workspaces/{other_wid}/approvals/{aid}", "get"),
        (f"/workspaces/{other_wid}/runs/{rid}", "get"),
    ]:
        assert getattr(other, method)(path).status_code == 404
    assert other.post(f"/workspaces/{other_wid}/approvals/{aid}/decision", json={"decision": "approve"}).status_code == 404
    assert other.post(f"/workspaces/{wid}/approvals/{aid}/decision", json={"decision": "approve"}).status_code == 404
    assert db.query(m.Approval).one().status == "pending"


def test_unknown_workflow_and_bad_ids(client, db):
    wid, _ = make_ws(client, db)
    assert client.post(f"/workspaces/{wid}/runs", json={"workflow": "nope"}).status_code == 422
    assert client.get(f"/workspaces/{wid}/runs/not-a-uuid").status_code == 404
    assert client.get(f"/workspaces/{wid}/approvals/not-a-uuid").status_code == 404
    assert client.post(f"/workspaces/{wid}/notifications/not-a-uuid/read").status_code == 404


def test_notifications_are_per_user_and_markable(client, db):
    wid, owner = make_ws(client, db)
    start(client, wid)
    n = client.get(f"/workspaces/{wid}/notifications").json()[0]
    assert n["read_at"] is None
    assert client.post(f"/workspaces/{wid}/notifications/{n['id']}/read").json()["read_at"]
    assert client.get(f"/workspaces/{wid}/notifications?unread=true").json() == []


def test_cannot_read_another_users_notification(client, engine, db):
    wid, owner = make_ws(client, db)
    start(client, wid)
    nid = client.get(f"/workspaces/{wid}/notifications").json()[0]["id"]
    token = client.post(f"/workspaces/{wid}/invitations", json={"email": "ed@x.co"}).json()["token"]
    ed = make_client_for(engine, make_user(db, "ed@x.co"))
    ed.post("/invitations/accept", json={"token": token})
    assert ed.post(f"/workspaces/{wid}/notifications/{nid}/read").status_code == 404
