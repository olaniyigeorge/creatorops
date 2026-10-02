"""Project Management agent: turns a calendar item into a brief an editor can work from."""

from typing import Callable, Optional

from langchain_core.prompts import ChatPromptTemplate

from app.agents.creative import _strip
from app.llm.factory import structured_model
from app.schemas.brief import BriefDraft, OutlineSection

_SYSTEM = (
    "You are a YouTube production manager. You write briefs that a freelance video "
    "editor can act on without asking questions: clear, specific and short."
)

_HUMAN = """Channel context:
{context}

Video idea:
- Title idea: {title}
- Hook: {hook}
- Keywords: {keywords}
- Format: {format}

Chosen creative (may be empty):
{creative}

Deadline: {due}

Reviewer feedback to address (may be empty): {feedback}

Write the brief: one-sentence objective; an outline of 3-8 sections (heading and notes on
pacing/on-screen content); a shot list of what footage or b-roll is needed; up to 5
reference styles (descriptions, not links you are unsure of); the deliverables expected
(for example final cut, captions file, thumbnail source); and short notes on tone and
things to avoid."""


def clean(draft: BriefDraft) -> BriefDraft:
    """Strip markup from model output (it ends up in HTML emails and the editor UI)."""
    return BriefDraft(
        objective=_strip(draft.objective),
        outline=[
            OutlineSection(heading=_strip(s.heading), notes=_strip(s.notes))
            for s in draft.outline
            if _strip(s.heading)
        ],
        shot_list=[_strip(s) for s in draft.shot_list if _strip(s)],
        references=[_strip(s) for s in draft.references if _strip(s)],
        deliverables=[_strip(s) for s in draft.deliverables if _strip(s)],
        editor_notes=_strip(draft.editor_notes),
    )


class ProjectManagerAgent:
    def __init__(self, model: Optional[Callable] = None):
        self._model = model

    def write_brief(
        self, context: str, idea: dict, due: Optional[str], feedback: Optional[str] = None
    ) -> BriefDraft:
        prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
        chain = prompt | (self._model or structured_model(BriefDraft))
        creative = idea.get("creative") or {}
        titles = [t.get("title", "") for t in creative.get("titles", [])][:3]
        raw: BriefDraft = chain.invoke(
            {
                "context": context,
                "title": idea.get("title", ""),
                "hook": idea.get("hook", ""),
                "keywords": ", ".join(idea.get("keywords", [])),
                "format": idea.get("format", "video"),
                "creative": ("titles: " + "; ".join(titles)) if titles else "none yet",
                "due": due or "not set",
                "feedback": feedback or "none",
            }
        )
        return clean(raw)
