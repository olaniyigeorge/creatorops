"""Provider-agnostic video generation contract.

Generation is asynchronous and expensive, so the contract is submit / poll / fetch
(a Celery task drives it) rather than one blocking call. Providers register
themselves in `registry`; the rest of the system only sees `VideoProvider`.
"""

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VideoJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VideoRequest(BaseModel):
    prompts: List[Dict[str, Any]]  # ordered scene/frame prompts
    aspect_ratio: str = "16:9"
    duration_seconds: Optional[int] = None
    model: Optional[str] = None  # provider default when None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VideoJob(BaseModel):
    job_id: str  # provider-side id, stored on the Run so polling survives restarts
    provider: str
    status: VideoJobStatus = VideoJobStatus.PENDING
    error: Optional[str] = None
    estimated_cost_usd: Optional[float] = None


class VideoProvider(ABC):
    name: str

    @abstractmethod
    def submit(self, request: VideoRequest) -> VideoJob: ...

    @abstractmethod
    def poll(self, job: VideoJob) -> VideoJob: ...

    @abstractmethod
    def fetch(self, job: VideoJob, dest_dir: Path, filename: str) -> Path: ...

    def estimate_cost_usd(self, request: VideoRequest) -> Optional[float]:
        """Used by the gate to enforce per-workspace budgets. None = unknown."""
        return None
