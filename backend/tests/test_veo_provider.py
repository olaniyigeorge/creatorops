"""GeminiVeoProvider against a fake client: jobs must survive a worker restart."""

from pathlib import Path

from app.video.base import VideoJobStatus, VideoRequest
from app.video.gemini_veo import GeminiVeoProvider


class FakeVideo:
    def save(self, path):
        Path(path).write_bytes(b"mp4-bytes")


class FakeOp:
    def __init__(self, name, done=False):
        self.name, self.done, self.error = name, done, None
        self.response = type("R", (), {"generated_videos": [type("G", (), {"video": FakeVideo()})()]})()


class FakeClient:
    """Server-side state lives here, like the real API: independent of any provider instance."""

    def __init__(self):
        self.finished = set()
        self.models = type("M", (), {"generate_videos": lambda s, model, prompt: FakeOp("operations/job-1")})()
        self.operations = type("O", (), {"get": lambda s, op: FakeOp(op.name, done=op.name in self.finished)})()
        self.files = type("F", (), {"download": lambda s, file: None})()


def test_job_survives_provider_restart(tmp_path):
    client = FakeClient()
    job = GeminiVeoProvider(client=client).submit(VideoRequest(prompts=[{"text": "a cat"}]))
    assert job.job_id == "operations/job-1" and job.status is VideoJobStatus.RUNNING

    # A different worker process: fresh instance, empty cache, only the stored job.
    restarted = GeminiVeoProvider(client=client)
    assert restarted.poll(job).status is VideoJobStatus.RUNNING
    client.finished.add("operations/job-1")
    done = restarted.poll(job)
    assert done.status is VideoJobStatus.SUCCEEDED
    assert restarted.fetch(done, tmp_path, "v.mp4").read_bytes() == b"mp4-bytes"


def test_fetch_on_a_fresh_instance_refreshes_the_operation(tmp_path):
    client = FakeClient()
    job = GeminiVeoProvider(client=client).submit(VideoRequest(prompts=[{"text": "x"}]))
    client.finished.add(job.job_id)
    assert GeminiVeoProvider(client=client).fetch(job, tmp_path, "v.mp4").exists()


def test_submit_without_operation_name_is_an_error():
    client = FakeClient()
    client.models.generate_videos = lambda model, prompt: type("Op", (), {"name": None})()
    import pytest
    with pytest.raises(RuntimeError, match="no operation name"):
        GeminiVeoProvider(client=client).submit(VideoRequest(prompts=[{"text": "x"}]))


def test_cost_estimate_needs_a_configured_price(monkeypatch):
    from app.core.config import settings

    p = GeminiVeoProvider(client=FakeClient())
    req = VideoRequest(prompts=[{"text": "x"}], duration_seconds=10)
    monkeypatch.setattr(settings, "VIDEO_COST_PER_SECOND_USD", 0.0)
    assert p.estimate_cost_usd(req) is None  # unknown -> the gate blocks it
    monkeypatch.setattr(settings, "VIDEO_COST_PER_SECOND_USD", 0.25)
    assert p.estimate_cost_usd(req) == 2.5
    assert p.estimate_cost_usd(VideoRequest(prompts=[{"text": "x"}])) == 2.0  # default 8s
