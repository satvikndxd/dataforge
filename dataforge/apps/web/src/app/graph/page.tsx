"use client";

import { useEffect, useMemo, useState } from "react";
import Shell, { PageTitle } from "@/components/Shell";
import { api } from "@/lib/api";

/** Dependency-free radial graph lens with geometric (Bauhaus) node styling. */
export default function GraphPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [projectId, setProjectId] = useState("");
  const [graph, setGraph] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
  const [minConfidence, setMinConfidence] = useState(0.5);
  const [hover, setHover] = useState<string | null>(null);

  useEffect(() => {
    api("/v1/projects").then((d) => {
      setProjects(d.items);
      if (d.items[0]) setProjectId(d.items[0].id);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (projectId) api(`/v1/graph?project_id=${projectId}&limit=60`).then(setGraph).catch(() => {});
  }, [projectId]);

  const layout = useMemo(() => {
    const nodes = graph.nodes.slice(0, 40);
    const cx = 420, cy = 300;
    const maxMentions = Math.max(1, ...nodes.map((n) => n.mentions));
    return nodes.map((n, i) => {
      const ring = i === 0 ? 0 : i < 9 ? 130 : 240;
      const angle = i === 0 ? 0 : ((i * 2 * Math.PI) / (i < 9 ? 8 : Math.max(1, nodes.length - 9)));
      return {
        ...n,
        x: cx + ring * Math.cos(angle),
        y: cy + ring * Math.sin(angle),
        r: 8 + 14 * (n.mentions / maxMentions),
        shape: i % 3, // 0 circle, 1 square, 2 triangle
      };
    });
  }, [graph.nodes]);

  const positions = useMemo(
    () => Object.fromEntries(layout.map((n) => [n.id, n])), [layout]);

  const edges = graph.edges.filter((e) => e.confidence >= minConfidence
    && positions[e.source] && positions[e.target]);

  return (
    <Shell>
      <PageTitle kicker="Intelligence Plane" title="Knowledge" accent="Graph" />
      <div className="flex flex-wrap items-end gap-4 mb-6">
        <div>
          <label className="label">Project</label>
          <select className="input w-64" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Min edge confidence: {minConfidence.toFixed(2)}</label>
          <input type="range" min={0} max={1} step={0.05} value={minConfidence}
                 onChange={(e) => setMinConfidence(Number(e.target.value))}
                 className="w-56 accent-[#E02617]" />
        </div>
        <div className="chip ml-auto">{graph.nodes.length} entities · {edges.length} edges</div>
      </div>

      <div className="panel p-2 overflow-auto">
        {layout.length === 0 ? (
          <p className="p-8 text-steel">No entities yet — run a pipeline with graph building enabled.</p>
        ) : (
          <svg viewBox="0 0 840 600" className="w-full min-w-[700px] bg-surface">
            {edges.map((e, i) => {
              const a = positions[e.source], b = positions[e.target];
              return (
                <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                      stroke="#1E58E8" strokeWidth={1 + e.confidence * 2}
                      strokeOpacity={hover && hover !== e.source && hover !== e.target ? 0.12 : 0.55} />
              );
            })}
            {layout.map((n) => (
              <g key={n.id} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
                 opacity={hover && hover !== n.id ? 0.35 : 1} style={{ cursor: "pointer" }}>
                {n.shape === 0 && <circle cx={n.x} cy={n.y} r={n.r} fill="#E02617" stroke="#141414" strokeWidth="2" />}
                {n.shape === 1 && <rect x={n.x - n.r} y={n.y - n.r} width={n.r * 2} height={n.r * 2}
                                        fill="#F5A800" stroke="#141414" strokeWidth="2" />}
                {n.shape === 2 && (
                  <polygon points={`${n.x},${n.y - n.r} ${n.x - n.r},${n.y + n.r} ${n.x + n.r},${n.y + n.r}`}
                           fill="#1E58E8" stroke="#141414" strokeWidth="2" />
                )}
                <text x={n.x} y={n.y - n.r - 5} textAnchor="middle"
                      fontSize="10" fontFamily="var(--font-mono)" fill="#141414">
                  {n.name.length > 24 ? n.name.slice(0, 22) + "…" : n.name}
                </text>
              </g>
            ))}
          </svg>
        )}
      </div>
    </Shell>
  );
}
