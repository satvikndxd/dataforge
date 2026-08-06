import { useState, useEffect, useMemo, useCallback } from "react";
import dynamic from "next/dynamic";
import { Loader2, Zap } from "lucide-react";

// Disable SSR for ForceGraph
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

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

  const fetchSources = useCallback(async () => {
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
  }, [jobId]);

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
  }, [jobId, fetchSources]);

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
    const nodes = sources.map((s) => ({
      id: s.url,
      name: s.domain,
      val: s.relevance_score * 10,
      color: selectedUrls.has(s.url) ? "#E02617" : "#D8D4CB", // Bauhaus red vs hairline gray
    }));

    // Create theoretical links to a central node to form a constellation
    const links = sources.map((s) => ({
      source: "CORE",
      target: s.url,
      color: selectedUrls.has(s.url) ? "rgba(224, 38, 23, 0.45)" : "rgba(110, 106, 99, 0.25)",
    }));

    nodes.push({ id: "CORE", name: "QUERY CORE", val: 20, color: "#1E58E8" }); // Bauhaus blue core

    return { nodes, links };
  }, [sources, selectedUrls]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-6">
        <Loader2 className="animate-spin text-frost" size={64} />
        <h2 className="font-display font-bold text-4xl tracking-[0.15em] text-ink uppercase">
          Surveying Sources...
        </h2>
        <div className="flex gap-2" aria-hidden="true">
          <div className="w-4 h-4 rounded-full bg-ember border-2 border-ink" />
          <div className="w-4 h-4 bg-frost border-2 border-ink" />
          <div className="w-4 h-4 bg-burnt border-2 border-ink rotate-45" />
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-7xl flex flex-col md:flex-row gap-8 relative mt-10">
      {/* Left: Constellation / List */}
      <div className="flex-[3] flex flex-col gap-6 relative">
        <div className="flex justify-between items-end bau-rule pb-4">
          <h2 className="font-display font-bold text-4xl md:text-5xl uppercase tracking-tight text-ink">
            Source <span className="text-frost">Constellation</span>
          </h2>
          <div className="flex gap-4">
            <button
              onClick={() => setViewMode("graph")}
              className={`font-display font-bold text-sm tracking-[0.2em] uppercase px-3 py-1 border-2 transition-all ${
                viewMode === "graph"
                  ? "border-ink bg-frost text-paper"
                  : "border-transparent text-steel hover:text-ink"
              }`}
            >
              Graph
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`font-display font-bold text-sm tracking-[0.2em] uppercase px-3 py-1 border-2 transition-all ${
                viewMode === "list"
                  ? "border-ink bg-frost text-paper"
                  : "border-transparent text-steel hover:text-ink"
              }`}
            >
              List
            </button>
          </div>
        </div>

        <div className="runic-panel h-[600px] overflow-hidden relative">
          {viewMode === "graph" ? (
            <div className="absolute inset-0 bg-surface">
              <ForceGraph2D
                graphData={graphData}
                nodeRelSize={4}
                nodeColor="color"
                linkColor="color"
                backgroundColor="#FFFFFF"
                onNodeClick={(node: any) => {
                  if (node.id !== "CORE") toggleSource(node.id);
                }}
                width={900}
                height={600}
              />
              <div className="absolute bottom-4 left-4 bg-surface p-3 border-2 border-ink font-inter text-xs text-ink shadow-[4px_4px_0_0_#141414]">
                <p>
                  <span className="text-ember">●</span> Selected Node
                </p>
                <p>
                  <span className="text-steel">●</span> Inactive Node
                </p>
                <p className="mt-2 text-steel">Click nodes to toggle extraction.</p>
              </div>
            </div>
          ) : (
            <div className="p-4 grid grid-cols-1 gap-2 h-full overflow-y-auto custom-scrollbar">
              <div className="flex gap-4 mb-4">
                <button
                  onClick={() => selectAll(true)}
                  className="text-frost text-xs font-display font-bold uppercase tracking-widest hover:text-ink"
                >
                  Select All
                </button>
                <button
                  onClick={() => selectAll(false)}
                  className="text-steel text-xs font-display font-bold uppercase tracking-widest hover:text-ink"
                >
                  Deselect All
                </button>
              </div>
              {sources.map((src, i) => {
                const isSelected = selectedUrls.has(src.url);
                return (
                  <div
                    key={i}
                    onClick={() => toggleSource(src.url)}
                    className={`p-3 border-2 border-l-8 cursor-pointer transition-colors bg-surface ${
                      isSelected
                        ? "border-ink border-l-ember"
                        : "border-line border-l-line hover:border-l-steel"
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <h3 className="font-bold text-sm text-ink truncate max-w-[70%]">{src.title}</h3>
                      <span className="text-paper bg-frost border border-ink font-mono text-xs px-1.5 py-0.5">
                        {(src.relevance_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-xs text-steel font-mono mt-1">{src.domain}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Right: Technical Readout */}
      <div className="w-full md:w-80 flex flex-col gap-6 sticky top-6">
        <div className="runic-panel p-8 flex flex-col gap-6">
          <div className="absolute top-0 left-0 w-full h-2 bg-burnt border-b-2 border-ink" aria-hidden="true" />
          <h3 className="font-display font-bold text-2xl text-ink uppercase tracking-[0.1em] bau-rule pb-4 flex items-center gap-3 mt-2">
            <Zap className="text-frost" size={24} /> Telemetry
          </h3>

          <div className="flex flex-col gap-1 border-b-2 border-line pb-3">
            <span className="text-steel font-display font-bold tracking-[0.2em] text-xs uppercase">
              Nodes Aligned
            </span>
            <span className="font-inter font-bold text-ink text-2xl">
              {selectedUrls.size} <span className="text-steel text-lg">/ {sources.length}</span>
            </span>
          </div>

          <div className="flex flex-col gap-1 border-b-2 border-line pb-3">
            <span className="text-steel font-display font-bold tracking-[0.2em] text-xs uppercase">
              Base Confidence
            </span>
            <span className="font-inter font-bold text-paper text-xl bg-frost border-2 border-ink px-2 py-1 w-fit mt-1">
              87.4%
            </span>
          </div>

          <div className="flex flex-col gap-1">
            <span className="text-steel font-display font-bold tracking-[0.2em] text-xs uppercase">
              Est. Processing Cycle
            </span>
            <span className="font-mono text-ember text-lg font-bold">
              ~{(selectedUrls.size * 1.5).toFixed(0)}s
            </span>
          </div>

          <div className="mt-8 flex flex-col gap-4">
            <button
              onClick={() => {}}
              className="text-steel text-xs font-display font-bold tracking-[0.2em] uppercase hover:text-ink text-center transition-colors"
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
