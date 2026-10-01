"""Asset storage behind a small interface. Cloudinary is the first implementation.

Not exercised against live Cloudinary in tests (a fake store is used)."""

import io
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.config import settings


@dataclass
class StoredAsset:
    public_id: str
    url: str


class AssetStore(ABC):
    @abstractmethod
    def upload_bytes(
        self, data: bytes, workspace_id: uuid.UUID, kind: str, resource_type: str = "image"
    ) -> StoredAsset: ...


class CloudinaryStore(AssetStore):
    def __init__(self, cloudinary_url: str | None = None):
        import cloudinary

        parsed = urlparse(cloudinary_url or settings.CLOUDINARY_URL)
        if parsed.scheme != "cloudinary" or not parsed.hostname:
            raise RuntimeError("CLOUDINARY_URL is not configured (cloudinary://key:secret@cloud)")
        cloudinary.config(
            cloud_name=parsed.hostname,
            api_key=parsed.username,
            api_secret=parsed.password,
            secure=True,
        )

    def upload_bytes(self, data, workspace_id, kind, resource_type="image") -> StoredAsset:
        import cloudinary.uploader

        res = cloudinary.uploader.upload(
            io.BytesIO(data),
            folder=f"creatorops/{workspace_id}/{kind}",
            resource_type=resource_type,
            type="authenticated",  # unpublished work is never publicly addressable
            tags=[str(workspace_id), kind],
        )
        return StoredAsset(public_id=res["public_id"], url=res["secure_url"])


def get_asset_store() -> AssetStore:
    return CloudinaryStore()
