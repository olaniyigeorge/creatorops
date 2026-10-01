import sys
import types
import uuid

import pytest

from app.core.config import settings
from app.image import base as image_base
from app.image.gemini_imagen import GeminiImagenProvider
from app.integrations.storage import CloudinaryStore


def test_image_gen_is_off_by_default_and_unknown_provider_is_an_error(monkeypatch):
    with pytest.raises(RuntimeError, match="disabled"):
        image_base.get_image_provider()
    monkeypatch.setattr(settings, "IMAGE_GEN_ENABLED", True)
    with pytest.raises(ValueError, match="Unknown image provider"):
        image_base.get_image_provider("nope")


class FakeModels:
    def __init__(self, images):
        self.images, self.kwargs = images, None

    def generate_images(self, **kw):
        self.kwargs = kw
        return types.SimpleNamespace(generated_images=self.images)


def test_imagen_returns_bytes_and_asks_for_16_9():
    img = types.SimpleNamespace(image=types.SimpleNamespace(image_bytes=b"\x89PNG"))
    client = types.SimpleNamespace(models=FakeModels([img]))
    assert GeminiImagenProvider(client=client).generate("a thumbnail") == b"\x89PNG"
    cfg = client.models.kwargs["config"]
    assert cfg.aspect_ratio == "16:9" and cfg.number_of_images == 1


def test_imagen_empty_result_is_surfaced_not_swallowed():
    client = types.SimpleNamespace(models=FakeModels([]))
    with pytest.raises(RuntimeError, match="safety"):
        GeminiImagenProvider(client=client).generate("x")


def test_cloudinary_uploads_private_into_a_per_workspace_folder(monkeypatch):
    seen = {}
    cfg = {}
    uploader = types.SimpleNamespace(upload=lambda f, **kw: seen.update(kw, data=f.read()) or {"public_id": "p1", "secure_url": "https://c/p1"})
    fake = types.ModuleType("cloudinary")
    fake.config = lambda **kw: cfg.update(kw)
    fake.uploader = uploader
    monkeypatch.setitem(sys.modules, "cloudinary", fake)
    monkeypatch.setitem(sys.modules, "cloudinary.uploader", uploader)

    ws = uuid.uuid4()
    store = CloudinaryStore("cloudinary://key:secret@mycloud")
    out = store.upload_bytes(b"img", ws, "thumbnail")
    assert cfg == {"cloud_name": "mycloud", "api_key": "key", "api_secret": "secret", "secure": True}
    assert out.public_id == "p1"
    assert seen["folder"] == f"creatorops/{ws}/thumbnail" and seen["type"] == "authenticated"
    assert seen["data"] == b"img" and str(ws) in seen["tags"]


def test_cloudinary_requires_configuration(monkeypatch):
    monkeypatch.setitem(sys.modules, "cloudinary", types.ModuleType("cloudinary"))
    with pytest.raises(RuntimeError, match="CLOUDINARY_URL"):
        CloudinaryStore("")
