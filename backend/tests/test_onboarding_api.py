from tests.conftest import PROFILE, login, make_client_for, make_user, new_workspace


def test_owner_submits_profile_and_rubric_is_derived(client, db):
    wid, _ = new_workspace(client, db, onboard=False)
    assert client.get(f"/workspaces/{wid}/onboarding").status_code == 404
    r = client.put(f"/workspaces/{wid}/onboarding", json=PROFILE)
    assert r.status_code == 200 and r.json()["region_code"] == "US"  # normalised

    ws = client.get(f"/workspaces/{wid}").json()
    assert ws["brand_json"]["onboarded"] is True
    assert ws["rubric_json"] == {
        "brand_voice": "friendly and practical. plain language, no hype",
        "banned_topics": ["politics"],
        "extra_rules": ["never promise income"],
    }
    assert client.get(f"/workspaces/{wid}/onboarding").json()["channel_name"] == "Retro Fix"


def test_validation(client, db):
    wid, _ = new_workspace(client, db, onboard=False)
    url = f"/workspaces/{wid}/onboarding"
    assert client.put(url, json={**PROFILE, "goal": "fame"}).status_code == 422
    assert client.put(url, json={**PROFILE, "videos_per_week": 0}).status_code == 422
    assert client.put(url, json={**PROFILE, "videos_per_week": 99}).status_code == 422
    assert client.put(url, json={**PROFILE, "region_code": "USA"}).status_code == 422
    assert client.put(url, json={**PROFILE, "competitors": [f"@c{i}abc" for i in range(11)]}).status_code == 422
    assert client.put(url, json={**PROFILE, "channel_name": ""}).status_code == 422


def test_lists_are_cleaned_and_deduped(client, db):
    wid, _ = new_workspace(client, db, onboard=False)
    body = {**PROFILE, "competitors": ["@a_chan", " @a_chan ", "", "@b_chan"], "banned_topics": ["x", "x", "  "]}
    out = client.put(f"/workspaces/{wid}/onboarding", json=body).json()
    assert out["competitors"] == ["@a_chan", "@b_chan"] and out["banned_topics"] == ["x"]


def test_resubmitting_keeps_the_niche_the_agent_chose(client, db):
    import uuid

    from app.db.models import Workspace

    wid, _ = new_workspace(client, db)
    ws = db.get(Workspace, uuid.UUID(wid))
    ws.brand_json = {**ws.brand_json, "niche": {"name": "Console repair"}}
    db.commit()
    client.put(f"/workspaces/{wid}/onboarding", json={**PROFILE, "tone": "calm"})
    db.expire_all()
    assert db.get(Workspace, uuid.UUID(wid)).brand_json["niche"] == {"name": "Console repair"}


def test_only_owner_writes_members_read_others_blocked(client, engine, db):
    wid, _ = new_workspace(client, db)
    token = client.post(f"/workspaces/{wid}/invitations", json={"email": "ed@x.co"}).json()["token"]
    ed = make_client_for(engine, make_user(db, "ed@x.co"))
    ed.post("/invitations/accept", json={"token": token})
    assert ed.get(f"/workspaces/{wid}/onboarding").status_code == 200
    assert ed.put(f"/workspaces/{wid}/onboarding", json=PROFILE).status_code == 403

    stranger = make_client_for(engine, make_user(db, "s@x.co"))
    assert stranger.get(f"/workspaces/{wid}/onboarding").status_code == 404
    assert stranger.put(f"/workspaces/{wid}/onboarding", json=PROFILE).status_code == 404
