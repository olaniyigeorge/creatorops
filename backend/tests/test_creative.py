import uuid

import pytest

from app.agents.creative import CreativeAgent, enforce_limits
from app.core.config import settings
from app.db import models as m
from app.schemas.strategy import CreativePackage, TitleOption
from app.workflows import creative_flow
from tests.conftest import make_client_for, make_user, new_workspace
from tests.fakes import Recorder, creative

# ------------------------------------------------------------ YouTube limits in code


def pkg(**kw):
    base = dict(titles=[TitleOption(title="Good title")], description="d", tags=[])
    return CreativePackage(**{**base, **kw})


def test_titles_over_100_chars_are_dropped_tags_stripped_and_deduped():
    out = enforce_limits(pkg(titles=[
        TitleOption(title="x" * 101), TitleOption(title="Fix <b>it</b> now"),
        TitleOption(title="FIX IT NOW"), TitleOption(title="2 < 3 and 5 > 4"),
    ]))
    assert [t.title for t in out.titles] == ["Fix it now", "2 3 and 5 4"]


def test_no_valid_title_is_an_error_not_a_silent_empty_package():
    with pytest.raises(ValueError, match="100-character"):
        enforce_limits(pkg(titles=[TitleOption(title="y" * 150)]))


def test_description_is_cut_to_5000_bytes_without_breaking_characters():
    out = enforce_limits(pkg(description="é" * 4000))  # 8000 bytes
    assert len(out.description.encode()) <= 5000 and out.description == "é" * 2500


def test_tags_limited_per_tag_and_in_total_and_cleaned():
    tags = ["ok tag", "OK TAG", "a,b", "z" * 31] + [f"tag-number-{i:03d}" for i in range(100)]
    out = enforce_limits(pkg(tags=tags)).tags
    assert out[:2] == ["ok tag", "ab"] and all(len(t) <= 30 for t in out)
    assert sum(len(t) + 1 for t in out) <= 480 and len(out) < 100


# --------------------------------------------------------------------- workflow


@pytest.fixture
def env(monkeypatch, worker):
    rec = Recorder(creative)
    monkeypatch.setattr(creative_flow, "get_agent", lambda: CreativeAgent(model=rec.model))
    return type("Env", (), {"rec": rec, "worker": worker})


def make_item(db, wid, title="Retrobright a console"):
    item = m.CalendarItem(workspace_id=uuid.UUID(wid), idea_json={"title": title, "hook": "h", "keywords": ["k"], "format": "tutorial"}, status="planned")
    db.add(item)
    db.commit()
    return item


def start(client, wid, item):
    return client.post(f"/workspaces/{wid}/runs", json={"workflow": "creative_for_item", "params": {"calendar_item_id": str(item.id)}})


def test_routine_creative_proceeds_at_medium_autonomy_and_saves_to_the_item(client, db, env):
    wid, _ = new_workspace(client, db, "medium")
    item = make_item(db, wid)
    r = start(client, wid, item)
    assert r.status_code == 201
    run = client.get(f"/workspaces/{wid}/runs/{r.json()['id']}").json()
    assert run["status"] == "succeeded" and client.get(f"/workspaces/{wid}/approvals").json() == []

    saved = client.get(f"/workspaces/{wid}/calendar/{item.id}").json()
    assert saved["status"] == "creative_ready"
    c = saved["idea_json"]["creative"]
    assert c["titles"][0]["title"] == "Fix a yellowed console in 10 minutes" and c["video_plan"]
    assert saved["idea_json"]["title"] == "Retrobright a console"  # original idea preserved
    assert "Retro Fix" in env.rec.prompts[0] and "retrobright" in env.rec.prompts[0].lower()


def test_low_autonomy_escalates_and_admin_edit_is_re_validated(client, db, env):
    wid, _ = new_workspace(client, db, "low")
    item = make_item(db, wid)
    rid = start(client, wid, item).json()["id"]
    assert client.get(f"/workspaces/{wid}/runs/{rid}").json()["status"] == "waiting_approval"
    [ap] = client.get(f"/workspaces/{wid}/approvals?status=pending").json()

    too_long = {**ap["payload"], "package": {**ap["payload"]["package"], "titles": [{"title": "t" * 120, "angle": ""}]}}
    r = client.post(f"/workspaces/{wid}/approvals/{ap['id']}/decision", json={"decision": "approve", "edited_payload": too_long})
    assert r.status_code == 422 and "100-character" in r.json()["detail"]

    edited = {**ap["payload"], "package": {**ap["payload"]["package"], "titles": [{"title": "My own title", "angle": "admin"}]}}
    assert client.post(f"/workspaces/{wid}/approvals/{ap['id']}/decision", json={"decision": "approve", "edited_payload": edited}).status_code == 200
    assert client.get(f"/workspaces/{wid}/calendar/{item.id}").json()["idea_json"]["creative"]["titles"][0]["title"] == "My own title"


