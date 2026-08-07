"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Shell, { PageTitle, Stat } from "@/components/Shell";
import { api, fmtDate, STAGE_COLORS } from "@/lib/api";

export default function Dashboard() {
  const [metrics, setMetrics] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [agentRuns, setAgentRuns] = useState<any[]>([]);
  const [usage, setUsage] = useState<any>(null);

  useEffect(() => {
    api("/v1/admin/metrics").then(setMetrics).catch(() => {});
    api("/v1/runs?limit=6").then((d) => setRuns(d.items)).catch(() => {});
    api("/v1/agent-runs?limit=8").then((d) => setAgentRuns(d.items)).catch(() => {});
    api("/v1/admin/usage").then(setUsage).catch(() => {});
    const t = setInterval(() => {
      api("/v1/runs?limit=6").then((d) => setRuns(d.items)).catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, []);

  const r = metrics?.resources || {};
  return (
    <Shell>
      <PageTitle kicker="Control Plane" title="Dashboard" />
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <Stat label="Projects" value={r.projects ?? "—"} color="bg-red" />
        <Stat label="Datasets" value={r.datasets ?? "—"} color="bg-blue" />
        <Stat label="Documents" value={r.documents ?? "—"} color="bg-yellow" />
        <Stat label="Records" value={r.records ?? "—"} color="bg-red" />
        <Stat label="Runs" value={r.runs ?? "—"} color="bg-blue" />
        <Stat label="Pending review" value={r.pending_reviews ?? "—"} color="bg-yellow" />
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        {/* Recent runs */}
        <section className="lg:col-span-3 panel p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-display font-bold text-xl uppercase">Recent pipeline runs</h2>
            <Link href="/builder" className="btn text-xs px-3 py-1.5">New run</Link>
          </div>
          {runs.length === 0 && (
            <p className="text-steel">No runs yet — launch one from the Builder.</p>
          )}
          <div className="space-y-3">
            {runs.map((run) => (
              <Link key={run.id} href={`/runs/${run.id}`}
                    className="block border-2 border-ink p-3 hover:shadow-bau-sm transition-shadow bg-paper">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-xs truncate">{run.id}</span>
                  <span className={`chip ${run.status === "succeeded" ? "bg-green text-paper" : run.status === "failed" ? "bg-red text-paper" : "bg-yellow"}`}>
                    {run.status}
                  </span>
                </div>
                <div className="flex gap-1 mt-2">
                  {run.stages?.map((s: any) => (
                    <span key={s.name} title={`${s.name}: ${s.status}`}
                          className={`h-2 flex-1 border border-ink ${STAGE_COLORS[s.status] || "bg-line"}`} />
                  ))}
                </div>
              </Link>
            ))}
          </div>
        </section>

        {/* Agent activity + usage */}
        <section className="lg:col-span-2 space-y-6">
          <div className="panel p-6">
            <h2 className="font-display font-bold text-xl uppercase mb-4">Agent activity</h2>
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {agentRuns.map((a) => (
                <div key={a.id} className="flex items-center justify-between text-sm border-b border-line pb-1.5">
                  <span className="font-display font-bold uppercase text-xs tracking-wide">{a.agent}</span>
                  <span className={`chip text-[10px] ${
                    a.status === "succeeded" ? "bg-green text-paper"
                    : a.status === "failed" ? "bg-red text-paper"
                    : a.status === "pending_approval" ? "bg-yellow" : "bg-surface"}`}>
                    {a.status}
                  </span>
                </div>
              ))}
              {agentRuns.length === 0 && <p className="text-steel text-sm">No agent runs yet.</p>}
            </div>
          </div>
          <div className="panel p-6">
            <h2 className="font-display font-bold text-xl uppercase mb-4">LLM usage</h2>
            <div className="font-mono text-sm space-y-1">
              <div>cost: <b>${usage?.llm_cost_usd ?? 0}</b></div>
              <div>tokens: <b>{usage?.llm_tokens ?? 0}</b></div>
              <div>agent runs: <b>{usage?.agent_runs ?? 0}</b></div>
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
