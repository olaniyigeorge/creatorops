from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from enum import Enum


class AgentStatus(str, Enum):
    """Status tracking for agent execution"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class Decision(BaseModel):
    """Code-driven decision with rationale"""

    approved: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    suggested_alternatives: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """Standardized result from any agent"""

    agent_name: str
    status: AgentStatus
    suggestions: List[Any]
    decision: Optional[Decision] = None
    selected_output: Optional[Any] = None
    execution_time: float
    timestamp: datetime = Field(default_factory=datetime.now)
    error_message: Optional[str] = None


# ==================== NICHE AGENT ====================


class NicheCandidate(BaseModel):
    name: str
    search_demand: float = Field(ge=0.0, le=1.0)
    trend_velocity: float = Field(ge=-1.0, le=1.0)
    competition_score: float = Field(ge=0.0, le=1.0)
    estimated_rpm: float = Field(ge=0.0)
    monetization_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NicheAgentState(BaseModel):
    """Sub-state for niche discovery agent"""

    candidates_from_api: List[NicheCandidate] = Field(default_factory=list)
    ranked_candidates: List[NicheCandidate] = Field(default_factory=list)
    decision: Optional[Decision] = None
    selected_niche: Optional[NicheCandidate] = None
    result: Optional[AgentResult] = None


# ==================== STRATEGY AGENT ====================


class VideoIdea(BaseModel):
    title: str
    hook: str
    target_keywords: List[str]
    estimated_views: int
    estimated_ctr: float = Field(ge=0.0, le=1.0)
    virality_score: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StrategyAgentState(BaseModel):
    """Sub-state for strategy agent"""

    llm_ideas: List[VideoIdea] = Field(default_factory=list)
    ranked_ideas: List[VideoIdea] = Field(default_factory=list)
    decision: Optional[Decision] = None
    selected_idea: Optional[VideoIdea] = None
    keywords: List[str] = Field(default_factory=list)
    result: Optional[AgentResult] = None


# ==================== SCRIPT AGENT ====================


class ScriptSection(BaseModel):
    section_type: Literal["hook", "intro", "body", "cta", "outro"]
    content: str
    duration_seconds: int
    engagement_hooks: List[str] = Field(default_factory=list)


class ScriptCandidate(BaseModel):
    full_script: str
    sections: List[ScriptSection]
    estimated_length: int  # seconds
    readability_score: float = Field(ge=0.0, le=1.0)
    engagement_score: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScriptAgentState(BaseModel):
    """Sub-state for script agent"""

    llm_scripts: List[ScriptCandidate] = Field(default_factory=list)
    decision: Optional[Decision] = None
    selected_script: Optional[ScriptCandidate] = None
    result: Optional[AgentResult] = None


# ==================== VIDEO AGENT ====================


class VideoAsset(BaseModel):
    asset_path: str
    duration: int
    resolution: str
    file_size: int  # bytes
    format: str
    thumbnail_path: Optional[str] = None
    quality_score: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VideoAgentState(BaseModel):
    """Sub-state for video production agent"""

    llm_suggestions: Dict[str, Any] = Field(default_factory=dict)  # Style, pacing, etc.
    decision: Optional[Decision] = None
    generated_asset: Optional[VideoAsset] = None
    result: Optional[AgentResult] = None


# ==================== PUBLISH AGENT ====================


class PublishMetadata(BaseModel):
    title: str
    description: str
    tags: List[str]
    category: str
    thumbnail_url: Optional[str] = None
    playlist_id: Optional[str] = None
    visibility: Literal["public", "unlisted", "private"]
    scheduled_time: Optional[datetime] = None


class PublishAgentState(BaseModel):
    """Sub-state for publish agent"""

    llm_metadata: List[PublishMetadata] = Field(default_factory=list)
    decision: Optional[Decision] = None
    selected_metadata: Optional[PublishMetadata] = None
    video_url: Optional[str] = None
    published: bool = False
    result: Optional[AgentResult] = None


# ==================== ANALYTICS AGENT ====================


class PerformanceMetrics(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    watch_time_hours: float = 0.0
    ctr: float = Field(ge=0.0, le=1.0, default=0.0)
    avg_view_duration: int = 0  # seconds
    revenue: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)


class AnalyticsInsight(BaseModel):
    insight_type: Literal["positive", "negative", "neutral"]
    message: str
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_action: Optional[str] = None


class AnalyticsAgentState(BaseModel):
    """Sub-state for analytics agent"""

    metrics: Optional[PerformanceMetrics] = None
    llm_insights: List[AnalyticsInsight] = Field(default_factory=list)
    decision: Optional[Decision] = None
    actionable_insights: List[AnalyticsInsight] = Field(default_factory=list)
    result: Optional[AgentResult] = None


# ==================== MAIN ORCHESTRATOR STATE ====================


class YouTubeAutomationState(BaseModel):
    """Main orchestrator state - aggregates all agent states"""

    workflow_id: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    current_stage: str = "initialized"

    # Agent sub-states
    niche_state: NicheAgentState = Field(default_factory=NicheAgentState)
    strategy_state: StrategyAgentState = Field(default_factory=StrategyAgentState)
    script_state: ScriptAgentState = Field(default_factory=ScriptAgentState)
    video_state: VideoAgentState = Field(default_factory=VideoAgentState)
    publish_state: PublishAgentState = Field(default_factory=PublishAgentState)
    analytics_state: AnalyticsAgentState = Field(default_factory=AnalyticsAgentState)

    # Global workflow state
    workflow_status: AgentStatus = AgentStatus.PENDING
    error_log: List[str] = Field(default_factory=list)
    execution_timeline: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)
