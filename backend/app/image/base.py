"""Provider-agnostic image generation (thumbnails). Same shape as app.video."""

from abc import ABC, abstractmethod
from typing import Callable, Dict

from app.core.config import settings


class ImageProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, prompt: str, aspect_ratio: str = "16:9") -> bytes:
        """Returns encoded image bytes (PNG/JPEG)."""


_PROVIDERS: Dict[str, Callable[[], ImageProvider]] = {}


def register(name: str, factory: Callable[[], ImageProvider]) -> None:
    _PROVIDERS[name] = factory


def get_image_provider(name: str | None = None) -> ImageProvider:
    if not settings.IMAGE_GEN_ENABLED:
        raise RuntimeError("Image generation is disabled (IMAGE_GEN_ENABLED=false)")
    name = name or settings.IMAGE_PROVIDER
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown image provider '{name}'. Registered: {list(_PROVIDERS)}")
    return _PROVIDERS[name]()


def _register_builtin() -> None:
    def gemini_imagen() -> ImageProvider:
        from app.image.gemini_imagen import GeminiImagenProvider

        return GeminiImagenProvider()

    register("gemini_imagen", gemini_imagen)


_register_builtin()
