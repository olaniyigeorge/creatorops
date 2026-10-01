import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.agents import strategy as st
from app.db import models as m
from app.integrations.youtube import MarketSignals
from app.schemas.strategy import CalendarProposal, VideoIdeaDraft
from app.memory import service
from app.workflows import strategy_flow
from tests.conftest import PROFILE, make_client_for, make_user, new_workspace
from tests.fakes import calendar_ideas, niche_options, strategy_agent

# ------------------------------------------------------------------ pure logic


def test_scoring_follows_the_owners_goal():
    safe = st.NicheOption(name="a", rationale="", search_demand=0.5, competition=0.1, trend=0, monetization=0.2)
    money = st.NicheOption(name="b", rationale="", search_demand=0.5, competition=0.6, trend=0, monetization=0.95)
    assert st.score_option(safe, "growth") > st.score_option(money, "growth")
    assert st.score_option(money, "monetization") > st.score_option(safe, "monetization")


def test_rank_options_sorted_with_scores():
    ranked = st.rank_options(niche_options().options, "growth")
    assert [o["score"] for o in ranked] == sorted((o["score"] for o in ranked), reverse=True)
    assert ranked[0]["name"] == "Console repair"  # .68 vs .66 vs .52 for goal=growth


def test_videos_needed_and_schedule_are_computed_in_code():
    assert st.videos_needed(2) == 9 and st.videos_needed(14) == 60 and st.videos_needed(1) == 5
    start = datetime(2026, 10, 2, 15, tzinfo=timezone.utc)
    dates = st.schedule_dates(4, 2, start)
    assert dates[0] == start and [(d - start).days for d in dates] == [0, 4, 7, 11]  # ~every 3.5 days
    default = st.schedule_dates(1, 2)[0]
    assert default > datetime.now(timezone.utc) and default.hour == 15


def test_calendar_dedupes_truncates_and_ignores_model_dates():
    agent, _, cal = strategy_agent(calendar=lambda n: CalendarProposal(ideas=[
        VideoIdeaDraft(title=t) for t in ["A", "a", "B"] + [f"T{i}" for i in range(30)]
    ]))
    start = datetime(2026, 10, 2, 15, tzinfo=timezone.utc)
    entries = agent.propose_calendar("ctx", "sig", "niche", 2, start=start)
    assert [e.title for e in entries][:3] == ["A", "B", "T0"] and len(entries) == st.videos_needed(2)
    assert entries[0].scheduled_for == start


# -------------------------------------------------------------- the full workflow


@pytest.fixture
def agent_env(monkeypatch, worker):
    agent, niche_rec, cal_rec = strategy_agent()
    monkeypatch.setattr(strategy_flow, "get_agent", lambda: agent)
    signals = MarketSignals(trending=[{"title": "Console mod", "avg_views_per_day": 500, "relevance_score": 500}])
    fetched = []
    monkeypatch.setattr(strategy_flow, "fetch_signals", lambda profile: fetched.append(profile) or signals)
    return type("Env", (), {"niche": niche_rec, "calendar": cal_rec, "fetched": fetched, "worker": worker})


