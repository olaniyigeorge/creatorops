"""Communication agent: follow-ups to late editors and escalation notes to the owner."""

from typing import Callable, Optional

from langchain_core.prompts import ChatPromptTemplate

from app.agents.creative import _strip
from app.llm.factory import structured_model
from app.schemas.brief import FollowUpDraft

_SYSTEM = (
    "You write short, polite and direct work emails for a YouTube channel. You never "
    "invent facts, never threaten, and never mention payment terms."
)

_HUMAN = """Channel context:
{context}

Write an email to the {audience}.

Situation: the editing brief "{title}" was due {due} and is now {days_late} day(s) late. It
is currently "{status}". Follow-ups already sent to the editor: {sent}.

{audience_goal}

Reviewer feedback to address (may be empty): {feedback}

Keep it under 120 words, plain text, no placeholders, no links."""

_GOALS = {
    "editor": "Goal: ask for a status update and a realistic new date, and offer help if blocked.",
    "owner": "Goal: tell the channel owner the editor has not responded to repeated follow-ups and a decision is needed (wait, reassign, or move the date).",
}


class CommsAgent:
    def __init__(self, model: Optional[Callable] = None):
        self._model = model

    def follow_up(
        self,
        context: str,
        audience: str,
        title: str,
        due: str,
        days_late: int,
        status: str,
        sent: int,
        feedback: Optional[str] = None,
    ) -> FollowUpDraft:
        prompt = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])
        chain = prompt | (self._model or structured_model(FollowUpDraft))
        raw: FollowUpDraft = chain.invoke(
            {
                "context": context,
                "audience": audience,
                "audience_goal": _GOALS[audience],
                "title": title,
                "due": due,
                "days_late": days_late,
                "status": status,
                "sent": sent,
                "feedback": feedback or "none",
            }
        )
        # Keep paragraph breaks in the body; strip markup per line.
        body = "\n".join(_strip(line) for line in raw.body.splitlines() if _strip(line))
        return FollowUpDraft(subject=_strip(raw.subject), body=body)
