"""Object storage abstraction.

Default backend: content-addressed files on the local filesystem under
``settings.storage_root`` (correct for self-hosted single-node deployments
and tests). Production deployments flip ``DATAFORGE_STORAGE_BACKEND`` to
``s3`` (AWS S3 / MinIO), ``gcs`` (Google Cloud Storage), or ``azure``
(Azure Blob Storage) and set the matching env vars — call-sites are
identical, only the store implementation changes.

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
                 access_key: str | None, secret_key: str | None,
                 region: str | None = None):
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
            region_name=region,
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


class GCSObjectStore(ObjectStore):
    """Google Cloud Storage-backed store. Requires ``google-cloud-storage``.

    Auth: explicit service-account file via ``DATAFORGE_GCS_CREDENTIALS_FILE``,
    otherwise Application Default Credentials (``GOOGLE_APPLICATION_CREDENTIALS``,
    workload identity, gcloud login, …).
    """

    def __init__(self, bucket: str, project: str | None = None,
                 credentials_file: str | None = None):
        try:
            from google.cloud import storage as gcs  # noqa: PLC0415 — optional dependency
        except ImportError as exc:  # pragma: no cover
            raise ObjectStoreError(
                "DATAFORGE_STORAGE_BACKEND=gcs requires google-cloud-storage "
                "(pip install google-cloud-storage)"
            ) from exc
        if credentials_file:
            client = gcs.Client.from_service_account_json(credentials_file, project=project)
        else:
            client = gcs.Client(project=project)
        self._bucket = client.bucket(bucket)

    def put(self, key: str, data: bytes) -> str:
        self._bucket.blob(key).upload_from_string(data)
        return key

    def get(self, key: str) -> bytes:
        from google.cloud.exceptions import NotFound  # noqa: PLC0415

        try:
            return self._bucket.blob(key).download_as_bytes()
        except NotFound as exc:
            raise ObjectStoreError(f"object not found: {key!r}") from exc

    def exists(self, key: str) -> bool:
        return self._bucket.blob(key).exists()

    def delete(self, key: str) -> None:
        from google.cloud.exceptions import NotFound  # noqa: PLC0415

        try:
            self._bucket.blob(key).delete()
        except NotFound:
            pass


class AzureBlobObjectStore(ObjectStore):
    """Azure Blob Storage-backed store. Requires ``azure-storage-blob``.

    Auth: a full connection string, or ``account_url`` + ``account_key``
    (``account_url`` alone falls back to ``DefaultAzureCredential`` when
    ``azure-identity`` is installed — managed identity / az login).
    """

    def __init__(self, container: str, connection_string: str | None = None,
                 account_url: str | None = None, account_key: str | None = None):
        try:
            from azure.storage.blob import BlobServiceClient  # noqa: PLC0415 — optional dependency
        except ImportError as exc:  # pragma: no cover
            raise ObjectStoreError(
                "DATAFORGE_STORAGE_BACKEND=azure requires azure-storage-blob "
                "(pip install azure-storage-blob)"
            ) from exc
        if connection_string:
            service = BlobServiceClient.from_connection_string(connection_string)
        elif account_url and account_key:
            service = BlobServiceClient(account_url=account_url, credential=account_key)
        elif account_url:
            try:
                from azure.identity import DefaultAzureCredential  # noqa: PLC0415
            except ImportError as exc:  # pragma: no cover
                raise ObjectStoreError(
                    "Azure backend without an account key requires azure-identity "
                    "(pip install azure-identity)"
                ) from exc
            service = BlobServiceClient(account_url=account_url,
                                        credential=DefaultAzureCredential())
        else:
            raise ObjectStoreError(
                "Azure backend needs DATAFORGE_AZURE_CONNECTION_STRING or "
                "DATAFORGE_AZURE_ACCOUNT_URL"
            )
        self._container = service.get_container_client(container)

    def put(self, key: str, data: bytes) -> str:
        self._container.upload_blob(name=key, data=data, overwrite=True)
        return key

    def get(self, key: str) -> bytes:
        from azure.core.exceptions import ResourceNotFoundError  # noqa: PLC0415

        try:
            return self._container.download_blob(key).readall()
        except ResourceNotFoundError as exc:
            raise ObjectStoreError(f"object not found: {key!r}") from exc

    def exists(self, key: str) -> bool:
        return self._container.get_blob_client(key).exists()

    def delete(self, key: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError  # noqa: PLC0415

        try:
            self._container.delete_blob(key)
        except ResourceNotFoundError:
            pass


_store: ObjectStore | None = None
_lock = threading.Lock()


def get_object_store() -> ObjectStore:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                settings = get_settings()
                backend = settings.storage_backend
                if backend == "s3":
                    logger.info("object store: s3 bucket=%s endpoint=%s region=%s",
                                settings.s3_bucket, settings.s3_endpoint, settings.s3_region)
                    _store = S3ObjectStore(settings.s3_endpoint, settings.s3_bucket,
                                           settings.s3_access_key, settings.s3_secret_key,
                                           settings.s3_region)
                elif backend == "gcs":
                    logger.info("object store: gcs bucket=%s project=%s",
                                settings.gcs_bucket, settings.gcs_project)
                    _store = GCSObjectStore(settings.gcs_bucket, settings.gcs_project,
                                            settings.gcs_credentials_file)
                elif backend == "azure":
                    logger.info("object store: azure container=%s", settings.azure_container)
                    _store = AzureBlobObjectStore(
                        settings.azure_container,
                        connection_string=settings.azure_connection_string,
                        account_url=settings.azure_account_url,
                        account_key=settings.azure_account_key,
                    )
                elif backend == "local":
                    logger.info("object store: local root=%s", settings.storage_root)
                    _store = LocalObjectStore(settings.storage_path)
                else:
                    raise ObjectStoreError(
                        f"unknown DATAFORGE_STORAGE_BACKEND: {backend!r} "
                        "(expected local | s3 | gcs | azure)"
                    )
    return _store


def reset_object_store() -> None:
    """Test helper: rebuild the store from current settings on next access."""
    global _store
    with _lock:
        _store = None
