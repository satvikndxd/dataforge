import { useState, useEffect, useMemo, useCallback } from "react";
import dynamic from 'next/dynamic';
import { Loader2, Zap } from "lucide-react";

// Disable SSR for ForceGraph
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

interface Source {
  title: string;
  url: string;
  domain: string;
  relevance_score: number;
}

interface Props {
  jobId: string;
  onProceed: () => void;
}

export default function SourceSelection({ jobId, onProceed }: Props) {
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedUrls, setSelectedUrls] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [viewMode, setViewMode] = useState<"graph" | "list">("graph");

  useEffect(() => {
    // Poll status until it reaches pending_selection
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        const data = await res.json();
        
        if (data.status === "pending_selection") {
          clearInterval(poll);
          fetchSources();
        } else if (data.status === "failed") {
          clearInterval(poll);
          alert(`Search failed: ${data.error}`);
        }
      } catch (e) {
        console.error("Polling error", e);
      }
    }, 2000);

    return () => clearInterval(poll);
  }, [jobId]);

  const fetchSources = async () => {
    try {
      const res = await fetch(`/api/sources/${jobId}`);
      if (!res.ok) throw new Error("Could not fetch sources");
      const data = await res.json();
      setSources(data.sources || []);
      setSelectedUrls(new Set((data.sources || []).map((s: Source) => s.url)));
      setLoading(false);
    } catch (e) {
      console.error(e);
      setLoading(false);
    }
  };

  const toggleSource = useCallback((url: string) => {
    setSelectedUrls((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(url)) newSet.delete(url);
      else newSet.add(url);
      return newSet;
    });
  }, []);

  const selectAll = (select: boolean) => {
    if (select) setSelectedUrls(new Set(sources.map((s) => s.url)));
    else setSelectedUrls(new Set());
  };

  const handleProceed = async () => {
    if (selectedUrls.size === 0) {
      alert("Select at least one node.");
      return;
    }
    setSubmitting(true);
    try {
      await fetch("/api/select_sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: jobId, selected_urls: Array.from(selectedUrls) }),
      });
      onProceed();
    } catch (e) {
      console.error(e);
      setSubmitting(false);
    }
  };

  const graphData = useMemo(() => {
    const nodes = sources.map(s => ({
      id: s.url,
      name: s.domain,
      val: s.relevance_score * 10,
      color: selectedUrls.has(s.url) ? "#FF5500" : "#2A2A2A" // Ember vs Iron
    }));

    // Create theoretical links to a central node to form a constellation
    const links = sources.map(s => ({
      source: "CORE",
      target: s.url,
      color: selectedUrls.has(s.url) ? "rgba(255, 85, 0, 0.4)" : "rgba(42, 42, 42, 0.4)"
    }));

    nodes.push({ id: "CORE", name: "QUERY CORE", val: 20, color: "#3B82F6" }); // Frost Core

    return { nodes, links };
  }, [sources, selectedUrls]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-6">
        <Loader2 className="animate-spin text-frost" size={64} />
        <h2 className="font-bebas text-4xl tracking-widest animate-pulse text-bone uppercase shadow-black drop-shadow-md">
          Consulting the Void...
        </h2>
      </div>
    );
  }

  return (
    <div className="w-full max-w-7xl flex flex-col md:flex-row gap-8 relative mt-10">
      
      {/* Left: Constellation / List */}
      <div className="flex-[3] flex flex-col gap-6 relative">
        <div className="flex justify-between items-end border-b-2 border-iron pb-4">
          <h2 className="font-bebas text-5xl uppercase tracking-widest text-bone">
            Source Constellation
          </h2>
          <div className="flex gap-4">
            <button
              onClick={() => setViewMode("graph")}
              className={`font-bebas text-lg tracking-[0.2em] transition-all border-b-2 ${viewMode === "graph" ? "border-frost text-frost" : "border-transparent text-iron hover:text-bone"}`}
            >
              GRAPH
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`font-bebas text-lg tracking-[0.2em] transition-all border-b-2 ${viewMode === "list" ? "border-frost text-frost" : "border-transparent text-iron hover:text-bone"}`}
            >
              LIST
            </button>
          </div>
        </div>

        <div className="runic-panel h-[600px] overflow-hidden relative">
          {viewMode === "graph" ? (
            <div className="absolute inset-0 bg-obsidian">
              <ForceGraph2D
                graphData={graphData}
                nodeRelSize={4}
                nodeColor="color"
                linkColor="color"
                backgroundColor="#0B0B0B"
                onNodeClick={(node: any) => {
                  if(node.id !== "CORE") toggleSource(node.id);
                }}
                width={900}
                height={600}
              />
              <div className="absolute bottom-4 left-4 bg-obsidian/80 backdrop-blur-sm p-3 border border-iron font-inter text-xs text-bone">
                <p><span className="text-ember">●</span> Selected Node</p>
                <p><span className="text-iron">●</span> Inactive Node</p>
                <p className="mt-2 opacity-50">Click nodes to toggle extraction.</p>
              </div>
            </div>
          ) : (
            <div className="p-4 grid grid-cols-1 gap-2 h-full overflow-y-auto custom-scrollbar">
              <div className="flex gap-4 mb-4">
                <button onClick={() => selectAll(true)} className="text-frost text-xs uppercase tracking-widest hover:text-bone">Select All</button>
                <button onClick={() => selectAll(false)} className="text-iron text-xs uppercase tracking-widest hover:text-bone">Deselect All</button>
              </div>
              {sources.map((src, i) => {
                const isSelected = selectedUrls.has(src.url);
                return (
                  <div
                    key={i}
                    onClick={() => toggleSource(src.url)}
                    className={`p-3 border-l-4 cursor-pointer transition-colors bg-obsidian ${
                      isSelected ? "border-ember" : "border-iron hover:border-gray-500"
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <h3 className="font-bold text-sm text-bone truncate max-w-[70%]">{src.title}</h3>
                      <span className="text-frost font-mono text-xs">{(src.relevance_score * 100).toFixed(0)}%</span>
                    </div>
                    <p className="text-xs text-iron font-mono mt-1">{src.domain}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Right: Technical Readout */}
      <div className="w-full md:w-80 flex flex-col gap-6 sticky top-6">
        <div className="runic-panel p-8 flex flex-col gap-6 bg-obsidian/50 backdrop-blur-md">
          <h3 className="font-bebas text-3xl text-bone uppercase tracking-[0.15em] border-b-2 border-iron pb-4 flex items-center gap-3">
            <Zap className="text-frost" size={24} /> Telemetry
          </h3>
          
          <div className="flex flex-col gap-1 border-b border-iron pb-3">
            <span className="text-iron font-bebas tracking-[0.2em] text-sm">Nodes Aligned</span>
            <span className="font-inter font-bold text-bone text-2xl">
              {selectedUrls.size} <span className="text-iron text-lg">/ {sources.length}</span>
            </span>
          </div>
          
          <div className="flex flex-col gap-1 border-b border-iron pb-3">
            <span className="text-iron font-bebas tracking-[0.2em] text-sm">Base Confidence</span>
            <span className="font-inter font-bold text-frost text-xl border border-frost/20 bg-frost/5 px-2 py-1 w-fit mt-1">
              87.4%
            </span>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-iron font-bebas tracking-[0.2em] text-sm">Est. Processing Cycle</span>
            <span className="font-inter font-mono text-ember text-lg">
              ~{(selectedUrls.size * 1.5).toFixed(0)}s
            </span>
          </div>

          <div className="mt-8 flex flex-col gap-4">
            <button
              onClick={() => {}}
              className="text-iron text-xs font-bebas tracking-[0.2em] uppercase hover:text-bone text-center transition-colors"
            >
              Refine Sources
            </button>
            <button
              onClick={handleProceed}
              disabled={submitting || selectedUrls.size === 0}
              className="runic-btn w-full mt-2"
            >
              {submitting ? <Loader2 className="animate-spin mx-auto" /> : "Proceed"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