def start_strategy(client, wid):
    r = client.post(f"/workspaces/{wid}/runs", json={"workflow": "strategy_onboarding"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def run(client, wid, rid):
    return client.get(f"/workspaces/{wid}/runs/{rid}").json()


def pending(client, wid):
    return client.get(f"/workspaces/{wid}/approvals?status=pending").json()


def decide(client, wid, aid, **body):
    return client.post(f"/workspaces/{wid}/approvals/{aid}/decision", json=body)


def test_medium_autonomy_niche_then_calendar_with_admin_edit(client, db, agent_env):
    wid, _ = new_workspace(client, db, "medium")
    rid = start_strategy(client, wid)
    assert run(client, wid, rid)["status"] == "waiting_approval"

    [ap] = pending(client, wid)
    payload = ap["payload"]
    assert payload["selected"] == "Console repair"  # best score for goal=growth
    assert [o["name"] for o in payload["options"]][0] == "Console repair"
    assert "model estimates" in payload["estimates_note"] and "Console mod" in payload["evidence"]
    assert ap["action"]["gate_reason"].startswith("High-stakes")

    # the admin overrides the pick
    assert decide(client, wid, ap["id"], decision="approve", edited_payload={**payload, "selected": "Modding tutorials"}).status_code == 200
    ws = client.get(f"/workspaces/{wid}").json()
    assert ws["brand_json"]["niche"]["name"] == "Modding tutorials"

    [cal_ap] = pending(client, wid)  # now waiting on the calendar
    assert run(client, wid, rid)["status"] == "waiting_approval"
    items = cal_ap["payload"]["items"]
    assert len(items) == st.videos_needed(2) and cal_ap["payload"]["niche"] == "Modding tutorials"
    assert "Modding tutorials" in agent_env.calendar.prompts[0]  # calendar is built for the chosen niche

    assert decide(client, wid, cal_ap["id"], decision="approve").status_code == 200
    final = run(client, wid, rid)
    assert final["status"] == "succeeded"
    cal = client.get(f"/workspaces/{wid}/calendar").json()
    assert len(cal) == len(items) and all(c["status"] == "planned" for c in cal)
    dates = [c["scheduled_for"] for c in cal]
    assert dates == sorted(dates) and datetime.fromisoformat(dates[0]) > datetime.now(timezone.utc)


def test_signals_are_fetched_once_per_execution_not_per_step(client, db, agent_env):
    wid, _ = new_workspace(client, db, "high")
    rid = start_strategy(client, wid)
    assert run(client, wid, rid)["status"] == "succeeded" and len(agent_env.fetched) == 1


def test_high_autonomy_needs_no_approval_and_records_the_decision(client, db, agent_env):
    wid, _ = new_workspace(client, db, "high")
    rid = start_strategy(client, wid)
    assert run(client, wid, rid)["status"] == "succeeded" and pending(client, wid) == []
    assert len(client.get(f"/workspaces/{wid}/calendar").json()) == st.videos_needed(2)
    mem = db.query(m.MemoryItem).one()
    assert mem.kind == "decision" and "Niche selected automatically" in mem.text


def test_rejection_note_reaches_the_next_attempts_prompt(client, db, agent_env):
    wid, _ = new_workspace(client, db, "medium")
    rid = start_strategy(client, wid)
    [first] = pending(client, wid)
    decide(client, wid, first["id"], decision="reject", note="no gaming niches, we do woodworking")

    [second] = pending(client, wid)  # a fresh proposal, not the same approval
    assert second["id"] != first["id"] and run(client, wid, rid)["status"] == "waiting_approval"
    assert "no gaming niches, we do woodworking" not in agent_env.niche.prompts[0]
    assert "no gaming niches, we do woodworking" in agent_env.niche.prompts[1]  # learned from the note
    assert agent_env.niche.calls == 2


def test_three_rejections_stop_the_run_cleanly(client, db, agent_env):
    wid, _ = new_workspace(client, db, "medium")
    rid = start_strategy(client, wid)
    for _ in range(strategy_flow.MAX_ATTEMPTS):
        [ap] = pending(client, wid)
        decide(client, wid, ap["id"], decision="reject", note="try again")
    final = run(client, wid, rid)
    assert final["status"] == "succeeded" and db.query(m.Run).one().state_json["stopped"] == "niche_rejected"
    assert client.get(f"/workspaces/{wid}/calendar").json() == []


def test_invalid_admin_edits_are_rejected_before_anything_changes(client, db, agent_env):
    wid, _ = new_workspace(client, db, "medium")
    start_strategy(client, wid)
    [ap] = pending(client, wid)
    bad = decide(client, wid, ap["id"], decision="approve", edited_payload={**ap["payload"], "selected": "Not an option"})
    assert bad.status_code == 422 and "not one of the proposed options" in bad.json()["detail"]
    assert pending(client, wid)[0]["status"] == "pending"  # still decidable
    assert decide(client, wid, ap["id"], decision="approve").status_code == 200

    [cal] = pending(client, wid)
    assert decide(client, wid, cal["id"], decision="approve", edited_payload={"niche": "x", "items": []}).status_code == 422
    assert decide(client, wid, cal["id"], decision="approve", edited_payload={"niche": "x", "items": [{"title": "t" * 101, "scheduled_for": "2026-12-01T10:00:00Z"}]}).status_code == 422


def test_requires_onboarding(client, db, agent_env):
    wid, _ = new_workspace(client, db, "high", onboard=False)
    rid = start_strategy(client, wid)
    final = run(client, wid, rid)
    assert final["status"] == "failed" and "onboarding" in final["error"]


def test_market_data_outage_does_not_stop_strategy(client, db, agent_env, monkeypatch):
    monkeypatch.setattr(strategy_flow, "fetch_signals", lambda p: MarketSignals(errors=["YOUTUBE_API_KEY is not configured"]))
    wid, _ = new_workspace(client, db, "high")
    rid = start_strategy(client, wid)
    assert run(client, wid, rid)["status"] == "succeeded"
    assert "profile only" in agent_env.niche.prompts[0]  # the model is told there is no market data


def test_guardrail_failure_escalates_even_at_high_autonomy(client, db, agent_env):
    agent_env.worker.guardrail_score = 0.1
    wid, _ = new_workspace(client, db, "high")
    rid = start_strategy(client, wid)
    assert run(client, wid, rid)["status"] == "waiting_approval"
    [ap] = pending(client, wid)
    assert ap["action"]["gate_reason"] == "Guardrail failed after retries"
    assert agent_env.niche.calls == 3  # initial + 2 retries


def test_replanning_replaces_unstarted_items_but_keeps_work_in_progress(client, db, agent_env):
    wid, _ = new_workspace(client, db, "high")
    start_strategy(client, wid)
    items = client.get(f"/workspaces/{wid}/calendar").json()
    keep = db.get(m.CalendarItem, uuid.UUID(items[0]["id"]))
    keep.status = "creative_ready"
    db.commit()
    start_strategy(client, wid)
    after = client.get(f"/workspaces/{wid}/calendar").json()
    assert len(after) == st.videos_needed(2) + 1  # new plan + the preserved item
    assert items[0]["id"] in [c["id"] for c in after]


def test_calendar_visibility(client, engine, db, agent_env):
    wid, _ = new_workspace(client, db, "high")
    start_strategy(client, wid)
    first = client.get(f"/workspaces/{wid}/calendar").json()[0]["id"]
    token = client.post(f"/workspaces/{wid}/invitations", json={"email": "ed@x.co"}).json()["token"]
    ed = make_client_for(engine, make_user(db, "ed@x.co"))
    ed.post("/invitations/accept", json={"token": token})
    assert ed.get(f"/workspaces/{wid}/calendar/{first}").status_code == 200
    stranger = make_client_for(engine, make_user(db, "s@x.co"))
    assert stranger.get(f"/workspaces/{wid}/calendar").status_code == 404
    other = make_client_for(engine, make_user(db, "o@x.co"))
    owid = other.post("/workspaces", json={"name": "Other"}).json()["id"]
    assert other.get(f"/workspaces/{owid}/calendar/{first}").status_code == 404
    assert other.get(f"/workspaces/{owid}/calendar/not-a-uuid").status_code == 404
