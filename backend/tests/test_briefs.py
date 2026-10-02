import uuid
from datetime import timedelta

import pytest

from app.agents.comms import CommsAgent
from app.agents.pm import ProjectManagerAgent
from app.core.config import settings
from app.db import models as m
from app.db.base import utcnow
from app.tasks import dispatch
from app.tasks.brief_tasks import scan_overdue_briefs
from app.workflows import brief_flow
from tests.conftest import make_client_for, make_user, new_workspace
from tests.fakes import Recorder, brief_draft, followup


@pytest.fixture
def env(monkeypatch, worker):
    pm, comms = Recorder(brief_draft), Recorder(followup)
    monkeypatch.setattr(brief_flow, "get_pm_agent", lambda: ProjectManagerAgent(model=pm.model))
    monkeypatch.setattr(brief_flow, "get_comms_agent", lambda: CommsAgent(model=comms.model))
    return type("Env", (), {"pm": pm, "comms": comms, "worker": worker})


def add_editor(db, wid, email="ed@x.co"):
    user = make_user(db, email, name="Ed")
    db.add(m.Membership(workspace_id=uuid.UUID(wid), user_id=user.id, role="editor"))
    db.commit()
    return user


def make_item(db, wid, title="Retrobright a console", days=30):
    item = m.CalendarItem(
        workspace_id=uuid.UUID(wid),
        idea_json={"title": title, "hook": "h", "keywords": ["k"], "format": "tutorial"},
        scheduled_for=utcnow() + timedelta(days=days),
        status="planned",
    )
    db.add(item)
    db.commit()
    return item


def start(client, wid, item, editor=None, **extra):
    params = {"calendar_item_id": str(item.id), **extra}
    if editor:
        params["editor_id"] = str(editor.id)
    return client.post(f"/workspaces/{wid}/runs", json={"workflow": "brief_for_item", "params": params})


def run_status(client, wid, r):
    return client.get(f"/workspaces/{wid}/runs/{r.json()['id']}").json()


def only_brief(db):
    db.expire_all()
    return db.query(m.Brief).one()


def make_late(db, brief, days=2, followups=0, last=None):
    brief.due_at = utcnow() - timedelta(days=days)
    brief.followup_count = followups
    brief.last_followup_at = last
    db.commit()


def scan(db):
    db.expire_all()  # the worker commits from other sessions; the real scan starts fresh too
    created = scan_overdue_briefs(db)
    for ws_id, run_id in created:
        dispatch.enqueue_run(ws_id, run_id)
    return created


# ------------------------------------------------------------------ brief generation


def test_calendar_item_becomes_a_brief_and_the_editor_is_emailed(client, db, env):
    wid, _ = new_workspace(client, db, "medium")
    editor, item = add_editor(db, wid), make_item(db, wid)
    r = start(client, wid, item, editor)
    assert run_status(client, wid, r)["status"] == "succeeded"

    brief = only_brief(db)
    assert brief.status == "assigned" and brief.editor_id == editor.id
    assert brief.body_json["objective"].startswith("Cut a 10 minute")
    assert "<b>" not in brief.body_json["editor_notes"]  # model markup stripped
    lead = (item.scheduled_for - brief.due_at.replace(tzinfo=item.scheduled_for.tzinfo)).days
    assert lead in (settings.BRIEF_LEAD_DAYS, settings.BRIEF_LEAD_DAYS - 1)
    assert db.get(m.CalendarItem, item.id).status == "briefed"
    assert env.worker.emails == [(editor.email, "New brief: Retrobright a console")]
    assert "Retro Fix" in env.pm.prompts[0]  # channel context reached the model

    note = db.query(m.Notification).filter_by(user_id=editor.id).one()
    assert note.kind == "brief_assigned" and note.link.endswith(f"/briefs/{brief.id}")


