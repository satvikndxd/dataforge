"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Shell, { PageTitle } from "@/components/Shell";
import { api, fmtDate, STAGE_COLORS } from "@/lib/api";

export default function RunsPage() {
  const [runs, setRuns] = useState<any[]>([]);

  useEffect(() => {
    const load = () => api("/v1/runs?limit=100").then((d) => setRuns(d.items)).catch(() => {});
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  return (
    <Shell>
      <PageTitle kicker="Data Plane" title="Pipeline" accent="Runs" />
      <div className="panel overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b-2 border-ink font-display uppercase text-xs tracking-[0.15em] text-left">
              <th className="p-3">Run</th>
              <th className="p-3">Status</th>
              <th className="p-3 w-1/3">Stages</th>
              <th className="p-3">Records</th>
              <th className="p-3">Created</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-b border-line hover:bg-paper">
                <td className="p-3 font-mono text-xs">
                  <Link href={`/runs/${run.id}`} className="underline decoration-blue decoration-2 underline-offset-2">
                    {run.id.slice(0, 22)}…
                  </Link>
                </td>
                <td className="p-3">
                  <span className={`chip ${run.status === "succeeded" ? "bg-green text-paper" : run.status === "failed" ? "bg-red text-paper" : run.status === "running" ? "bg-yellow" : ""}`}>
                    {run.status}
                  </span>
                </td>
                <td className="p-3">
                  <div className="flex gap-0.5">
                    {run.stages?.map((s: any) => (
                      <span key={s.name} title={`${s.name}: ${s.status}`}
                            className={`h-3 flex-1 border border-ink ${STAGE_COLORS[s.status] || "bg-line"}`} />
                    ))}
                  </div>
                </td>
                <td className="p-3 font-mono">{run.stats?.chunks ?? "—"}</td>
                <td className="p-3 text-steel text-xs">{fmtDate(run.created_at)}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr><td className="p-6 text-steel" colSpan={5}>No pipeline runs yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
