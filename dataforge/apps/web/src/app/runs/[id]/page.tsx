"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Shell, { PageTitle } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";

const STAGE_FILL: Record<string, string> = {
  pending: "bg-surface text-steel",
  running: "bg-yellow text-ink animate-pulse",
  succeeded: "bg-green text-paper",
  failed: "bg-red text-paper",
};

export default function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = () => {
      api(`/v1/runs/${id}`).then(setRun).catch(() => {});
      api(`/v1/runs/${id}/events?limit=300`).then((d) => setEvents(d.items)).catch(() => {});
    };
    load();
    const t = setInterval(() => {
      load();
    }, 2500);
    return () => clearInterval(t);
  }, [id]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [events.length]);

  if (!run) return <Shell><p className="text-steel">Loading…</p></Shell>;

  const terminal = run.status === "succeeded" || run.status === "failed" || run.status === "cancelled";

  return (
    <Shell>
      <PageTitle kicker={`Run ${run.id}`} title="Pipeline" accent="Visualizer" />

      {/* Stage DAG */}
      <div className="panel p-6 mb-6 overflow-x-auto">
        <div className="flex items-stretch gap-0 min-w-[900px]">
          {run.stages.map((s: any, i: number) => (
            <div key={s.name} className="flex items-center flex-1">
              <div className={`flex-1 border-2 border-ink p-3 text-center ${STAGE_FILL[s.status] || "bg-surface"}`}>
                <div className="font-display font-bold text-xs uppercase tracking-wide">{s.name}</div>
                <div className="text-[10px] font-mono mt-1">
                  {s.status}
                  {s.detail && Object.keys(s.detail).length > 0 && (
                    <div className="truncate" title={JSON.stringify(s.detail)}>
                      {Object.entries(s.detail).slice(0, 2).map(([k, v]) =>
                        typeof v === "object" ? k : `${k}:${v}`).join(" ")}
                    </div>
                  )}
                </div>
              </div>
              {i < run.stages.length - 1 && <div className="w-3 h-0.5 bg-ink shrink-0" />}
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between mt-4">
          <div className="flex items-center gap-4 text-xs font-mono">
            <span>status: <b className={run.status === "failed" ? "text-red" : run.status === "succeeded" ? "text-green" : ""}>{run.status}</b></span>
            <span>started: {fmtDate(run.started_at)}</span>
            <span>finished: {fmtDate(run.finished_at)}</span>
          </div>
          {!terminal && (
            <button className="btn btn-ghost text-xs px-3 py-1.5"
                    onClick={() => api(`/v1/runs/${id}/cancel`, { method: "POST" })}>
              Cancel run
            </button>
          )}
        </div>
        {run.error && (
          <div className="mt-3 border-2 border-ink bg-red text-paper px-3 py-2 font-mono text-xs">{run.error}</div>
        )}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Event log */}
        <section className="lg:col-span-2 panel p-0 overflow-hidden">
          <div className="border-b-2 border-ink px-4 py-3 font-display font-bold uppercase text-sm bg-ink text-paper">
            Event stream ({events.length})
          </div>
          <div ref={logRef} className="h-96 overflow-y-auto bg-ink text-paper font-mono text-[11px] p-3 space-y-0.5">
            {events.map((e) => (
              <div key={e.id} className="flex gap-2">
                <span className="text-yellow shrink-0">{e.event_type}</span>
                <span className="text-paper/70 truncate">
                  {e.actor !== "system" ? `[${e.actor}] ` : ""}
                  {JSON.stringify(e.payload).slice(0, 140)}
                </span>
              </div>
            ))}
            {events.length === 0 && <span className="text-paper/50">waiting for events…</span>}
          </div>
        </section>

        {/* Stats */}
        <section className="panel p-6">
          <h2 className="font-display font-bold text-lg uppercase mb-4">Run stats</h2>
          <div className="font-mono text-xs space-y-1.5">
            {Object.entries(run.stats || {}).map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-line pb-1">
                <span className="text-steel">{k}</span>
                <span className="font-bold">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
              </div>
            ))}
          </div>
          {run.dataset_id && run.status === "succeeded" && (
            <Link href={`/datasets/${run.dataset_id}`} className="btn btn-blue w-full mt-6 text-xs">
              View dataset →
            </Link>
          )}
        </section>
      </div>
    </Shell>
  );
}
