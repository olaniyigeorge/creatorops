import aiohttp
import asyncio
from datetime import datetime, timezone
from collections import Counter
import math
import re

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3/videos"
STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "for",
    "on",
    "with",
    "this",
    "that",
    "is",
    "are",
    "be",
    "by",
    "from",
    "how",
    "what",
    "you",
    "your",
    "it",
    "video",
    "videos",
}


def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return 0


def _days_since(published_at_iso):
    try:
        published = datetime.fromisoformat(published_at_iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - published
        days = max(1.0, delta.total_seconds() / 86400.0)
        return days
    except Exception:
        return 1.0


async def _fetch_json(session, params):
    async with session.get(YOUTUBE_API_URL, params=params) as resp:
        resp.raise_for_status()
        return await resp.json()


async def get_trending_videos(api_key, region_code="US", max_results=10):
    """
    Fetch trending videos (mostPopular) with snippet,contentDetails,statistics.
    Returns list of raw items as returned by the API.
    """
    params = {
        "part": "snippet,contentDetails,statistics",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": str(max_results),
        "key": api_key,
    }
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, params)
    return data.get("items", [])


async def fetch_videos_by_ids(api_key, video_ids):
    """
    Fetch videos using their IDs (comma-separated list or list).
    Returns list of items.
    """
    if isinstance(video_ids, (list, tuple)):
        video_ids = ",".join(video_ids)
    params = {
        "part": "snippet,contentDetails,statistics",
        "id": video_ids,
        "maxResults": "50",
        "key": api_key,
    }
    async with aiohttp.ClientSession() as session:
        data = await _fetch_json(session, params)
    return data.get("items", [])


def compute_relevance_for_item(item):
    """
    Compute metrics and a relevance score for a single video item.
    Returns a dict with metrics.
    """
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    views = _safe_int(stats.get("viewCount"))
    likes = _safe_int(stats.get("likeCount"))
    comments = _safe_int(stats.get("commentCount"))

    published_at = snippet.get("publishedAt", "")
    days = _days_since(published_at)

    avg_views_per_day = views / days

    like_ratio = (likes / views) if views > 0 else 0.0
    comment_ratio = (comments / views) if views > 0 else 0.0

    # Simple weighted relevance score (tweak weights as needed)
    # - avg views per day matters most
    # - like ratio and comment ratio improve relevance
    score = (
        avg_views_per_day * 0.7 + like_ratio * 1000 * 0.2 + comment_ratio * 1000 * 0.1
    )
    score = float(score)

    return {
        "videoId": item.get("id"),
        "title": snippet.get("title"),
        "publishedAt": published_at,
        "views": views,
        "likes": likes,
        "comments": comments,
        "avg_views_per_day": avg_views_per_day,
        "like_ratio": like_ratio,
        "comment_ratio": comment_ratio,
        "relevance_score": score,
        "tags": snippet.get("tags", []) or [],
        "categoryId": snippet.get("categoryId"),
    }


# def generate_niche_ideas_from_items(items, top_n=5, min_count=2):
#     """
#     Generate simple niche ideas from trending videos by extracting frequent keywords and tag combos.
#     Returns list of short niche idea strings.
#     """
#     words = []
#     tag_phrases = []
#     for it in items:
#         title = (it.get("title") or "").lower()
#         # split title into words, keep alphanumerics
#         tokens = re.findall(r"\b[a-z0-9]{3,}\b", title)
#         words.extend([t for t in tokens if t not in STOPWORDS])

#         for tag in (it.get("tags") or []):
#             tag_norm = tag.lower().strip()
#             if len(tag_norm) >= 3:
#                 tag_phrases.append(tag_norm)

#     word_counts = Counter(words)
#     tag_counts = Counter(tag_phrases)

#     ideas = []
#     # top keywords
#     for word, cnt in word_counts.most_common(top_n * 2):
#         if cnt >= min_count:
#             ideas.append(f"{word} tutorials" if word.isalpha() else word)
#         if len(ideas) >= top_n:
#             break

#     # if not enough, add tag-based ideas
#     if len(ideas) < top_n:
#         for tag, cnt in tag_counts.most_common(top_n * 2):
#             if cnt >= min_count:
#                 ideas.append(f"{tag} niche")
#             if len(ideas) >= top_n:
#                 break

#     # fallback: return unique short phrases
#     return list(dict.fromkeys(ideas))[:top_n]


# # Example orchestration function
# async def analyze_trending_and_generate_niches(api_key, region_code="US", max_results=20, niche_count=5):
#     trending = await get_trending_videos(api_key, region_code=region_code, max_results=max_results)
#     metrics = [compute_relevance_for_item(it) for it in trending]
#     # sort by relevance_score desc
#     metrics_sorted = sorted(metrics, key=lambda x: x["relevance_score"], reverse=True)
#     # generate niche ideas from the top N trending items (use titles/tags)
#     top_items_for_ideas = metrics_sorted[:max(5, int(len(metrics_sorted) * 0.2))]
#     niche_ideas = generate_niche_ideas_from_items(top_items_for_ideas, top_n=niche_count)
#     return {"metrics": metrics_sorted, "niche_ideas": niche_ideas}