def test_without_an_editor_the_brief_stays_a_draft_and_nobody_is_emailed(client, db, env):
    wid, _ = new_workspace(client, db, "high")
    r = start(client, wid, make_item(db, wid))
    assert run_status(client, wid, r)["status"] == "succeeded"
    assert only_brief(db).status == "draft" and env.worker.emails == []


def test_low_autonomy_escalates_and_the_admin_can_edit_the_deadline(client, db, env):
    wid, _ = new_workspace(client, db, "low")
    editor, item = add_editor(db, wid), make_item(db, wid)
    r = start(client, wid, item, editor)
    assert run_status(client, wid, r)["status"] == "waiting_approval" and db.query(m.Brief).count() == 0
    assert env.worker.emails and env.worker.emails[0][0] == "owner@x.co"  # owner asked, editor not yet told

    [ap] = client.get(f"/workspaces/{wid}/approvals?status=pending").json()
    new_due = (utcnow() + timedelta(days=5)).isoformat()
    bad = {**ap["payload"], "body": {**ap["payload"]["body"], "outline": []}}
    assert client.post(f"/workspaces/{wid}/approvals/{ap['id']}/decision", json={"decision": "approve", "edited_payload": bad}).status_code == 422
    ok = client.post(f"/workspaces/{wid}/approvals/{ap['id']}/decision", json={"decision": "approve", "edited_payload": {**ap["payload"], "due_at": new_due}})
    assert ok.status_code == 200
    assert only_brief(db).due_at.date() == (utcnow() + timedelta(days=5)).date()
    assert (editor.email, "New brief: Retrobright a console") in env.worker.emails


def test_editor_must_belong_to_the_workspace_and_costs_no_llm_call(client, engine, db, env):
    wid, _ = new_workspace(client, db, "high")
    stranger = make_user(db, "stranger@x.co")
    run = run_status(client, wid, start(client, wid, make_item(db, wid), stranger))
    assert run["status"] == "failed" and "not a member" in run["error"]
    assert env.pm.calls == 0 and db.query(m.Brief).count() == 0


def test_an_item_cannot_have_two_open_briefs(client, db, env):
    wid, _ = new_workspace(client, db, "high")
    item = make_item(db, wid)
    assert run_status(client, wid, start(client, wid, item))["status"] == "succeeded"
    again = run_status(client, wid, start(client, wid, item))
    assert again["status"] == "failed" and "already has an open brief" in again["error"]
    assert db.query(m.Brief).count() == 1


def test_cannot_brief_another_workspaces_item(client, engine, db, env):
    wid_a, _ = new_workspace(client, db, "high", email="a@x.co")
    item_a = make_item(db, wid_a)
    other = make_client_for(engine, make_user(db, "b@x.co"))
    wid_b = other.post("/workspaces", json={"name": "B"}).json()["id"]
    other.patch(f"/workspaces/{wid_b}", json={"autonomy": "high"})
    run = run_status(other, wid_b, start(other, wid_b, item_a))
    assert run["status"] == "failed" and "not found in this workspace" in run["error"]
    assert env.pm.calls == 0 and db.query(m.Brief).count() == 0


# ------------------------------------------------------------------ editor view / API


def assigned(client, db, env, engine):
    wid, owner = new_workspace(client, db, "high")
    editor = add_editor(db, wid)
    start(client, wid, make_item(db, wid), editor)
    return wid, owner, editor, make_client_for(engine, editor), only_brief(db)


def test_editors_see_only_their_own_briefs(client, engine, db, env):
    wid, _, editor, ed_client, brief = assigned(client, db, env, engine)
    other = make_client_for(engine, add_editor(db, wid, "ed2@x.co"))
    assert [b["id"] for b in ed_client.get(f"/workspaces/{wid}/briefs").json()] == [str(brief.id)]
    assert other.get(f"/workspaces/{wid}/briefs").json() == []
    assert other.get(f"/workspaces/{wid}/briefs/{brief.id}").status_code == 404
    assert len(client.get(f"/workspaces/{wid}/briefs").json()) == 1  # the owner sees all
    got = ed_client.get(f"/workspaces/{wid}/briefs/{brief.id}").json()
    assert got["title"] == "Retrobright a console" and got["overdue"] is False
    assert make_client_for(engine, make_user(db, "nobody@x.co")).get(f"/workspaces/{wid}/briefs").status_code == 404


