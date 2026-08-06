"""Plugin registry (spec §4.3).

Plugins live in `plugins/<type>/<name>/plugin.json` (+ optional plugin.py).
Manifests declare type, entrypoint, permissions, capabilities and a config
schema. Rules enforced here: manifests must declare permissions; unknown
permission scopes are rejected; plugins are disabled by default until an
admin installs them for an org.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.core.ids import new_id
from backend.db.base import session_scope
from backend.db.models import PluginInstallation

logger = logging.getLogger(__name__)

PLUGIN_TYPES = {"source", "extractor", "transform", "scorer", "exporter", "agent", "ui"}
ALLOWED_PERMISSION_PREFIXES = ("network:", "storage:", "db:", "llm:", "events:")

PLUGINS_ROOT = Path(__file__).resolve().parents[2] / "plugins"


class PluginError(Exception):
    pass


def validate_manifest(manifest: dict) -> list[str]:
    errors = []
    for field in ("name", "version", "type", "entrypoint"):
        if not manifest.get(field):
            errors.append(f"missing required field '{field}'")
    if manifest.get("type") and manifest["type"] not in PLUGIN_TYPES:
        errors.append(f"unknown plugin type '{manifest['type']}'")
    permissions = manifest.get("permissions")
    if permissions is None:
        errors.append("plugins must declare a 'permissions' array (may be empty)")
    else:
        for perm in permissions:
            if not perm.startswith(ALLOWED_PERMISSION_PREFIXES):
                errors.append(f"unknown permission scope '{perm}'")
    return errors


def discover_available() -> list[dict]:
    """Scan the plugins/ tree for manifests."""
    found = []
    if not PLUGINS_ROOT.exists():
        return found
    for manifest_path in sorted(PLUGINS_ROOT.glob("*/*/plugin.json")):
        try:
            manifest = json.loads(manifest_path.read_text())
            errors = validate_manifest(manifest)
            found.append({
                "manifest": manifest,
                "path": str(manifest_path.parent.relative_to(PLUGINS_ROOT)),
                "valid": not errors,
                "errors": errors,
            })
        except (json.JSONDecodeError, OSError) as exc:
            found.append({"manifest": {}, "path": str(manifest_path), "valid": False,
                          "errors": [str(exc)]})
    return found


def install(org_id: str, manifest: dict) -> str:
    errors = validate_manifest(manifest)
    if errors:
        raise PluginError("; ".join(errors))
    plugin_id = new_id("plg")
    with session_scope() as session:
        session.add(
            PluginInstallation(
                id=plugin_id, org_id=org_id, name=manifest["name"],
                version=manifest.get("version", "0.0.0"),
                plugin_type=manifest["type"], manifest=manifest, enabled=True,
            )
        )
    return plugin_id


def list_installed(org_id: str) -> list[dict]:
    with session_scope() as session:
        rows = session.query(PluginInstallation).filter_by(org_id=org_id).all()
        return [
            {"id": r.id, "name": r.name, "version": r.version, "type": r.plugin_type,
             "enabled": r.enabled, "permissions": r.manifest.get("permissions", [])}
            for r in rows
        ]


def set_enabled(org_id: str, plugin_id: str, enabled: bool) -> None:
    with session_scope() as session:
        row = session.get(PluginInstallation, plugin_id)
        if row is None or row.org_id != org_id:
            raise PluginError("plugin installation not found")
        row.enabled = enabled
