"""Gemini Veo adapter for the VideoProvider contract (google-genai SDK)."""

import logging
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.video.base import (
    VideoJob,
    VideoJobStatus,
    VideoProvider,
    VideoRequest,
)

logger = logging.getLogger(__name__)


class GeminiVeoProvider(VideoProvider):
    name = "gemini_veo"

    def __init__(self, api_key: Optional[str] = None, client: Optional[Any] = None):
        if client is None:
            from google import genai  # imported lazily: optional dependency

            client = genai.Client(api_key=api_key or settings.GEMINI_API_KEY)
        self.client = client
        # In-process cache only. The provider-side job id (the operation name) is the
        # source of truth and is stored on the Run, so any worker or a restarted
        # process can poll and fetch by rebuilding the operation from that id.
        self._operations: dict[str, Any] = {}

    def _operation(self, job: VideoJob) -> Any:
        op = self._operations.get(job.job_id)
        if op is None:
            from google.genai import types

            op = types.GenerateVideosOperation(name=job.job_id)
        return op

    def estimate_cost_usd(self, request: VideoRequest) -> Optional[float]:
        rate = settings.VIDEO_COST_PER_SECOND_USD
        if rate <= 0:
            return None  # unpriced: the gate blocks generation rather than assume it is free
        return round(rate * (request.duration_seconds or settings.VIDEO_DEFAULT_SECONDS), 4)

    def submit(self, request: VideoRequest) -> VideoJob:
        operation = self.client.models.generate_videos(
            model=request.model or settings.VIDEO_MODEL,
            prompt=request.prompts,
        )
        job_id = getattr(operation, "name", None)
        if not job_id:
            raise RuntimeError("Provider returned no operation name; cannot track this job")
        self._operations[job_id] = operation
        return VideoJob(
            job_id=job_id,
            provider=self.name,
            status=VideoJobStatus.RUNNING,
            estimated_cost_usd=self.estimate_cost_usd(request),
        )

    def poll(self, job: VideoJob) -> VideoJob:
        operation = self.client.operations.get(self._operation(job))
        self._operations[job.job_id] = operation
        if not getattr(operation, "done", False):
            return job.model_copy(update={"status": VideoJobStatus.RUNNING})
        if getattr(operation, "error", None):
            return job.model_copy(
                update={"status": VideoJobStatus.FAILED, "error": str(operation.error)}
            )
        return job.model_copy(update={"status": VideoJobStatus.SUCCEEDED})

    def fetch(self, job: VideoJob, dest_dir: Path, filename: str) -> Path:
        operation = self._operations.get(job.job_id)
        if operation is None or not getattr(operation, "done", False):
            operation = self.client.operations.get(self._operation(job))
            self._operations[job.job_id] = operation
        videos = getattr(getattr(operation, "response", None), "generated_videos", None)
        if not videos:
            raise RuntimeError("No generated videos in operation response")
        video = videos[0].video
        dest_dir.mkdir(parents=True, exist_ok=True)
        out = dest_dir / filename
        self.client.files.download(file=video)
        video.save(str(out))
        logger.info("Generated video saved to %s", out)
        return out
