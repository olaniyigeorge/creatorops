from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _clean_list(values: list[str], max_items: int, max_len: int) -> list[str]:
    out = []
    for v in values:
        v = v.strip()
        if v and len(v) <= max_len and v not in out:
            out.append(v)
    return out[:max_items]


class ChannelProfile(BaseModel):
    """Onboarding answers. Becomes the workspace brand profile and guardrail rubric."""

    channel_name: str = Field(min_length=1, max_length=200)
    goal: Literal["growth", "monetization", "engagement"]
    audience: str = Field(min_length=1, max_length=500)
    tone: str = Field(min_length=1, max_length=300)
    brand_voice: str = Field(default="", max_length=1000)
    niche_hint: Optional[str] = Field(default=None, max_length=200)
    banned_topics: list[str] = Field(default_factory=list, max_length=30)
    extra_rules: list[str] = Field(default_factory=list, max_length=30)
    competitors: list[str] = Field(default_factory=list, max_length=10)  # @handles, URLs or channel ids
    videos_per_week: int = Field(default=2, ge=1, le=14)
    region_code: str = Field(default="US", pattern=r"^[A-Za-z]{2}$")

    @field_validator("banned_topics", "extra_rules", mode="after")
    @classmethod
    def _clean_text_lists(cls, v):
        return _clean_list(v, 30, 300)

    @field_validator("competitors", mode="after")
    @classmethod
    def _clean_competitors(cls, v):
        return _clean_list(v, 10, 200)

    @field_validator("region_code", mode="after")
    @classmethod
    def _upper(cls, v):
        return v.upper()
