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
        # Operations are kept in-process between submit/poll. Persisting the
        # operation name on the Run and rehydrating it is a TODO for the Celery task.
        self._operations: dict[str, Any] = {}

    def submit(self, request: VideoRequest) -> VideoJob:
        operation = self.client.models.generate_videos(
            model=request.model or settings.VIDEO_MODEL,
            prompt=request.prompts,
        )
        job_id = getattr(operation, "name", None) or str(id(operation))
        self._operations[job_id] = operation
        return VideoJob(
            job_id=job_id,
            provider=self.name,
            status=VideoJobStatus.RUNNING,
            estimated_cost_usd=self.estimate_cost_usd(request),
        )

    def poll(self, job: VideoJob) -> VideoJob:
        operation = self.client.operations.get(self._operations[job.job_id])
        self._operations[job.job_id] = operation
        if not getattr(operation, "done", False):
            return job.model_copy(update={"status": VideoJobStatus.RUNNING})
        if getattr(operation, "error", None):
            return job.model_copy(
                update={"status": VideoJobStatus.FAILED, "error": str(operation.error)}
            )
        return job.model_copy(update={"status": VideoJobStatus.SUCCEEDED})

    def fetch(self, job: VideoJob, dest_dir: Path, filename: str) -> Path:
        operation = self._operations[job.job_id]
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
