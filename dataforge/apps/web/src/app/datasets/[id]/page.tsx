"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Shell, { ErrorNote, PageTitle } from "@/components/Shell";
import { api, fmtDate, getToken } from "@/lib/api";

const FORMATS = ["jsonl", "json", "csv", "sqlite", "hf"];

export default function DatasetDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [dataset, setDataset] = useState<any>(null);
  const [version, setVersion] = useState<any>(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await api(`/v1/datasets/${id}`);
      setDataset(d);
      if (d.versions?.length) {
        const v = await api(`/v1/datasets/${id}/versions/${d.versions[0].id}`);
        setVersion(v);
      }
    } catch (e: any) { setError(e.message); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const doExport = async (fmt: string) => {
    if (!version) return;
    setExporting(fmt); setError("");
    try {
      const { export_id } = await api("/v1/exports", {
        method: "POST", body: { dataset_version_id: version.id, format: fmt },
      });
      for (let i = 0; i < 60; i++) {
        const job = await api(`/v1/exports/${export_id}`);
        if (job.status === "succeeded") {
          const resp = await fetch(`/v1/exports/${export_id}/download`, {
            headers: { Authorization: `Bearer ${getToken()}` },
          });
          const blob = await resp.blob();
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `dataforge_${version.version}.${fmt === "hf" ? "zip" : fmt}`;
          a.click();
          URL.revokeObjectURL(a.href);
          break;
        }
        if (job.status === "failed") { setError(job.error || "export failed"); break; }
        await new Promise((r) => setTimeout(r, 500));
      }
    } catch (e: any) { setError(e.message); }
    setExporting("");
  };

  const publish = async () => {
    setError("");
    try { await api(`/v1/datasets/${id}/publish`, { method: "POST" }); await load(); }
    catch (e: any) { setError(e.message); }
  };

  if (!dataset) return <Shell><p className="text-steel">Loading…</p></Shell>;

  const gates = version?.quality_report?.gates || {};
  const scores = version?.quality_report?.scores || {};

  return (
    <Shell>
      <PageTitle kicker={dataset.id} title={dataset.name} />
      <ErrorNote error={error} />

      <div className="grid lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 space-y-6">
          {/* Sample records */}
          <div className="panel p-6">
            <h2 className="font-display font-bold text-lg uppercase mb-4">
              Sample records {version && <span className="text-steel text-sm">({version.record_count} total)</span>}
            </h2>
            <div className="space-y-3 max-h-[28rem] overflow-y-auto">
              {version?.sample_records?.map((r: any) => (
                <div key={r.id} className="border-2 border-line border-l-4 border-l-blue p-3">
                  <div className="flex justify-between text-[10px] font-mono text-steel mb-1">
                    <span>{r.id}</span>
                    <span>quality: {r.scores?.total ?? "—"}</span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{r.content}</p>
                </div>
              ))}
              {!version && <p className="text-steel">No versions yet.</p>}
            </div>
          </div>

          {/* Dataset card */}
          {version?.dataset_card && (
            <div className="panel p-6">
              <h2 className="font-display font-bold text-lg uppercase mb-4">Dataset card</h2>
              <pre className="whitespace-pre-wrap font-mono text-xs bg-paper border-2 border-line p-4 max-h-96 overflow-y-auto">
                {version.dataset_card}
              </pre>
            </div>
          )}
        </section>

        <section className="space-y-6">
          {/* Version + gates */}
          <div className="panel p-6">
            <h2 className="font-display font-bold text-lg uppercase mb-4">Version</h2>
            {version ? (
              <>
                <div className="flex items-center justify-between mb-3">
                  <span className="font-display font-bold text-2xl">v{version.version}</span>
                  <span className={`chip ${version.status === "published" ? "bg-green text-paper" : "bg-yellow"}`}>
                    {version.status}
                  </span>
                </div>
                <div className="font-mono text-[11px] text-steel break-all mb-4">
                  sha256:{version.content_hash?.slice(0, 24)}…
                </div>
                <h3 className="label">Quality gates</h3>
                <div className="space-y-1 mb-4">
                  {Object.entries(gates).map(([gate, ok]) => (
                    <div key={gate} className="flex items-center justify-between text-xs font-mono">
                      <span>{gate}</span>
                      <span className={`chip text-[10px] ${ok ? "bg-green text-paper" : "bg-red text-paper"}`}>
                        {ok ? "pass" : "fail"}
                      </span>
                    </div>
                  ))}
                </div>
                <h3 className="label">Scores</h3>
                <div className="space-y-1.5 mb-4">
                  {Object.entries(scores).map(([k, v]: any) => (
                    <div key={k}>
                      <div className="flex justify-between text-[11px] font-mono">
                        <span>{k}</span><span>{typeof v === "number" ? v.toFixed(2) : v}</span>
                      </div>
                      {typeof v === "number" && (
                        <div className="h-1.5 border border-ink bg-surface">
                          <div className="h-full bg-blue" style={{ width: `${Math.min(100, v * 100)}%` }} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                {version.status !== "published" && (
                  <button className="btn w-full text-xs" onClick={publish}>Publish version</button>
                )}
              </>
            ) : <p className="text-steel text-sm">No versions.</p>}
          </div>

          {/* Export */}
          {version && (
            <div className="panel p-6">
              <h2 className="font-display font-bold text-lg uppercase mb-4">Export</h2>
              <div className="grid grid-cols-2 gap-2">
                {FORMATS.map((fmt) => (
                  <button key={fmt} className="btn btn-ghost text-xs py-2" disabled={!!exporting}
                          onClick={() => doExport(fmt)}>
                    {exporting === fmt ? "…" : fmt.toUpperCase()}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-steel mt-3">
                Checksummed artifacts; HF = zip bundle with data + dataset card. Parquet available with polars installed.
              </p>
            </div>
          )}

          {/* Versions list */}
          <div className="panel p-6">
            <h2 className="font-display font-bold text-lg uppercase mb-3">History</h2>
            <div className="space-y-1 text-xs font-mono">
              {dataset.versions?.map((v: any) => (
                <div key={v.id} className="flex justify-between border-b border-line pb-1">
                  <span>v{v.version} · {v.record_count} rec</span>
                  <span className="text-steel">{fmtDate(v.created_at)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
