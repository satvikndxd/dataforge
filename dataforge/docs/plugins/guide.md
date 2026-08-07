# Plugin Guide

DataForge is plugin-first (spec §4.3). Seven plugin types:

| Type | Extends | Examples |
|---|---|---|
| `source` | discovery + fetching | wikipedia, arxiv, github, common-crawl |
| `extractor` | content parsing | pdf, docx, pptx, audio transcriber |
| `transform` | cleaning/normalization | boilerplate strippers, chunkers |
| `scorer` | quality dimensions | toxicity models, domain classifiers |
| `exporter` | output formats | webdataset, tfrecord, coco |
| `agent` | custom agents | domain-specific curators |
| `ui` | web panels | custom visualizers |

## Manifest schema

```json
{
  "name": "dataforge-source-example",       // required, unique
  "version": "1.0.0",                        // required, semver
  "type": "source",                          // required, one of the 7 types
  "description": "…",
  "entrypoint": "pkg.module:ClassName",      // required
  "permissions": ["network:example.com"],    // required (may be empty)
  "capabilities": ["search", "fetch"],
  "config_schema": { "type": "object", "properties": {} }
}
```

## Permission scopes

- `network:<domain>` — outbound HTTP to the domain
- `storage:read` / `storage:write` — object-store access
- `db:read` — read-only queries (core tables are never writable by plugins)
- `llm:invoke` — calls through the model router (counted against budgets)
- `events:publish` — emit namespaced events

Manifests with undeclared or unknown scopes are rejected at validation time.
Installation is org-scoped and Admin-gated; the marketplace UI surfaces the
requested permissions before install.

## Design rules (enforced or reviewed)

1. Declare every permission; least privilege.
2. Version everything; breaking config changes bump the major version.
3. Emit standardized events (`<plugin>.` prefix).
4. Never touch core DB tables directly — use service interfaces.
5. Expose a health check for long-running plugins.