def test_editor_moves_a_brief_forward_and_the_owner_is_told_on_delivery(client, engine, db, env):
    wid, owner, editor, ed_client, brief = assigned(client, db, env, engine)
    url = f"/workspaces/{wid}/briefs/{brief.id}/status"
    assert ed_client.post(url, json={"status": "done"}).status_code == 409  # only the owner closes
    assert ed_client.post(url, json={"status": "in_progress"}).json()["status"] == "in_progress"
    assert ed_client.post(url, json={"status": "assigned"}).status_code == 409  # no going back
    env.worker.emails.clear()
    out = ed_client.post(url, json={"status": "submitted"}).json()
    assert out["status"] == "submitted" and out["submitted_at"]
    assert env.worker.emails == [(owner.email, "Editor delivered: Retrobright a console")]
    assert ed_client.post(url, json={"status": "in_progress"}).status_code == 409
    assert client.post(url, json={"status": "done"}).json()["status"] == "done"


def test_editors_cannot_reassign_or_change_deadlines(client, engine, db, env):
    wid, _, _, ed_client, brief = assigned(client, db, env, engine)
    r = ed_client.patch(f"/workspaces/{wid}/briefs/{brief.id}", json={"due_at": utcnow().isoformat()})
    assert r.status_code == 403


def test_owner_reassigns_and_the_new_editor_is_notified_with_follow_ups_reset(client, engine, db, env):
    wid, _, _, _, brief = assigned(client, db, env, engine)
    make_late(db, brief, followups=2, last=utcnow())
    new = add_editor(db, wid, "new@x.co")
    env.worker.emails.clear()
    r = client.patch(f"/workspaces/{wid}/briefs/{brief.id}", json={"editor_id": str(new.id)})
    assert r.status_code == 200 and r.json()["editor_id"] == str(new.id)
    b = only_brief(db)
    assert b.followup_count == 0 and b.last_followup_at is None and b.status == "assigned"
    assert env.worker.emails == [(new.email, "New brief: Retrobright a console")]
    stranger = make_user(db, "s@x.co")
    assert client.patch(f"/workspaces/{wid}/briefs/{brief.id}", json={"editor_id": str(stranger.id)}).status_code == 422


# ---------------------------------------------------------------- deadline follow-ups


def test_overdue_brief_triggers_a_follow_up_to_the_editor(client, engine, db, env):
    wid, _, editor, ed_client, brief = assigned(client, db, env, engine)
    assert scan(db) == []  # not due yet
    make_late(db, brief)
    assert ed_client.get(f"/workspaces/{wid}/briefs/{brief.id}").json()["overdue"] is True
    env.worker.emails.clear()
    [(_, run_id)] = scan(db)
    assert db.get(m.Run, run_id).status == "succeeded"
    assert env.worker.emails == [(editor.email, "Checking in on your brief (#1)")]
    b = only_brief(db)
    assert b.followup_count == 1 and b.last_followup_at is not None
    assert "2 day(s) late" in env.comms.prompts[0] and "Retrobright" in env.comms.prompts[0]
    assert db.query(m.Notification).filter_by(user_id=editor.id, kind="brief_followup").count() == 1


