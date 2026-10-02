"""Fake chat models: RunnableLambdas that return a Pydantic object and record the prompt."""

from langchain_core.runnables import RunnableLambda

from app.agents.strategy import StrategyAgent
from app.schemas.strategy import (
    CalendarProposal,
    CreativePackage,
    NicheOption,
    NicheProposal,
    TitleOption,
    VideoIdeaDraft,
)


class Recorder:
    def __init__(self, make):
        self.prompts: list[str] = []
        self.calls = 0
        self._make = make
        self.model = RunnableLambda(self._invoke)

    def _invoke(self, prompt_value):
        self.prompts.append(prompt_value.to_string())
        self.calls += 1
        return self._make(self.calls)


def niche_options(n=1):
    return NicheProposal(
        options=[
            NicheOption(name="Console repair", rationale="steady demand", keywords=["repair"], search_demand=0.8, competition=0.4, trend=0.3, monetization=0.6),
            NicheOption(name="Retro gaming news", rationale="crowded", keywords=["news"], search_demand=0.9, competition=0.9, trend=0.1, monetization=0.4),
            NicheOption(name="Modding tutorials", rationale="engaged audience", keywords=["mods"], search_demand=0.6, competition=0.3, trend=0.5, monetization=0.5),
        ]
    )


def calendar_ideas(n=1, count=20):
    return CalendarProposal(
        ideas=[VideoIdeaDraft(title=f"Idea {i}", hook=f"hook {i}", keywords=["k"], format="tutorial") for i in range(count)]
    )


def creative(n=1):
    return CreativePackage(
        titles=[TitleOption(title="Fix a yellowed console in 10 minutes", angle="speed")],
        description="Learn the safe way to retrobright.\n\nSteps inside.",
        tags=["retrobright", "console repair"],
        thumbnail_concepts=["before and after of a yellowed console"],
        video_plan=["close up of the console", "applying the gel"],
    )


def strategy_agent(niche=niche_options, calendar=calendar_ideas):
    n, c = Recorder(niche), Recorder(calendar)
    return StrategyAgent(niche_model=n.model, calendar_model=c.model), n, c


def brief_draft(n=1):
    from app.schemas.brief import BriefDraft, OutlineSection

    return BriefDraft(
        objective="Cut a 10 minute tutorial on retrobrighting",
        outline=[OutlineSection(heading="Hook", notes="show the yellowed shell first"), OutlineSection(heading="Steps", notes="gel, UV, rinse")],
        shot_list=["close up of the shell", "applying gel"],
        references=["fast cuts, warm colour grade"],
        deliverables=["final cut", "captions file"],
        editor_notes="Friendly tone. <b>No</b> hype.",
    )


def followup(n=1):
    from app.schemas.brief import FollowUpDraft

    return FollowUpDraft(subject=f"Checking in on your brief (#{n})", body="Hi,\nCould you share a status and a new date?\nThanks")
