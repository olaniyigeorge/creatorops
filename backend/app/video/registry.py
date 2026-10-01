from typing import Callable, Dict

from app.core.config import settings
from app.video.base import VideoProvider

_PROVIDERS: Dict[str, Callable[[], VideoProvider]] = {}


def register(name: str, factory: Callable[[], VideoProvider]) -> None:
    _PROVIDERS[name] = factory


def get_video_provider(name: str | None = None) -> VideoProvider:
    if not settings.VIDEO_GEN_ENABLED:
        raise RuntimeError("Video generation is disabled (VIDEO_GEN_ENABLED=false)")
    name = name or settings.VIDEO_PROVIDER
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown video provider '{name}'. Registered: {list(_PROVIDERS)}")
    return _PROVIDERS[name]()


def _register_builtin() -> None:
    def gemini_veo() -> VideoProvider:
        from app.video.gemini_veo import GeminiVeoProvider

        return GeminiVeoProvider()

    register("gemini_veo", gemini_veo)


_register_builtin()
