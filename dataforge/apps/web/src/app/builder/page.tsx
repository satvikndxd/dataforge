"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Shell, { ErrorNote, PageTitle } from "@/components/Shell";
import { api } from "@/lib/api";

export default function BuilderPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState("");
  const [newProject, setNewProject] = useState({ name: "", goal: "" });
  const [sourceType, setSourceType] = useState<"url" | "inline">("url");
  const [sourceUrl, setSourceUrl] = useState("");
  const [inlineTitle, setInlineTitle] = useState("");
  const [inlineText, setInlineText] = useState("");
  const [sources, setSources] = useState<any[]>([]);
  const [run, setRun] = useState({ dataset_name: "", auto_discover: true, auto_publish: false, max_sources: 5 });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadProjects = () => api("/v1/projects").then((d) => setProjects(d.items)).catch(() => {});
  useEffect(() => { loadProjects(); }, []);
  useEffect(() => {
    if (projectId) api(`/v1/sources?project_id=${projectId}`).then((d) => setSources(d.items)).catch(() => {});
    else setSources([]);
  }, [projectId]);

  const createProject = async () => {
    setError("");
    try {
      const p = await api("/v1/projects", { method: "POST", body: newProject });
      await loadProjects();
      setProjectId(p.id);
      setNewProject({ name: "", goal: "" });
    } catch (e: any) { setError(e.message); }
  };

  const addSource = async () => {
    setError("");
    try {
      const body = sourceType === "url"
        ? { project_id: projectId, type: "url", uri: sourceUrl }
        : { project_id: projectId, type: "inline", config: { title: inlineTitle, text: inlineText } };
      await api("/v1/sources", { method: "POST", body });
      const d = await api(`/v1/sources?project_id=${projectId}`);
      setSources(d.items);
      setSourceUrl(""); setInlineTitle(""); setInlineText("");
    } catch (e: any) { setError(e.message); }
  };

  const launch = async () => {
    setError(""); setBusy(true);
    try {
      const resp = await api("/v1/pipelines/run", {
        method: "POST",
        body: { project_id: projectId, ...run },
      });
      router.push(`/runs/${resp.run_id}`);
    } catch (e: any) { setError(e.message); setBusy(false); }
  };

  const selected = projects.find((p) => p.id === projectId);

  return (
    <Shell>
      <PageTitle kicker="Dataset Supply Chain" title="Dataset" accent="Builder" />
      <ErrorNote error={error} />

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Step 1: project */}
        <section className="panel p-6 relative">
          <div className="absolute top-0 right-0 w-7 h-7 bg-red border-l-2 border-b-2 border-ink" />
          <h2 className="font-display font-bold text-lg uppercase mb-4">01 — Project</h2>
          <label className="label">Existing project</label>
          <select className="input mb-4" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">— select —</option>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div className="border-t-2 border-line pt-4">
            <label className="label">Or create new</label>
            <input className="input mb-2" placeholder="Project name" value={newProject.name}
                   onChange={(e) => setNewProject({ ...newProject, name: e.target.value })} />
            <textarea className="input mb-3" rows={3}
                      placeholder="Goal, e.g. 'Instruction dataset for legal reasoning'"
                      value={newProject.goal}
                      onChange={(e) => setNewProject({ ...newProject, goal: e.target.value })} />
            <button className="btn btn-blue w-full text-xs" disabled={!newProject.name} onClick={createProject}>
              Create project
            </button>
          </div>
        </section>

        {/* Step 2: sources */}
        <section className={`panel p-6 relative ${!projectId ? "opacity-50 pointer-events-none" : ""}`}>
          <div className="absolute top-0 right-0 w-7 h-7 bg-blue border-l-2 border-b-2 border-ink" />
          <h2 className="font-display font-bold text-lg uppercase mb-4">02 — Sources</h2>
          <div className="flex gap-2 mb-4">
            {(["url", "inline"] as const).map((t) => (
              <button key={t} onClick={() => setSourceType(t)}
                      className={`chip flex-1 py-1.5 ${sourceType === t ? "bg-ink text-paper" : ""}`}>
                {t === "url" ? "Web URL" : "Paste text"}
              </button>
            ))}
          </div>
          {sourceType === "url" ? (
            <input className="input mb-3" placeholder="https://en.wikipedia.org/wiki/…"
                   value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
          ) : (
            <>
              <input className="input mb-2" placeholder="Document title"
                     value={inlineTitle} onChange={(e) => setInlineTitle(e.target.value)} />
              <textarea className="input mb-3" rows={5} placeholder="Paste document text…"
                        value={inlineText} onChange={(e) => setInlineText(e.target.value)} />
            </>
          )}
          <button className="btn btn-blue w-full text-xs mb-4"
                  disabled={sourceType === "url" ? !sourceUrl : !inlineText}
                  onClick={addSource}>
            Add source
          </button>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {sources.map((s) => (
              <div key={s.id} className="flex items-center gap-2 text-xs font-mono border-b border-line pb-1">
                <span className="chip text-[10px]">{s.type}</span>
                <span className="truncate">{s.uri || s.config?.title || s.id}</span>
              </div>
            ))}
            {projectId && sources.length === 0 && (
              <p className="text-steel text-xs">No explicit sources — auto-discovery can find some.</p>
            )}
          </div>
        </section>

        {/* Step 3: launch */}
        <section className={`panel p-6 relative ${!projectId ? "opacity-50 pointer-events-none" : ""}`}>
          <div className="absolute top-0 right-0 w-7 h-7 bg-yellow border-l-2 border-b-2 border-ink" />
          <h2 className="font-display font-bold text-lg uppercase mb-4">03 — Pipeline</h2>
          {selected?.goal && (
            <p className="text-xs text-steel mb-3 border-l-4 border-yellow pl-2">Goal: {selected.goal}</p>
          )}
          <label className="label">Dataset name</label>
          <input className="input mb-3" placeholder={selected?.goal ? "defaults to goal" : "my-dataset"}
                 value={run.dataset_name}
                 onChange={(e) => setRun({ ...run, dataset_name: e.target.value })} />
          <label className="label">Max sources</label>
          <input type="number" min={1} max={50} className="input mb-4" value={run.max_sources}
                 onChange={(e) => setRun({ ...run, max_sources: Number(e.target.value) })} />
          {([
            ["auto_discover", "Auto-discover sources (research + search agents)"],
            ["auto_publish", "Auto-publish when quality gates pass"],
          ] as const).map(([key, label]) => (
            <label key={key} className="flex items-start gap-2 mb-3 cursor-pointer text-sm">
              <input type="checkbox" className="mt-0.5 w-4 h-4 accent-[#E02617]"
                     checked={(run as any)[key]}
                     onChange={(e) => setRun({ ...run, [key]: e.target.checked })} />
              {label}
            </label>
          ))}
          <button className="btn w-full mt-2" disabled={!projectId || busy} onClick={launch}>
            {busy ? "Launching…" : "Commence extraction"}
          </button>
          <p className="text-[11px] text-steel mt-3">
            discover → fetch → extract → chunk → embed → dedup → score → graph → document → version → publish
          </p>
        </section>
      </div>
    </Shell>
  );
}