def test_follow_ups_are_spaced_then_the_owner_is_told_once_and_the_nagging_stops(client, engine, db, env):
    wid, owner, editor, _, brief = assigned(client, db, env, engine)
    make_late(db, brief)
    assert len(scan(db)) == 1
    assert scan(db) == []  # too soon after the last one

    emails = env.worker.emails
    for expected in range(2, settings.BRIEF_MAX_FOLLOWUPS + 1):
        b = only_brief(db)
        b.last_followup_at = utcnow() - timedelta(hours=settings.BRIEF_FOLLOWUP_INTERVAL_HOURS + 1)
        db.commit()
        assert len(scan(db)) == 1 and only_brief(db).followup_count == expected
    assert {to for to, _ in emails} == {editor.email}

    b = only_brief(db)
    b.last_followup_at = utcnow() - timedelta(hours=settings.BRIEF_FOLLOWUP_INTERVAL_HOURS + 1)
    db.commit()
    emails.clear()
    assert len(scan(db)) == 1
    assert [to for to, _ in emails] == [owner.email]  # the editor is not nagged a fourth time
    assert db.query(m.Notification).filter_by(user_id=owner.id, kind="brief_overdue").count() == 1

    b = only_brief(db)
    b.last_followup_at = utcnow() - timedelta(days=30)
    db.commit()
    assert scan(db) == []  # owner already told: no more runs


def test_a_run_waiting_for_approval_is_not_duplicated_by_the_next_scan(client, engine, db, env):
    wid, owner = new_workspace(client, db, "high")
    editor = add_editor(db, wid)
    start(client, wid, make_item(db, wid), editor)
    client.patch(f"/workspaces/{wid}", json={"autonomy": "low"})
    make_late(db, only_brief(db))
    assert len(scan(db)) == 1
    assert db.query(m.Run).filter_by(workflow="brief_followup").one().status == "waiting_approval"
    b = only_brief(db)
    b.last_followup_at = utcnow() - timedelta(days=3)
    db.commit()
    assert scan(db) == []  # one follow-up is already awaiting the owner


def test_rejected_follow_up_is_not_retried_straight_away(client, engine, db, env):
    wid, owner = new_workspace(client, db, "high")
    start(client, wid, make_item(db, wid), add_editor(db, wid))
    client.patch(f"/workspaces/{wid}", json={"autonomy": "low"})
    make_late(db, only_brief(db))
    scan(db)
    [ap] = client.get(f"/workspaces/{wid}/approvals?status=pending").json()
    client.post(f"/workspaces/{wid}/approvals/{ap['id']}/decision", json={"decision": "reject", "note": "I will message them myself"})
    db.expire_all()
    assert db.query(m.Run).filter_by(workflow="brief_followup").one().state_json["followup"] == "rejected"
    assert only_brief(db).followup_count == 0 and scan(db) == []


def test_delivered_briefs_are_never_followed_up_even_if_approval_comes_late(client, engine, db, env):
    wid, owner = new_workspace(client, db, "high")
    editor = add_editor(db, wid)
    start(client, wid, make_item(db, wid), editor)
    client.patch(f"/workspaces/{wid}", json={"autonomy": "low"})
    brief = only_brief(db)
    make_late(db, brief)
    scan(db)
    make_client_for(engine, editor).post(f"/workspaces/{wid}/briefs/{brief.id}/status", json={"status": "submitted"})
    env.worker.emails.clear()
    [ap] = client.get(f"/workspaces/{wid}/approvals?status=pending").json()
    assert client.post(f"/workspaces/{wid}/approvals/{ap['id']}/decision", json={"decision": "approve"}).status_code == 200
    assert editor.email not in [to for to, _ in env.worker.emails]
    assert only_brief(db).followup_count == 0
    assert scan(db) == []


def test_follow_up_email_text_is_escaped(client, engine, db, env, monkeypatch):
    from app.comms import briefs as comms_mod

    wid, _, editor, _, brief = assigned(client, db, env, engine)
    brief_row = only_brief(db)
    email = comms_mod.notify_followup(db, db.get(m.Workspace, uuid.UUID(wid)), brief_row, editor, "brief_followup", "s", "<script>x</script>")
    assert "<script>" not in email.html and "&lt;script&gt;" in email.html
