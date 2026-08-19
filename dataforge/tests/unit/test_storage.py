"""Storage layer: object store + NoSQL store backends and factories."""
from __future__ import annotations

import pytest

from backend.storage.nosql_store import (
    LocalNoSQLStore,
    NoSQLStoreError,
    _encode_doc_id,
    get_nosql_store,
    reset_nosql_store,
)
from backend.storage.object_store import (
    LocalObjectStore,
    ObjectStore,
    ObjectStoreError,
    get_object_store,
    reset_object_store,
)


# ---------------------------------------------------------------------------
# Object store
# ---------------------------------------------------------------------------


def test_local_object_store_roundtrip(tmp_path):
    store = LocalObjectStore(tmp_path)
    key = "orgs/org_1/raw/deadbeef.bin"
    assert not store.exists(key)
    store.put(key, b"hello")
    assert store.exists(key)
    assert store.get(key) == b"hello"
    store.delete(key)
    assert not store.exists(key)
    with pytest.raises(ObjectStoreError):
        store.get(key)


def test_local_object_store_rejects_path_escape(tmp_path):
    store = LocalObjectStore(tmp_path)
    with pytest.raises(ObjectStoreError):
        store.put("../outside.bin", b"nope")


def test_content_address_is_deterministic_and_tenant_scoped():
    a = ObjectStore.content_address("org_1", "raw", b"same-bytes", "bin")
    b = ObjectStore.content_address("org_1", "raw", b"same-bytes", "bin")
    c = ObjectStore.content_address("org_2", "raw", b"same-bytes", "bin")
    assert a == b
    assert a != c and a.startswith("orgs/org_1/raw/")


def test_object_store_factory_default_local(app):
    reset_object_store()
    try:
        assert isinstance(get_object_store(), LocalObjectStore)
    finally:
        reset_object_store()


def test_object_store_factory_rejects_unknown_backend(app, monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_backend", "oracle-cloud")
    reset_object_store()
    try:
        with pytest.raises(ObjectStoreError, match="unknown"):
            get_object_store()
    finally:
        monkeypatch.undo()
        reset_object_store()


# ---------------------------------------------------------------------------
# NoSQL store
# ---------------------------------------------------------------------------


@pytest.fixture()
def nosql(tmp_path):
    return LocalNoSQLStore(str(tmp_path / "nosql.db"))


def test_nosql_put_get_delete(nosql):
    key = "orgs/org_1/docs/abc"
    assert nosql.get_item("documents", key) is None
    nosql.put_item("documents", key, {"title": "Hello", "score": 0.9})
    assert nosql.get_item("documents", key) == {"title": "Hello", "score": 0.9}
    # upsert overwrites
    nosql.put_item("documents", key, {"title": "Updated"})
    assert nosql.get_item("documents", key) == {"title": "Updated"}
    nosql.delete_item("documents", key)
    assert nosql.get_item("documents", key) is None
    nosql.delete_item("documents", key)  # idempotent


def test_nosql_tables_are_isolated(nosql):
    nosql.put_item("a", "k", {"v": 1})
    nosql.put_item("b", "k", {"v": 2})
    assert nosql.get_item("a", "k") == {"v": 1}
    assert nosql.get_item("b", "k") == {"v": 2}


def test_nosql_query_prefix(nosql):
    for i in range(5):
        nosql.put_item("docs", f"orgs/org_1/d/{i}", {"i": i})
    nosql.put_item("docs", "orgs/org_2/d/0", {"i": 99})

    hits = nosql.query_prefix("docs", "orgs/org_1/")
    assert [h["i"] for h in hits] == [0, 1, 2, 3, 4]
    assert hits[0]["_key"] == "orgs/org_1/d/0"

    assert len(nosql.query_prefix("docs", "orgs/org_1/", limit=2)) == 2
    assert len(nosql.query_prefix("docs")) == 6
    assert nosql.query_prefix("docs", "orgs/org_3/") == []


def test_nosql_prefix_wildcards_are_literal(nosql):
    nosql.put_item("t", "a_c", {"v": 1})
    nosql.put_item("t", "abc", {"v": 2})
    nosql.put_item("t", "a%c", {"v": 3})
    # "_" and "%" in the prefix must not act as LIKE wildcards
    assert [h["v"] for h in nosql.query_prefix("t", "a_")] == [1]
    assert [h["v"] for h in nosql.query_prefix("t", "a%")] == [3]


def test_nosql_persists_across_instances(tmp_path):
    path = str(tmp_path / "nosql.db")
    LocalNoSQLStore(path).put_item("t", "k", {"v": "persisted"})
    assert LocalNoSQLStore(path).get_item("t", "k") == {"v": "persisted"}


def test_nosql_factory_default_local(app):
    reset_nosql_store()
    try:
        store = get_nosql_store()
        assert isinstance(store, LocalNoSQLStore)
        assert get_nosql_store() is store  # singleton
    finally:
        reset_nosql_store()


def test_nosql_factory_rejects_unknown_backend(app, monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "nosql_backend", "cassandra")
    reset_nosql_store()
    try:
        with pytest.raises(NoSQLStoreError, match="unknown"):
            get_nosql_store()
    finally:
        monkeypatch.undo()
        reset_nosql_store()


def test_nosql_factory_mongodb_requires_url(app, monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "nosql_backend", "mongodb")
    reset_nosql_store()
    try:
        with pytest.raises(NoSQLStoreError, match="MONGODB_URL"):
            get_nosql_store()
    finally:
        monkeypatch.undo()
        reset_nosql_store()


def test_nosql_factory_cosmos_requires_credentials(app, monkeypatch):
    from backend.core.config import get_settings

    monkeypatch.setattr(get_settings(), "nosql_backend", "cosmos")
    reset_nosql_store()
    try:
        with pytest.raises(NoSQLStoreError, match="COSMOS"):
            get_nosql_store()
    finally:
        monkeypatch.undo()
        reset_nosql_store()


def test_doc_id_encoding_is_reversible_and_slash_free():
    from urllib.parse import unquote

    key = "orgs/org 1/docs/a?b#c"
    encoded = _encode_doc_id(key)
    assert "/" not in encoded and "?" not in encoded and "#" not in encoded
    assert unquote(encoded) == key
