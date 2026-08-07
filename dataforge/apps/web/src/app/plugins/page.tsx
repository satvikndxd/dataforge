"use client";

import { useEffect, useState } from "react";
import Shell, { ErrorNote, PageTitle } from "@/components/Shell";
import { api } from "@/lib/api";

export default function PluginsPage() {
  const [available, setAvailable] = useState<any[]>([]);
  const [installed, setInstalled] = useState<any[]>([]);
  const [error, setError] = useState("");

  const load = () => {
    api("/v1/plugins/available").then((d) => setAvailable(d.items)).catch(() => {});
    api("/v1/plugins").then((d) => setInstalled(d.items)).catch(() => {});
  };
  useEffect(load, []);

  const install = async (manifest: any) => {
    setError("");
    try { await api("/v1/plugins", { method: "POST", body: { manifest } }); load(); }
    catch (e: any) { setError(e.message); }
  };

  const installedNames = new Set(installed.map((p) => p.name));

  return (
    <Shell>
      <PageTitle kicker="Ecosystem" title="Plugin" accent="Marketplace" />
      <ErrorNote error={error} />

      <div className="grid lg:grid-cols-2 gap-6">
        <section>
          <h2 className="font-display font-bold text-xl uppercase mb-4">Available</h2>
          <div className="space-y-4">
            {available.map((p, i) => (
              <div key={i} className="panel p-5">
                <div className="flex items-center justify-between">
                  <span className="font-display font-bold uppercase">{p.manifest.name || p.path}</span>
                  <span className="chip bg-blue text-paper">{p.manifest.type}</span>
                </div>
                <p className="text-sm text-steel mt-1">{p.manifest.description || ""}</p>
                <div className="mt-3">
                  <span className="label">Requested permissions</span>
                  <div className="flex flex-wrap gap-1">
                    {(p.manifest.permissions || []).map((perm: string) => (
                      <span key={perm} className="chip text-[10px] bg-yellow">{perm}</span>
                    ))}
                    {(p.manifest.permissions || []).length === 0 && (
                      <span className="text-xs text-steel">none</span>
                    )}
                  </div>
                </div>
                {!p.valid && <p className="text-red text-xs font-bold mt-2">{p.errors.join("; ")}</p>}
                <button className="btn text-xs mt-4"
                        disabled={!p.valid || installedNames.has(p.manifest.name)}
                        onClick={() => install(p.manifest)}>
                  {installedNames.has(p.manifest.name) ? "Installed" : "Review & install"}
                </button>
              </div>
            ))}
            {available.length === 0 && (
              <div className="panel p-6 text-steel">No plugins found in the plugins/ directory.</div>
            )}
          </div>
        </section>

        <section>
          <h2 className="font-display font-bold text-xl uppercase mb-4">Installed</h2>
          <div className="space-y-3">
            {installed.map((p) => (
              <div key={p.id} className="panel p-4 flex items-center justify-between">
                <div>
                  <span className="font-display font-bold uppercase">{p.name}</span>
                  <span className="font-mono text-xs text-steel ml-2">v{p.version}</span>
                </div>
                <div className="flex gap-2">
                  <span className="chip">{p.type}</span>
                  <span className={`chip ${p.enabled ? "bg-green text-paper" : "bg-line"}`}>
                    {p.enabled ? "enabled" : "disabled"}
                  </span>
                </div>
              </div>
            ))}
            {installed.length === 0 && (
              <div className="panel p-6 text-steel">Nothing installed for this organization yet.</div>
            )}
          </div>
        </section>
      </div>
    </Shell>
  );
}
