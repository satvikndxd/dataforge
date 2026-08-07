# Developer Guide

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
uvicorn apps.api.main:app --reload --port 8000
cd apps/web && npm install && npm run dev
```

Run tests: `python -m pytest tests -q`.

## Adding a service

1. Create `backend/services/<name>.py` with plain functions taking `org_id`
   first (tenancy is explicit, never ambient).
2. Persist via `session_scope()`; emit events via `get_event_bus().emit(...)`.
3. Expose endpoints in `backend/api/v1.py` guarded by `require_role(...)`.
4. Add unit tests under `tests/unit/`, flows under `tests/integration/`.

## Adding an agent

```python
from backend.agents.runtime import Agent, AgentContext, AgentResult

class MyAgent(Agent):
    name = "my_agent"
    description = "One-line description shown in the catalog."
    requires_approval = False   # True parks runs behind a human gate
    tier = "cheap"              # LLM routing tier: cheap | reasoning

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:
        # self.llm.complete(...) for LLM access (offline-safe)
        return AgentResult(ok=True, output={"hello": ctx.project_id})
```

Register it in `backend/agents/catalog.py::register_all`. Every invocation is
automatically budget-checked, persisted as an `AgentRun`, and audited.

## Adding a pipeline stage

Stages live in `backend/pipelines/engine.py`. Add the stage name to `STAGES`,
wrap the work with `_set_stage(run_id, name, "running"/"succeeded", detail)`,
and prefer delegating the work to an agent so governance applies.

## Adding a plugin

Create `plugins/<type>/<name>/plugin.json`:

```json
{
  "name": "dataforge-source-example",
  "version": "1.0.0",
  "type": "source",
  "entrypoint": "example.plugin:ExamplePlugin",
  "permissions": ["network:example.com", "storage:write"],
  "capabilities": ["search", "fetch"],
  "config_schema": {"type": "object", "properties": {}}
}
```

Rules (enforced): permissions must be declared and use known scopes
(`network:`, `storage:`, `db:`, `llm:`, `events:`); type must be one of
source/extractor/transform/scorer/exporter/agent/ui. Installations are
per-organization and disabled until an Admin approves them.

## Conventions

- IDs are prefixed ULIDs (`proj_…`, `run_…`) — see `backend/core/ids.py`.
- SQLAlchemy JSON columns: always assign **new** (deep-copied) values so
  change detection fires; never mutate nested dicts in place.
- Anything that can call an LLM must work without one (offline heuristics).
