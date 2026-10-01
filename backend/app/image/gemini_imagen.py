"""Imagen adapter (google-genai). Not exercised against the live API in tests."""

from typing import Any, Optional

from app.core.config import settings
from app.image.base import ImageProvider


class GeminiImagenProvider(ImageProvider):
    name = "gemini_imagen"

    def __init__(self, api_key: Optional[str] = None, client: Optional[Any] = None):
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key or settings.GEMINI_API_KEY)
        self.client = client

    def generate(self, prompt: str, aspect_ratio: str = "16:9") -> bytes:
        from google.genai import types

        result = self.client.models.generate_images(
            model=settings.IMAGE_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio=aspect_ratio),
        )
        images = getattr(result, "generated_images", None)
        if not images:
            # Usually a safety filter; surface it rather than saving nothing.
            raise RuntimeError("Image provider returned no image (possibly blocked by safety filters)")
        return images[0].image.image_bytes
