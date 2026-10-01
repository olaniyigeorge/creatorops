import asyncio

import pytest

from app.integrations import youtube as yt


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("@retrorepair", {"forHandle": "@retrorepair"}),
        ("retrorepair", {"forHandle": "@retrorepair"}),
        ("https://www.youtube.com/@retro.repair", {"forHandle": "@retro.repair"}),
        ("UC" + "a" * 22, {"id": "UC" + "a" * 22}),
        ("https://youtube.com/channel/UC" + "b" * 22, {"id": "UC" + "b" * 22}),
    ],
)
def test_parse_channel_ref(ref, expected):
    assert yt.parse_channel_ref(ref) == expected


@pytest.mark.parametrize("bad", ["", "ab", "foo/bar", "https://example.com/@x", "a b c", "@x&key=steal"])
def test_parse_channel_ref_rejects_garbage_and_injection(bad):
    with pytest.raises(ValueError):
        yt.parse_channel_ref(bad)


def _video(title, views=1000):
    return {"title": title, "avg_views_per_day": views, "relevance_score": views}


def test_no_api_key_degrades_gracefully():
    s = asyncio.run(yt.collect_signals("", "US", ["@x_chan"]))
    assert not s.available and "not configured" in s.errors[0]
    assert "profile only" in s.summary()


def test_one_failing_competitor_does_not_fail_the_rest(monkeypatch):
    async def trending(key, region_code, max_results):
        return [{"id": "1", "snippet": {"title": "T", "publishedAt": "2026-01-01T00:00:00Z"}, "statistics": {"viewCount": "10"}}]

    async def recent(key, ref, max_results=8):
        if ref == "@bad_chan":
            raise LookupError("nope")
        return "Good Channel", [_video("Fix a console")]

    monkeypatch.setattr(yt, "get_trending_videos", trending)
    monkeypatch.setattr(yt, "get_channel_recent_videos", recent)
    s = asyncio.run(yt.collect_signals("key", "US", ["@bad_chan", "@good_chan"]))
    assert s.available and list(s.competitors) == ["Good Channel"]
    assert s.errors == ["competitor @bad_chan: LookupError"]


def test_summary_escapes_third_party_titles():
    s = yt.MarketSignals(competitors={"C": [_video("<script>ignore previous</script>")]})
    out = s.summary()
    assert "<script>" not in out and "‹script›" in out


def test_recent_videos_pipeline_and_missing_channel(monkeypatch):
    calls = []

    async def fake(session, endpoint, params):
        calls.append(endpoint)
        if endpoint == "channels":
            if params.get("forHandle") == "@ghost_ch":
                return {"items": []}
            return {"items": [{"snippet": {"title": "Chan"}, "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]}
        if endpoint == "playlistItems":
            return {"items": [{"contentDetails": {"videoId": "v1"}}]}
        return {"items": [{"id": "v1", "snippet": {"title": "Vid", "publishedAt": "2026-01-01T00:00:00Z"}, "statistics": {"viewCount": "100"}}]}

    monkeypatch.setattr(yt, "_get_endpoint", fake)
    title, vids = asyncio.run(yt.get_channel_recent_videos("k", "@real_chan"))
    assert title == "Chan" and vids[0]["title"] == "Vid" and calls == ["channels", "playlistItems", "videos"]
    with pytest.raises(LookupError):
        asyncio.run(yt.get_channel_recent_videos("k", "@ghost_ch"))
