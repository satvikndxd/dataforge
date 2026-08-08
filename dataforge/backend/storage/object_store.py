"""Object storage abstraction.

Default backend: content-addressed files on the local filesystem under
``settings.storage_root`` (correct for self-hosted single-node deployments
and tests). Production deployments flip ``DATAFORGE_STORAGE_BACKEND=s3`` and
point the S3 vars at MinIO/S3 — call-sites are identical, only the store
implementation changes.

Keys are opaque, ``/``-separated paths scoped per tenant, e.g.::

    orgs/{org_id}/raw/{sha256[:32]}.bin
    orgs/{org_id}/exports/{export_id}.jsonl
"""
from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class ObjectStoreError(RuntimeError):
    """Raised when an object cannot be read or written."""


class ObjectStore:
    """Interface shared by all backends."""

    def put(self, key: str, data: bytes) -> str:
        raise NotImplementedError

    def get(self, key: str) -> bytes:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    # --- text conveniences -------------------------------------------------

    def put_text(self, key: str, text: str) -> str:
        return self.put(key, text.encode("utf-8"))

    def get_text(self, key: str) -> str:
        return self.get(key).decode("utf-8")

    # --- content addressing ------------------------------------------------

    @staticmethod
    def content_address(org_id: str, kind: str, data: bytes, ext: str) -> str:
        """Deterministic, tenant-scoped key for a blob: same bytes → same key."""
        digest = hashlib.sha256(data).hexdigest()
        return f"orgs/{org_id}/{kind}/{digest[:32]}.{ext}"


class LocalObjectStore(ObjectStore):
    """Filesystem-backed store rooted at ``settings.storage_root``."""

    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root.resolve()):
            raise ObjectStoreError(f"key escapes storage root: {key!r}")
        return path

    def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic on POSIX
        return key

    def get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise ObjectStoreError(f"object not found: {key!r}") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3ObjectStore(ObjectStore):
    """S3/MinIO-backed store. Requires ``boto3`` and the S3 env vars."""

    def __init__(self, endpoint: str | None, bucket: str,
                 access_key: str | None, secret_key: str | None):
        try:
            import boto3  # noqa: PLC0415 — optional dependency
        except ImportError as exc:  # pragma: no cover
            raise ObjectStoreError(
                "DATAFORGE_STORAGE_BACKEND=s3 requires boto3 (pip install boto3)"
            ) from exc
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def put(self, key: str, data: bytes) -> str:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def get(self, key: str) -> bytes:
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey as exc:
            raise ObjectStoreError(f"object not found: {key!r}") from exc
        return resp["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._client.exceptions.ClientError:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


_store: ObjectStore | None = None
_lock = threading.Lock()


def get_object_store() -> ObjectStore:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                settings = get_settings()
                if settings.storage_backend == "s3":
                    logger.info("object store: s3 bucket=%s endpoint=%s",
                                settings.s3_bucket, settings.s3_endpoint)
                    _store = S3ObjectStore(settings.s3_endpoint, settings.s3_bucket,
                                           settings.s3_access_key, settings.s3_secret_key)
                else:
                    logger.info("object store: local root=%s", settings.storage_root)
                    _store = LocalObjectStore(settings.storage_path)
    return _store


def reset_object_store() -> None:
    """Test helper: rebuild the store from current settings on next access."""
    global _store
    with _lock:
        _store = None