def test_failing_guardrail_retries_with_feedback_then_escalates(client, db, env, monkeypatch):
    from app.gate import guardrails
    from app.gate.guardrails import GuardrailVerdict

    monkeypatch.setattr(guardrails, "rate", lambda c, r: GuardrailVerdict(score=0.2, feedback="sounds like a scam"))
    wid, _ = new_workspace(client, db, "high")
    rid = start(client, wid, make_item(db, wid)).json()["id"]
    assert client.get(f"/workspaces/{wid}/runs/{rid}").json()["status"] == "waiting_approval"
    assert env.rec.calls == 3 and "sounds like a scam" in env.rec.prompts[1]  # feedback reached the model


def test_params_are_validated_at_the_api(client, db, env):
    wid, _ = new_workspace(client, db, "medium")
    url = f"/workspaces/{wid}/runs"
    assert client.post(url, json={"workflow": "creative_for_item"}).status_code == 422
    assert client.post(url, json={"workflow": "creative_for_item", "params": {"calendar_item_id": "nope"}}).status_code == 422
    assert client.post(url, json={"workflow": "strategy_onboarding", "params": {"x": 1}}).status_code == 422


def test_cannot_generate_creative_for_another_workspaces_item(client, engine, db, env):
    wid_a, _ = new_workspace(client, db, "high", email="a@x.co")
    item_a = make_item(db, wid_a)
    other = make_client_for(engine, make_user(db, "b@x.co"))
    wid_b = other.post("/workspaces", json={"name": "B"}).json()["id"]
    other.patch(f"/workspaces/{wid_b}", json={"autonomy": "high"})
    rid = start(other, wid_b, item_a).json()["id"]
    run = other.get(f"/workspaces/{wid_b}/runs/{rid}").json()
    assert run["status"] == "failed" and "not found in this workspace" in run["error"]
    db.expire_all()
    assert db.get(m.CalendarItem, item_a.id).status == "planned"  # untouched
    assert env.rec.calls == 0  # no LLM spend for a foreign item


# ------------------------------------------------------------ thumbnails (opt-in)


class FakeImages:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt, aspect_ratio="16:9"):
        self.prompts.append(prompt)
        return b"png"


class FakeStore:
    def __init__(self):
        self.uploads = []

    def upload_bytes(self, data, workspace_id, kind, resource_type="image"):
        from app.integrations.storage import StoredAsset

        self.uploads.append((data, workspace_id, kind))
        return StoredAsset(public_id=f"creatorops/{workspace_id}/{kind}/abc", url="https://x/abc")


def test_thumbnail_is_generated_stored_and_linked_only_when_enabled(client, db, env, monkeypatch):
    images, store = FakeImages(), FakeStore()
    monkeypatch.setattr(creative_flow, "get_image_provider", lambda: images)
    monkeypatch.setattr(creative_flow, "get_asset_store", lambda: store)
    wid, _ = new_workspace(client, db, "high")

    item = make_item(db, wid)
    start(client, wid, item)
    assert images.prompts == []  # disabled by default

    monkeypatch.setattr(settings, "IMAGE_GEN_ENABLED", True)
    item2 = make_item(db, wid, "Second video")
    rid = start(client, wid, item2).json()["id"]
    assert client.get(f"/workspaces/{wid}/runs/{rid}").json()["status"] == "succeeded"
    assert images.prompts == ["before and after of a yellowed console"]
    asset = db.query(m.Asset).one()
    assert asset.kind == "thumbnail" and asset.source == "ai" and asset.workspace_id == uuid.UUID(wid)
    assert client.get(f"/workspaces/{wid}/calendar/{item2.id}").json()["idea_json"]["thumbnail_asset_id"] == str(asset.id)
    assert store.uploads[0][1:] == (uuid.UUID(wid), "thumbnail")
