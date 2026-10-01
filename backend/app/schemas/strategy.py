"""Pydantic contracts for the Strategy Engine. LLM output is validated against these."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator

MAX_CALENDAR_ITEMS = 60


class NicheOption(BaseModel):
    """One candidate niche. The four scores are the model's own estimates, grounded
    on the supplied market data where available; they are not measured values."""

    name: str = Field(min_length=1, max_length=120)
    rationale: str = Field(max_length=1000)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    search_demand: float = Field(ge=0, le=1)
    competition: float = Field(ge=0, le=1)
    trend: float = Field(ge=-1, le=1)
    monetization: float = Field(ge=0, le=1)


class NicheProposal(BaseModel):
    options: list[NicheOption] = Field(min_length=2, max_length=6)


class VideoIdeaDraft(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    hook: str = Field(default="", max_length=500)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    format: str = Field(default="video", max_length=40)


class CalendarProposal(BaseModel):
    ideas: list[VideoIdeaDraft] = Field(min_length=1, max_length=MAX_CALENDAR_ITEMS)


class CalendarEntry(VideoIdeaDraft):
    scheduled_for: datetime

    @field_validator("scheduled_for", mode="after")
    @classmethod
    def _utc(cls, v):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


class NichePayload(BaseModel):
    """What an approval of SET_STRATEGY executes. Admins may edit `selected`."""

    selected: str
    options: list[dict]
    evidence: str = ""
    estimates_note: str = ""


class CalendarPayload(BaseModel):
    niche: str
    items: list[CalendarEntry] = Field(min_length=1, max_length=MAX_CALENDAR_ITEMS)


class TitleOption(BaseModel):
    title: str
    angle: str = ""


class CreativePackage(BaseModel):
    titles: list[TitleOption] = Field(min_length=1, max_length=8)
    description: str
    tags: list[str] = Field(default_factory=list)
    thumbnail_concepts: list[str] = Field(default_factory=list, max_length=4)
    video_plan: list[str] = Field(default_factory=list, max_length=12)  # scene prompts, for M5


class CreativePayload(BaseModel):
    kind: str = "creative_package"
    calendar_item_id: str
    package: CreativePackage


class ThumbnailPayload(BaseModel):
    kind: str = "thumbnail"
    calendar_item_id: str
    prompt: str = Field(min_length=1, max_length=1500)
