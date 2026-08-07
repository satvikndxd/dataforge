"""Agent runtime (spec §5).

Agents are goal-directed, tool-using, policy-constrained, observable,
recoverable and auditable. Every invocation:
- gets a durable AgentRun row (input/output/error/cost),
- emits agent.run.started / agent.run.completed events,
- is budget-checked against the project's LLM budget,
- may declare `requires_approval`, which parks the run in
  `pending_approval` and emits agent.action.proposed until a human
  approves/rejects (approval gates, spec §5.4).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from backend.core.config import get_settings
from backend.core.ids import new_id
from backend.db.base import session_scope
from backend.db.models import AgentRun
from backend.events.bus import get_event_bus
from backend.intelligence.llm import get_llm_router

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    org_id: str
    project_id: str = ""
    pipeline_run_id: str = ""
    actor: str = "system"
    scratch: dict[str, Any] = field(default_factory=dict)  # short-term memory


@dataclass
class AgentResult:
    ok: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    cost_usd: float = 0.0
    tokens_used: int = 0
    requires_approval: bool = False


class Agent:
    """Base class. Subclasses define `name`, `description` and `execute`."""

    name: str = "agent"
    description: str = ""
    requires_approval: bool = False   # gate before side effects apply
    tier: str = "cheap"               # default LLM tier for this agent

    def execute(self, ctx: AgentContext, params: dict) -> AgentResult:  # pragma: no cover
        raise NotImplementedError

    # -- shared helpers -------------------------------------------------
    @property
    def llm(self):
        return get_llm_router()

    def recover(self, ctx: AgentContext, params: dict, error: Exception) -> AgentResult | None:
        """Optional failure-recovery hook. Return a result to swallow the error."""
        return None


class AgentRegistry:
    def __init__(self):
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> Agent:
        if name not in self._agents:
            raise KeyError(f"unknown agent '{name}'")
        return self._agents[name]

    def list(self) -> list[dict]:
        return [
            {"name": a.name, "description": a.description,
             "requires_approval": a.requires_approval, "tier": a.tier}
            for a in self._agents.values()
        ]


_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
        from backend.agents.catalog import register_all

        register_all(_registry)
    return _registry


# ---------------------------------------------------------------------------
# Governed invocation
# ---------------------------------------------------------------------------


def _project_spend(org_id: str, project_id: str) -> float:
    from sqlalchemy import func

    with session_scope() as session:
        total = (
            session.query(func.coalesce(func.sum(AgentRun.cost_usd), 0.0))
            .filter(AgentRun.org_id == org_id, AgentRun.project_id == project_id)
            .scalar()
        )
    return float(total or 0.0)


def invoke_agent(name: str, ctx: AgentContext, params: dict,
                 *, approved: bool = False) -> dict:
    """Run an agent under full governance. Returns the AgentRun as a dict."""
    agent = get_agent_registry().get(name)
    settings = get_settings()
    bus = get_event_bus()
    run_id = new_id("agrun")

    # budget guard
    if ctx.project_id and _project_spend(ctx.org_id, ctx.project_id) >= settings.llm_budget_usd_per_project:
        bus.emit("alert.raised", tenant_id=ctx.org_id, project_id=ctx.project_id,
                 payload={"kind": "budget_exceeded", "agent": name})
        raise PermissionError(f"project LLM budget (${settings.llm_budget_usd_per_project}) exhausted")

    with session_scope() as session:
        session.add(AgentRun(id=run_id, org_id=ctx.org_id,
                             project_id=ctx.project_id or None,
                             pipeline_run_id=ctx.pipeline_run_id or None,
                             agent_name=name, status="running", input=params))
    bus.emit("agent.run.started", tenant_id=ctx.org_id, project_id=ctx.project_id,
             run_id=ctx.pipeline_run_id, actor=f"agent:{name}",
             payload={"agent_run_id": run_id, "agent": name,
                      "resource_type": "agent_run", "resource_id": run_id})

    # approval gate (before execution side effects)
    if agent.requires_approval and not approved:
        with session_scope() as session:
            row = session.get(AgentRun, run_id)
            row.status = "pending_approval"
        bus.emit("agent.action.proposed", tenant_id=ctx.org_id, project_id=ctx.project_id,
                 actor=f"agent:{name}",
                 payload={"agent_run_id": run_id, "agent": name, "params": params,
                          "resource_type": "agent_run", "resource_id": run_id})
        return {"id": run_id, "agent": name, "status": "pending_approval", "output": {}}

    try:
        result = agent.execute(ctx, params)
    except Exception as exc:
        recovered = None
        try:
            recovered = agent.recover(ctx, params, exc)
        except Exception:
            logger.exception("agent %s recovery hook failed", name)
        if recovered is not None:
            result = recovered
        else:
            with session_scope() as session:
                row = session.get(AgentRun, run_id)
                row.status = "failed"
                row.error = str(exc)
                row.finished_at = datetime.now(timezone.utc)
            bus.emit("agent.run.completed", tenant_id=ctx.org_id, project_id=ctx.project_id,
                     actor=f"agent:{name}",
                     payload={"agent_run_id": run_id, "agent": name, "status": "failed",
                              "error": str(exc), "resource_type": "agent_run",
                              "resource_id": run_id})
            raise

    status = "succeeded" if result.ok else "failed"
    with session_scope() as session:
        row = session.get(AgentRun, run_id)
        row.status = status
        row.output = result.output
        row.error = result.error
        row.cost_usd = result.cost_usd
        row.tokens_used = result.tokens_used
        row.finished_at = datetime.now(timezone.utc)
    bus.emit("agent.run.completed", tenant_id=ctx.org_id, project_id=ctx.project_id,
             run_id=ctx.pipeline_run_id, actor=f"agent:{name}",
             payload={"agent_run_id": run_id, "agent": name, "status": status,
                      "resource_type": "agent_run", "resource_id": run_id})
    return {"id": run_id, "agent": name, "status": status,
            "output": result.output, "error": result.error}


def approve_agent_run(org_id: str, agent_run_id: str, approver: str) -> dict:
    """Human approves a parked agent action; the agent re-executes for real."""
    with session_scope() as session:
        row = session.get(AgentRun, agent_run_id)
        if row is None or row.org_id != org_id:
            raise ValueError("agent run not found")
        if row.status != "pending_approval":
            raise ValueError(f"agent run is '{row.status}', not pending_approval")
        name, params = row.agent_name, dict(row.input)
        project_id = row.project_id or ""
        pipeline_run_id = row.pipeline_run_id or ""
        row.status = "approved"
        row.finished_at = datetime.now(timezone.utc)

    get_event_bus().emit("agent.action.approved", tenant_id=org_id, actor=approver,
                         payload={"agent_run_id": agent_run_id, "agent": name,
                                  "resource_type": "agent_run", "resource_id": agent_run_id})
    ctx = AgentContext(org_id=org_id, project_id=project_id,
                       pipeline_run_id=pipeline_run_id, actor=approver)
    return invoke_agent(name, ctx, params, approved=True)


def reject_agent_run(org_id: str, agent_run_id: str, approver: str, reason: str = "") -> dict:
    with session_scope() as session:
        row = session.get(AgentRun, agent_run_id)
        if row is None or row.org_id != org_id:
            raise ValueError("agent run not found")
        if row.status != "pending_approval":
            raise ValueError(f"agent run is '{row.status}', not pending_approval")
        row.status = "rejected"
        row.error = reason
        row.finished_at = datetime.now(timezone.utc)
        name = row.agent_name
    get_event_bus().emit("agent.action.rejected", tenant_id=org_id, actor=approver,
                         payload={"agent_run_id": agent_run_id, "agent": name, "reason": reason,
                                  "resource_type": "agent_run", "resource_id": agent_run_id})
    return {"id": agent_run_id, "status": "rejected"}
