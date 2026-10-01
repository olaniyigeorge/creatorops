"""Guardrail scoring: rates generated content against the workspace rubric (LLM-as-judge)."""

from typing import List

from pydantic import BaseModel, Field

from app.llm.factory import structured_model


class Rubric(BaseModel):
    brand_voice: str = ""
    banned_topics: List[str] = Field(default_factory=list)
    extra_rules: List[str] = Field(default_factory=list)


class GuardrailVerdict(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    violations: List[str] = Field(default_factory=list)
    feedback: str = ""  # fed back to the generating agent on retry


_SYSTEM = (
    "You review content for a YouTube channel. Score 0-1 how well it follows the "
    "channel rubric and YouTube's content/community guidelines. List concrete "
    "violations and give actionable feedback."
)


def rate(content: str, rubric: Rubric) -> GuardrailVerdict:
    judge = structured_model(GuardrailVerdict, temperature=0.0)
    return judge.invoke(
        [
            ("system", _SYSTEM),
            ("human", f"Rubric:\n{rubric.model_dump_json(indent=2)}\n\nContent:\n{content}"),
        ]
    )
