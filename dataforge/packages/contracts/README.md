# @dataforge/contracts

Shared, language-neutral contracts:

- `event-envelope.schema.json` — the wire format of every bus event
  (mirrors `backend/events/schemas.py::Event`).
- `record.schema.json` — the canonical exported record shape
  (mirrors `backend/services/exports.py::collect_records`).

Python sources of truth live in `backend/events/schemas.py` (Pydantic) and
the SQLAlchemy models; TypeScript consumers can generate types from these
schemas (e.g. `json-schema-to-typescript`) or from the live OpenAPI document
at `/openapi.json`.
