"use client";

import { useEffect, useState } from "react";
import Shell, { ErrorNote, PageTitle } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";

export default function SettingsPage() {
  const [org, setOrg] = useState<any>(null);
  const [keys, setKeys] = useState<any[]>([]);
  const [newKey, setNewKey] = useState<any>(null);
  const [keyName, setKeyName] = useState("ci");
  const [audit, setAudit] = useState<any[]>([]);
  const [error, setError] = useState("");

  const load = () => {
    api("/v1/orgs").then(setOrg).catch(() => {});
    api("/v1/api-keys").then((d) => setKeys(d.items)).catch(() => {});
    api("/v1/admin/audit-logs?limit=50").then((d) => setAudit(d.items)).catch(() => {});
  };
  useEffect(load, []);

  const createKey = async () => {
    setError("");
    try { setNewKey(await api("/v1/api-keys", { method: "POST", body: { name: keyName } })); load(); }
    catch (e: any) { setError(e.message); }
  };

  const revoke = async (id: string) => {
    try { await api(`/v1/api-keys/${id}`, { method: "DELETE" }); load(); } catch {}
  };

  return (
    <Shell>
      <PageTitle kicker="Governance" title="Settings" />
      <ErrorNote error={error} />

      <div className="grid lg:grid-cols-2 gap-6">
        <section className="space-y-6">
          <div className="panel p-6">
            <h2 className="font-display font-bold text-lg uppercase mb-4">Organization</h2>
            {org && (
              <>
                <div className="font-display font-bold text-2xl">{org.name}</div>
                <div className="font-mono text-xs text-steel mb-4">{org.id} · /{org.slug}</div>
                <h3 className="label">Members</h3>
                {org.members?.map((m: any) => (
                  <div key={m.id} className="flex justify-between text-sm border-b border-line py-1.5">
                    <span>{m.email}</span>
                    <span className="chip text-[10px]">{m.role}</span>
                  </div>
                ))}
              </>
            )}
          </div>

          <div className="panel p-6">
            <h2 className="font-display font-bold text-lg uppercase mb-4">API keys</h2>
            <div className="flex gap-2 mb-4">
              <input className="input flex-1" value={keyName} onChange={(e) => setKeyName(e.target.value)} />
              <button className="btn text-xs" onClick={createKey}>Create key</button>
            </div>
            {newKey && (
              <div className="border-2 border-ink bg-yellow p-3 mb-4">
                <div className="label">Copy now — shown once</div>
                <code className="font-mono text-xs break-all">{newKey.key}</code>
              </div>
            )}
            {keys.map((k) => (
              <div key={k.id} className="flex items-center justify-between text-sm border-b border-line py-1.5">
                <span className="font-display font-bold">{k.name}</span>
                <span className="text-xs text-steel">{fmtDate(k.created_at)}</span>
                <button className="chip text-[10px] hover:bg-red hover:text-paper" onClick={() => revoke(k.id)}>
                  revoke
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="panel p-6">
          <h2 className="font-display font-bold text-lg uppercase mb-4">Audit trail</h2>
          <div className="space-y-1 max-h-[34rem] overflow-y-auto font-mono text-[11px]">
            {audit.map((a) => (
              <div key={a.id} className="flex gap-2 border-b border-line pb-1">
                <span className="text-blue shrink-0">{a.action}</span>
                <span className="text-steel truncate">{a.actor}</span>
                <span className="text-steel ml-auto shrink-0">{fmtDate(a.created_at)}</span>
              </div>
            ))}
            {audit.length === 0 && <p className="text-steel">No audited actions yet.</p>}
          </div>
        </section>
      </div>
    </Shell>
  );
}
