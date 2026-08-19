"""NoSQL document / key-value store abstraction.

Same philosophy as :mod:`backend.storage.object_store`: zero-infra by
default, cloud-scale via env vars alone. The default backend keeps JSON
documents in a SQLite file under ``settings.storage_root`` (correct for
single-node deployments and tests). Production deployments flip
``DATAFORGE_NOSQL_BACKEND`` to one of:

- ``dynamodb``  — AWS DynamoDB (single-table design, requires ``boto3``)
- ``mongodb``   — MongoDB / DocumentDB / Cosmos-Mongo (requires ``pymongo``)
- ``firestore`` — GCP Firestore (requires ``google-cloud-firestore``)
- ``cosmos``    — Azure Cosmos DB, Core/SQL API (requires ``azure-cosmos``)

The data model is deliberately lowest-common-denominator so every backend
can implement it natively:

- *table*: a logical namespace (``"documents"``, ``"cache"``, …)
- *key*: an opaque ``/``-separated string, tenant-scoped like object-store
  keys (``orgs/{org_id}/…``)
- *item*: a JSON-serializable dict

Supported access patterns: get/put/delete by exact key, and key-prefix
queries (which map to DynamoDB ``begins_with`` sort-key conditions, Mongo
anchored regex, Firestore range scans, and Cosmos ``STARTSWITH``).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any
from urllib.parse import quote

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


class NoSQLStoreError(RuntimeError):
    """Raised when the NoSQL backend cannot be reached or an op fails."""


class NoSQLStore:
    """Interface shared by all backends."""

    def put_item(self, table: str, key: str, item: dict[str, Any]) -> None:
        """Upsert ``item`` at (table, key)."""
        raise NotImplementedError

    def get_item(self, table: str, key: str) -> dict[str, Any] | None:
        """Return the item at (table, key), or ``None`` if absent."""
        raise NotImplementedError

    def delete_item(self, table: str, key: str) -> None:
        """Delete the item at (table, key); no-op if absent."""
        raise NotImplementedError

    def query_prefix(self, table: str, prefix: str = "",
                     limit: int = 100) -> list[dict[str, Any]]:
        """Return up to ``limit`` items whose key starts with ``prefix``,
        ordered by key ascending. Each result includes a ``_key`` field."""
        raise NotImplementedError


def _encode_doc_id(key: str) -> str:
    """Percent-encode a key for backends whose document ids forbid ``/``."""
    return quote(key, safe="")


class LocalNoSQLStore(NoSQLStore):
    """SQLite-backed store — the zero-infra default.

    One file (``<storage_root>/nosql.db``) shared across logical tables;
    thread-safe via a process-wide lock (SQLite serializes writes anyway).
    """

    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS items ("
                " tbl TEXT NOT NULL, key TEXT NOT NULL, doc TEXT NOT NULL,"
                " PRIMARY KEY (tbl, key))"
            )
            self._conn.commit()

    def put_item(self, table: str, key: str, item: dict[str, Any]) -> None:
        doc = json.dumps(item, ensure_ascii=False, default=str)
        with self._lock:
            self._conn.execute(
                "INSERT INTO items (tbl, key, doc) VALUES (?, ?, ?)"
                " ON CONFLICT (tbl, key) DO UPDATE SET doc = excluded.doc",
                (table, key, doc))
            self._conn.commit()

    def get_item(self, table: str, key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT doc FROM items WHERE tbl = ? AND key = ?",
                (table, key)).fetchone()
        return json.loads(row[0]) if row else None

    def delete_item(self, table: str, key: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM items WHERE tbl = ? AND key = ?", (table, key))
            self._conn.commit()

    def query_prefix(self, table: str, prefix: str = "",
                     limit: int = 100) -> list[dict[str, Any]]:
        # LIKE with escaped wildcards keeps this a pure prefix match.
        pattern = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT key, doc FROM items WHERE tbl = ? AND key LIKE ? ESCAPE '\\'"
                " ORDER BY key LIMIT ?", (table, pattern, limit)).fetchall()
        return [{**json.loads(doc), "_key": key} for key, doc in rows]


class DynamoDBNoSQLStore(NoSQLStore):
    """AWS DynamoDB-backed store using single-table design.

    One physical table with partition key ``pk`` (the logical table name)
    and sort key ``sk`` (the item key); prefix queries use ``begins_with``.
    Point ``DATAFORGE_DYNAMODB_ENDPOINT`` at DynamoDB Local for offline dev.
    """

    def __init__(self, table: str, region: str | None = None,
                 endpoint: str | None = None, access_key: str | None = None,
                 secret_key: str | None = None):
        try:
            import boto3  # noqa: PLC0415 — optional dependency
        except ImportError as exc:  # pragma: no cover
            raise NoSQLStoreError(
                "DATAFORGE_NOSQL_BACKEND=dynamodb requires boto3 (pip install boto3)"
            ) from exc
        resource = boto3.resource(
            "dynamodb",
            region_name=region,
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self._table = resource.Table(table)

    def put_item(self, table: str, key: str, item: dict[str, Any]) -> None:
        # Round-trip through JSON: DynamoDB rejects floats (wants Decimal)
        # and empty sets; parse_float=str keeps numbers lossless as strings.
        safe = json.loads(json.dumps(item, ensure_ascii=False, default=str),
                          parse_float=str)
        self._table.put_item(Item={"pk": table, "sk": key, "doc": safe})

    def get_item(self, table: str, key: str) -> dict[str, Any] | None:
        resp = self._table.get_item(Key={"pk": table, "sk": key})
        found = resp.get("Item")
        return dict(found["doc"]) if found else None

    def delete_item(self, table: str, key: str) -> None:
        self._table.delete_item(Key={"pk": table, "sk": key})

    def query_prefix(self, table: str, prefix: str = "",
                     limit: int = 100) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key  # noqa: PLC0415

        cond = Key("pk").eq(table)
        if prefix:
            cond = cond & Key("sk").begins_with(prefix)
        resp = self._table.query(KeyConditionExpression=cond, Limit=limit)
        return [{**dict(i["doc"]), "_key": i["sk"]} for i in resp.get("Items", [])]


class MongoDBNoSQLStore(NoSQLStore):
    """MongoDB-backed store (also covers AWS DocumentDB and Azure Cosmos DB's
    Mongo API). One collection per logical table, ``_id`` = item key."""

    def __init__(self, url: str, database: str):
        try:
            import pymongo  # noqa: PLC0415 — optional dependency
        except ImportError as exc:  # pragma: no cover
            raise NoSQLStoreError(
                "DATAFORGE_NOSQL_BACKEND=mongodb requires pymongo (pip install pymongo)"
            ) from exc
        self._db = pymongo.MongoClient(url)[database]

    def put_item(self, table: str, key: str, item: dict[str, Any]) -> None:
        doc = {k: v for k, v in item.items() if k != "_id"}
        self._db[table].replace_one({"_id": key}, doc, upsert=True)

    def get_item(self, table: str, key: str) -> dict[str, Any] | None:
        found = self._db[table].find_one({"_id": key})
        if found is None:
            return None
        found.pop("_id", None)
        return found

    def delete_item(self, table: str, key: str) -> None:
        self._db[table].delete_one({"_id": key})

    def query_prefix(self, table: str, prefix: str = "",
                     limit: int = 100) -> list[dict[str, Any]]:
        import re  # noqa: PLC0415

        query = {"_id": {"$regex": "^" + re.escape(prefix)}} if prefix else {}
        out = []
        for doc in self._db[table].find(query).sort("_id", 1).limit(limit):
            key = doc.pop("_id")
            out.append({**doc, "_key": key})
        return out


class FirestoreNoSQLStore(NoSQLStore):
    """GCP Firestore-backed store. One collection per logical table
    (namespaced by ``collection_prefix``); document ids are percent-encoded
    keys, and the raw key is duplicated into a ``__key`` field so prefix
    queries can range-scan an indexed field."""

    def __init__(self, project: str | None, collection_prefix: str,
                 credentials_file: str | None = None):
        try:
            from google.cloud import firestore  # noqa: PLC0415 — optional dependency
        except ImportError as exc:  # pragma: no cover
            raise NoSQLStoreError(
                "DATAFORGE_NOSQL_BACKEND=firestore requires google-cloud-firestore "
                "(pip install google-cloud-firestore)"
            ) from exc
        if credentials_file:
            self._client = firestore.Client.from_service_account_json(
                credentials_file, project=project)
        else:
            self._client = firestore.Client(project=project)
        self._prefix = collection_prefix

    def _collection(self, table: str):
        return self._client.collection(f"{self._prefix}_{table}")

    def put_item(self, table: str, key: str, item: dict[str, Any]) -> None:
        doc = {k: v for k, v in item.items() if k != "__key"}
        self._collection(table).document(_encode_doc_id(key)).set({**doc, "__key": key})

    def get_item(self, table: str, key: str) -> dict[str, Any] | None:
        snap = self._collection(table).document(_encode_doc_id(key)).get()
        if not snap.exists:
            return None
        doc = snap.to_dict()
        doc.pop("__key", None)
        return doc

    def delete_item(self, table: str, key: str) -> None:
        self._collection(table).document(_encode_doc_id(key)).delete()

    def query_prefix(self, table: str, prefix: str = "",
                     limit: int = 100) -> list[dict[str, Any]]:
        from google.cloud.firestore_v1 import FieldFilter  # noqa: PLC0415

        query = self._collection(table).order_by("__key")
        if prefix:
            query = (query
                     .where(filter=FieldFilter("__key", ">=", prefix))
                     .where(filter=FieldFilter("__key", "<", prefix + "\uf8ff")))
        out = []
        for snap in query.limit(limit).stream():
            doc = snap.to_dict()
            key = doc.pop("__key", snap.id)
            out.append({**doc, "_key": key})
        return out


class CosmosDBNoSQLStore(NoSQLStore):
    """Azure Cosmos DB (Core/SQL API)-backed store. One container with
    partition key ``/tbl``; ``id`` is the percent-encoded key (Cosmos ids
    forbid ``/``), and the raw key lives in a ``key`` field."""

    def __init__(self, endpoint: str, key: str, database: str, container: str):
        try:
            from azure.cosmos import CosmosClient, PartitionKey  # noqa: PLC0415 — optional dependency
        except ImportError as exc:  # pragma: no cover
            raise NoSQLStoreError(
                "DATAFORGE_NOSQL_BACKEND=cosmos requires azure-cosmos "
                "(pip install azure-cosmos)"
            ) from exc
        client = CosmosClient(endpoint, credential=key)
        db = client.create_database_if_not_exists(database)
        self._container = db.create_container_if_not_exists(
            id=container, partition_key=PartitionKey(path="/tbl"))

    def put_item(self, table: str, key: str, item: dict[str, Any]) -> None:
        doc = {k: v for k, v in item.items() if k not in ("id", "tbl", "key")}
        self._container.upsert_item(
            {"id": _encode_doc_id(key), "tbl": table, "key": key, "doc": doc})

    def get_item(self, table: str, key: str) -> dict[str, Any] | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError  # noqa: PLC0415

        try:
            found = self._container.read_item(
                item=_encode_doc_id(key), partition_key=table)
        except CosmosResourceNotFoundError:
            return None
        return dict(found["doc"])

    def delete_item(self, table: str, key: str) -> None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError  # noqa: PLC0415

        try:
            self._container.delete_item(item=_encode_doc_id(key), partition_key=table)
        except CosmosResourceNotFoundError:
            pass

    def query_prefix(self, table: str, prefix: str = "",
                     limit: int = 100) -> list[dict[str, Any]]:
        rows = self._container.query_items(
            query=("SELECT c.key, c.doc FROM c WHERE c.tbl = @tbl"
                   " AND STARTSWITH(c.key, @prefix) ORDER BY c.key"),
            parameters=[{"name": "@tbl", "value": table},
                        {"name": "@prefix", "value": prefix}],
            partition_key=table,
            max_item_count=limit,
        )
        out = []
        for row in rows:
            out.append({**dict(row["doc"]), "_key": row["key"]})
            if len(out) >= limit:
                break
        return out


_store: NoSQLStore | None = None
_lock = threading.Lock()


def get_nosql_store() -> NoSQLStore:
    global _store
    if _store is None:
        with _lock:
            if _store is None:
                settings = get_settings()
                backend = settings.nosql_backend
                if backend == "dynamodb":
                    logger.info("nosql store: dynamodb table=%s region=%s endpoint=%s",
                                settings.dynamodb_table, settings.dynamodb_region,
                                settings.dynamodb_endpoint)
                    _store = DynamoDBNoSQLStore(
                        settings.dynamodb_table, settings.dynamodb_region,
                        settings.dynamodb_endpoint, settings.dynamodb_access_key,
                        settings.dynamodb_secret_key)
                elif backend == "mongodb":
                    if not settings.mongodb_url:
                        raise NoSQLStoreError(
                            "DATAFORGE_NOSQL_BACKEND=mongodb requires DATAFORGE_MONGODB_URL")
                    logger.info("nosql store: mongodb db=%s", settings.mongodb_database)
                    _store = MongoDBNoSQLStore(settings.mongodb_url,
                                               settings.mongodb_database)
                elif backend == "firestore":
                    logger.info("nosql store: firestore project=%s prefix=%s",
                                settings.firestore_project,
                                settings.firestore_collection_prefix)
                    _store = FirestoreNoSQLStore(
                        settings.firestore_project,
                        settings.firestore_collection_prefix,
                        settings.firestore_credentials_file)
                elif backend == "cosmos":
                    if not (settings.cosmos_endpoint and settings.cosmos_key):
                        raise NoSQLStoreError(
                            "DATAFORGE_NOSQL_BACKEND=cosmos requires "
                            "DATAFORGE_COSMOS_ENDPOINT and DATAFORGE_COSMOS_KEY")
                    logger.info("nosql store: cosmos db=%s container=%s",
                                settings.cosmos_database, settings.cosmos_container)
                    _store = CosmosDBNoSQLStore(
                        settings.cosmos_endpoint, settings.cosmos_key,
                        settings.cosmos_database, settings.cosmos_container)
                elif backend == "local":
                    path = settings.storage_path / "nosql.db"
                    logger.info("nosql store: local sqlite path=%s", path)
                    _store = LocalNoSQLStore(str(path))
                else:
                    raise NoSQLStoreError(
                        f"unknown DATAFORGE_NOSQL_BACKEND: {backend!r} "
                        "(expected local | dynamodb | mongodb | firestore | cosmos)"
                    )
    return _store


def reset_nosql_store() -> None:
    """Test helper: rebuild the store from current settings on next access."""
    global _store
    with _lock:
        _store = None
