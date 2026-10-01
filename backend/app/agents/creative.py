"""Creative Engine: titles, description, tags, thumbnail concepts, video plan.

YouTube's hard limits are enforced in code after generation: models ignore length
limits often enough that trusting them would ship rejected uploads.
"""

import re
from typing import Callable, Optional

from langchain_core.prompts import ChatPromptTemplate

from app.llm.factory import structured_model
from app.schemas.strategy import CreativePackage, TitleOption

MAX_TITLE = 100
MAX_DESCRIPTION_BYTES = 5000
MAX_TAG_LEN = 30
MAX_TAGS_TOTAL = 480  # YouTube allows 500 characters in total; leave headroom for separators

_SYSTEM = (
    "You are a YouTube creative lead. You write titles, descriptions and thumbnail "
    "concepts that are honest (no misleading claims), on-brand and optimised for "
    "search and click-through."
)

_HUMAN = """Channel context:
{context}

Video idea:
- Title idea: {title}
- Hook: {hook}
- Keywords: {keywords}
- Format: {format}

Reviewer feedback to address (may be empty): {feedback}

Produce: 3-5 distinct title options (max 100 characters, no angle brackets) each with the
angle it takes; a description (first two lines must work as the preview, then context,
then a call to action); up to 15 short tags; 1-3 thumbnail concepts written as image
prompts (no text-heavy designs); and 3-8 scene prompts for an optional AI video draft."""


def _strip(text: str) -> str:
    """Remove HTML-ish tags first (so '<b>it</b>' becomes 'it'), then any stray angle
    bracket, which YouTube rejects in titles, descriptions and tags."""
    text = re.sub(r"</?[A-Za-z][^>]*>", "", text)
    return re.sub(r"\s+", " ", text.replace("<", "").replace(">", "")).strip()


def enforce_limits(pkg: CreativePackage) -> CreativePackage:
    titles, seen = [], set()
    for t in pkg.titles:
        title = _strip(t.title)
        if title and len(title) <= MAX_TITLE and title.lower() not in seen:
            seen.add(title.lower())
            titles.append(TitleOption(title=title, angle=t.angle))
    if not titles:
        raise ValueError("No title within YouTube's 100-character limit")

    desc = _strip(pkg.description).encode("utf-8")[:MAX_DESCRIPTION_BYTES]
    description = desc.decode("utf-8", errors="ignore")

    tags, total, seen_tags = [], 0, set()
    for raw in pkg.tags:
        tag = _strip(raw).replace(",", "")
        if not tag or len(tag) > MAX_TAG_LEN or tag.lower() in seen_tags:
            continue
        if total + len(tag) + 1 > MAX_TAGS_TOTAL:
            break
        seen_tags.add(tag.lower())
        tags.append(tag)
        total += len(tag) + 1

    return CreativePackage(
        titles=titles,
        description=description,
        tags=tags,
        thumbnail_concepts=[_strip(c) for c in pkg.thumbnail_concepts if _strip(c)],
        video_plan=[_strip(s) for s in pkg.video_plan if _strip(s)],
    )


class CreativeAgent:
    def __init__(self, model: Optional[Callable] = None):
        self._model = model

    def generate(self, context: str, idea: dict, feedback: Optional[str] = None) -> CreativePackage:
        prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
        chain = prompt | (self._model or structured_model(CreativePackage))
        raw: CreativePackage = chain.invoke(
            {
                "context": context,
                "title": idea.get("title", ""),
                "hook": idea.get("hook", ""),
                "keywords": ", ".join(idea.get("keywords", [])),
                "format": idea.get("format", "video"),
                "feedback": feedback or "none",
            }
        )
        return enforce_limits(raw)
