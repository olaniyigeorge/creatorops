from datetime import timedelta

from app.db.base import utcnow
from app.db.models import Invitation
from tests.conftest import login, make_client_for, make_user


def _create(client, name="Acme"):
    r = client.post("/workspaces", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def test_requires_auth(client):
    assert client.post("/workspaces", json={"name": "x"}).status_code == 401
    assert client.get("/workspaces").status_code == 401


def test_creator_becomes_owner_with_safe_defaults(client, db):
    login(client, make_user(db))
    ws = _create(client)
    assert ws["autonomy"] == "low" and ws["video_gen_enabled"] is False
    assert client.get("/workspaces").json() == [{"id": ws["id"], "name": "Acme", "role": "owner"}]


def test_members_cannot_see_other_workspaces(client, engine, db):
    a, b = make_user(db), make_user(db)
    ws_a = _create(login(client, a), "A")
    other = make_client_for(engine, b)
    ws_b = _create(other, "B")

    assert [w["id"] for w in other.get("/workspaces").json()] == [ws_b["id"]]
    for path in ("", "/members"):
        assert other.get(f"/workspaces/{ws_a['id']}{path}").status_code == 404
    assert other.patch(f"/workspaces/{ws_a['id']}", json={"name": "x"}).status_code == 404
    assert other.post(f"/workspaces/{ws_a['id']}/invitations", json={"email": "z@z.co"}).status_code == 404


def test_owner_updates_settings_with_validation(client, db):
    login(client, make_user(db))
    ws = _create(client)
    url = f"/workspaces/{ws['id']}"
    r = client.patch(url, json={"autonomy": "medium", "video_gen_enabled": True, "video_budget_usd": 25})
    assert r.status_code == 200 and r.json()["autonomy"] == "medium"
    assert client.patch(url, json={"autonomy": "reckless"}).status_code == 422
    assert client.patch(url, json={"guardrail_threshold": 2}).status_code == 422


def test_spend_and_publish_counters_are_not_client_settable(client, db):
    login(client, make_user(db))
    ws = _create(client)
    client.patch(f"/workspaces/{ws['id']}", json={"video_spent_usd": 0, "publishes_so_far": 99})
    assert client.get(f"/workspaces/{ws['id']}").json()["video_spent_usd"] == 0


def test_invitation_flow_and_editor_permissions(client, engine, db):
    owner, editor = make_user(db, "own@x.co"), make_user(db, "ed@x.co")
    ws = _create(login(client, owner))
    inv = client.post(f"/workspaces/{ws['id']}/invitations", json={"email": "Ed@X.co"})
    assert inv.status_code == 201
    token = inv.json()["token"]

    ed = make_client_for(engine, editor)
    r = ed.post("/invitations/accept", json={"token": token})
    assert r.status_code == 200 and r.json()["role"] == "editor"

    # editor can read but not administer
    assert ed.get(f"/workspaces/{ws['id']}").status_code == 200
    assert len(ed.get(f"/workspaces/{ws['id']}/members").json()) == 2
    assert ed.patch(f"/workspaces/{ws['id']}", json={"autonomy": "high"}).status_code == 403
    assert ed.post(f"/workspaces/{ws['id']}/invitations", json={"email": "n@x.co"}).status_code == 403

    # token is single-use; members cannot be re-invited
    assert ed.post("/invitations/accept", json={"token": token}).status_code == 400
    assert client.post(f"/workspaces/{ws['id']}/invitations", json={"email": "ed@x.co"}).status_code == 409


def test_invitation_rejects_wrong_email_expired_and_owner_role(client, engine, db):
    owner, stranger = make_user(db, "own@x.co"), make_user(db, "who@x.co")
    ws = _create(login(client, owner))
    url = f"/workspaces/{ws['id']}/invitations"

    assert client.post(url, json={"email": "ed@x.co", "role": "owner"}).status_code == 422

    token = client.post(url, json={"email": "ed@x.co"}).json()["token"]
    s = make_client_for(engine, stranger)
    assert s.post("/invitations/accept", json={"token": token}).status_code == 403
    assert s.post("/invitations/accept", json={"token": "nope"}).status_code == 400

    db.query(Invitation).update({"expires_at": utcnow() - timedelta(days=1)})
    db.commit()
    editor = make_user(db, "ed@x.co")
    assert make_client_for(engine, editor).post("/invitations/accept", json={"token": token}).status_code == 400


def test_invitation_token_is_stored_hashed(client, db):
    login(client, make_user(db))
    ws = _create(client)
    token = client.post(f"/workspaces/{ws['id']}/invitations", json={"email": "e@x.co"}).json()["token"]
    stored = db.query(Invitation).one()
    assert stored.token_hash != token and len(stored.token_hash) == 64


def test_workspace_response_includes_the_callers_role(client, engine, db):
    owner, editor = make_user(db, "own@x.co"), make_user(db, "ed@x.co")
    ws = _create(login(client, owner))
    assert ws["role"] == "owner" and client.get(f"/workspaces/{ws['id']}").json()["role"] == "owner"
    token = client.post(f"/workspaces/{ws['id']}/invitations", json={"email": "ed@x.co"}).json()["token"]
    ed = make_client_for(engine, editor)
    ed.post("/invitations/accept", json={"token": token})
    assert ed.get(f"/workspaces/{ws['id']}").json()["role"] == "editor"
