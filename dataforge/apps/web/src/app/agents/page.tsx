"use client";

import { useEffect, useState } from "react";
import Shell, { ErrorNote, PageTitle } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";

export default function AgentsPage() {
  const [agents, setAgents] = useState<any[]>([]);
  const [runs, setRuns] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [error, setError] = useState("");

  const load = () => {
    api("/v1/agents").then((d) => setAgents(d.items)).catch(() => {});
    api("/v1/agent-runs?limit=100").then((d) => setRuns(d.items)).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);

  const act = async (runId: string, action: "approve" | "reject") => {
    setError("");
    try {
      await api(`/v1/agent-runs/${runId}/${action}`, { method: "POST", body: action === "reject" ? { reason: "rejected from UI" } : undefined });
      load();
    } catch (e: any) { setError(e.message); }
  };

  const inspect = async (runId: string) => {
    try { setSelected(await api(`/v1/agent-runs/${runId}`)); } catch {}
  };

  const pending = runs.filter((r) => r.status === "pending_approval");

  return (
    <Shell>
      <PageTitle kicker="Agent Plane" title="Agent" accent="Monitor" />
      <ErrorNote error={error} />

      {pending.length > 0 && (
        <div className="panel p-5 mb-6 border-yellow" style={{ boxShadow: "5px 5px 0 0 #F5A800" }}>
          <h2 className="font-display font-bold text-lg uppercase mb-3">
            ⚠ Approval gate — {pending.length} action{pending.length > 1 ? "s" : ""} awaiting review
          </h2>
          {pending.map((r) => (
            <div key={r.id} className="flex items-center justify-between border-t border-line py-2 gap-3">
              <span className="font-display font-bold uppercase text-sm">{r.agent}</span>
              <span className="font-mono text-[11px] text-steel truncate flex-1">{r.id}</span>
              <button className="btn text-[11px] px-3 py-1" onClick={() => act(r.id, "approve")}>Approve</button>
              <button className="btn btn-ghost text-[11px] px-3 py-1" onClick={() => act(r.id, "reject")}>Reject</button>
            </div>
          ))}
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Catalog */}
        <section className="panel p-6">
          <h2 className="font-display font-bold text-lg uppercase mb-4">Catalog ({agents.length})</h2>
          <div className="space-y-2 max-h-[32rem] overflow-y-auto pr-1">
            {agents.map((a) => (
              <div key={a.name} className="border-2 border-line p-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-display font-bold uppercase text-sm">{a.name}</span>
                  <div className="flex gap-1">
                    {a.requires_approval && <span className="chip bg-yellow text-[9px]">gated</span>}
                    <span className="chip text-[9px]">{a.tier}</span>
                  </div>
                </div>
                <p className="text-[11px] text-steel mt-1">{a.description}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Run log */}
        <section className="panel p-6 lg:col-span-1">
          <h2 className="font-display font-bold text-lg uppercase mb-4">Recent runs</h2>
          <div className="space-y-1.5 max-h-[32rem] overflow-y-auto pr-1">
            {runs.map((r) => (
              <button key={r.id} onClick={() => inspect(r.id)}
                      className="w-full text-left flex items-center justify-between text-xs border-b border-line pb-1.5 hover:bg-paper px-1">
                <span className="font-display font-bold uppercase">{r.agent}</span>
                <span className="font-mono text-[10px] text-steel">{fmtDate(r.started_at)}</span>
                <span className={`chip text-[9px] ${
                  r.status === "succeeded" ? "bg-green text-paper"
                  : r.status === "failed" ? "bg-red text-paper"
                  : r.status === "pending_approval" ? "bg-yellow" : ""}`}>
                  {r.status}
                </span>
              </button>
            ))}
            {runs.length === 0 && <p className="text-steel text-sm">No agent runs yet.</p>}
          </div>
        </section>

        {/* Inspector */}
        <section className="panel p-6">
          <h2 className="font-display font-bold text-lg uppercase mb-4">Inspector</h2>
          {selected ? (
            <div className="font-mono text-[11px] space-y-3">
              <div><span className="label">Agent</span>{selected.agent} — {selected.status}</div>
              <div>
                <span className="label">Input</span>
                <pre className="bg-ink text-paper p-2 overflow-x-auto max-h-32">{JSON.stringify(selected.input, null, 1)}</pre>
              </div>
              <div>
                <span className="label">Output</span>
                <pre className="bg-ink text-paper p-2 overflow-x-auto max-h-56">{JSON.stringify(selected.output, null, 1)}</pre>
              </div>
              {selected.error && <div className="text-red font-bold">{selected.error}</div>}
              <div className="text-steel">cost: ${selected.cost_usd}</div>
            </div>
          ) : (
            <p className="text-steel text-sm">Select a run to inspect its typed input/output and cost.</p>
          )}
        </section>
      </div>
    </Shell>
  );
}
