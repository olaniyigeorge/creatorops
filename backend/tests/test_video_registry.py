import pytest

from app.core.config import settings
from app.video import registry


def test_disabled_by_default():
    with pytest.raises(RuntimeError):
        registry.get_video_provider()


def test_unknown_provider(monkeypatch):
    monkeypatch.setattr(settings, "VIDEO_GEN_ENABLED", True)
    with pytest.raises(ValueError):
        registry.get_video_provider("nope")
