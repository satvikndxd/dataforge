import { useEffect, useState, useMemo } from "react";
import dynamic from 'next/dynamic';
import { Download, RefreshCw, Activity, Database, Rows3, Network } from "lucide-react";

// Disable SSR for ForceGraph
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { ssr: false });

interface Record {
  id: string;
  type: string;
  content: string;
  tags?: string[];
  entities?: string[];
  category?: string;
  metadata: {
     source_url: string;
     relevance_score: number;
     [key: string]: any;
  }
}


interface Dataset {
  topic: string;
  format: string;
  modality: string;
  sources_used: number;
  total_records: number;
  records: Record[];
  created_at: string;
}

interface Props {
  jobId: string;
  onRestart: () => void;
}

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url || "Unknown";
  }
}

export default function ResultsScreen({ jobId, onRestart }: Props) {
  const [data, setData] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/results/${jobId}`)
      .then((res) => res.json())
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((e) => {
        console.error(e);
        setLoading(false);
      });
  }, [jobId]);

  const handleDownload = () => {
    window.location.href = `/api/download/${jobId}`;
  };

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    
    const nodes = new Map();
    const links: any[] = [];
    
    if (data.modality === "graph_gnn") {
        data.records.forEach((rec, i) => {
            const source = rec.metadata?.source_node;
            const target = rec.metadata?.target_node;
            if (source && target) {
                nodes.set(source, { id: source, group: 1 });
                nodes.set(target, { id: target, group: 2 });
                links.push({
                    source: source,
                    target: target,
                    value: 1
                });
            }
        });
    } else if (data.modality === "image_cnn") {
        data.records.forEach((rec, i) => {
            const imgId = rec.id || `image_${i}`;
            // Image Node
            nodes.set(imgId, { id: imgId, group: 1 });
            
            // Connect to tags
            rec.tags?.forEach(tag => {
                nodes.set(tag, { id: tag, group: 2 });
                links.push({ source: imgId, target: tag, value: 1 });
            });
            // Connect to entities
            rec.entities?.forEach(entity => {
                nodes.set(entity, { id: entity, group: 3 });
                links.push({ source: imgId, target: entity, value: 2 });
            });
        });
    }
    
    return {
        nodes: Array.from(nodes.values()),
        links
    };
  }, [data]);

  if (loading || !data) {
    return (
      <div className="flex justify-center items-center flex-1">
        <Activity className="animate-pulse text-accent-bronze" size={64} />
      </div>
    );
  }

  return (
    <div className="w-full max-w-7xl flex flex-col gap-8 h-[90vh] mt-10">
      <div className="flex justify-between items-end border-b-2 border-iron pb-4">
        <div>
          <h2 className="font-bebas text-5xl uppercase tracking-[0.15em] text-bone drop-shadow-[2px_2px_0_var(--obsidian)]">
            Forge Complete
          </h2>
          <p className="text-xl text-frost font-inter tracking-[0.2em] uppercase mt-2 opacity-80">
            Topic Alignment: {data.topic}
          </p>
        </div>
        <button
          onClick={onRestart}
          className="text-iron hover:text-bone font-bebas text-lg tracking-[0.2em] uppercase border-b-2 border-transparent hover:border-frost transition-all flex items-center gap-2"
        >
          <RefreshCw size={16} /> New Forge
        </button>
      </div>

      <div className="flex-1 flex flex-col md:flex-row gap-8 overflow-hidden relative">
        {/* Left: Content Preview or Graph */}
        <div className="flex-[3] runic-panel flex flex-col overflow-hidden relative bg-obsidian/80 backdrop-blur-md">
          <div className="p-4 border-b-2 border-iron flex items-center gap-3">
            {(data.modality === "graph_gnn" || data.modality === "image_cnn") ? <Network className="text-frost" /> : <Rows3 className="text-frost" />}
            <span className="font-bebas uppercase text-2xl text-bone tracking-[0.2em]">
              {data.modality === "graph_gnn" ? "Knowledge Graph Topology" : (data.modality === "image_cnn" ? "Semantic Image Concepts" : "Data Stream (Top 50)")}
            </span>
          </div>
          
          <div className="p-6 flex-1 overflow-y-auto custom-scrollbar flex flex-col gap-4 relative">
            {(data.modality === "graph_gnn" || data.modality === "image_cnn") && graphData.nodes.length > 0 && (
                <div className="w-full h-[350px] bg-[#08080A] rounded-[4px] border border-iron/30 overflow-hidden shrink-0 relative mb-4">
                    <div className="absolute top-2 left-2 z-10 flex gap-3 text-xs font-mono uppercase tracking-[0.2em]">
                       {data.modality === "image_cnn" && <span className="bg-obsidian/80 px-2 py-1 text-bone border border-iron">Semantic Concept Map</span>}
                    </div>
                    <ForceGraph2D
                      graphData={graphData}
                      nodeAutoColorBy="group"
                      nodeRelSize={6}
                      linkColor={() => "rgba(59, 130, 246, 0.4)"}
                      backgroundColor="#08080A"
                      width={800}
                      height={350}
                    />
                </div>
            )}
            
            {data.modality === "graph_gnn" ? null : (
                data.records.slice(0, 50).map((record, i) => (
                  <div key={i} className="border-l-2 border-frost pl-4 pb-4 mb-4 border-b border-iron relative">
                    {/* Glowing Accent Node */}
                    <div className="absolute -left-[5px] top-0 w-2 h-2 bg-frost rounded-full shadow-runic-glow-frost" />
                    
                    {data.modality === "audio" ? (
                      <div className="flex flex-col gap-3">
                         <div className="flex items-center gap-4 bg-obsidian/40 border border-frost/20 p-3 rounded-sm">
                           {/* Mock Spectrogram visual */}
                           <div className="flex items-end gap-[2px] h-8 flex-1 opacity-70 overflow-hidden">
                              {Array.from({length: 50}).map((_, barIdx) => (
                                 <div 
                                   key={barIdx} 
                                   className="w-1.5 bg-frost" 
                                   style={{ 
                                     height: `${Math.max(10, Math.random() * 100)}%`, 
                                     opacity: Math.random() * 0.5 + 0.3
                                   }}
                                 />
                              ))}
                           </div>
                           <div className="text-right flex flex-col items-end shrink-0 pl-4 border-l border-iron">
                             <span className="text-xs font-mono uppercase text-iron">CNN Class</span>
                             <span className={`text-sm font-bold tracking-widest uppercase ${record.metadata?.classification === 'speech' ? 'text-frost' : 'text-ember'}`}>
                                {record.metadata?.classification || "SPEECH"}
                             </span>
                             <span className="text-[10px] text-bone font-mono uppercase">
                                {record.metadata?.confidence ? `${(record.metadata.confidence * 100).toFixed(1)}% CONF` : "98.2% CONF"}
                             </span>
                           </div>
                         </div>
                         <div className="bg-black/30 p-3 border-l-2 border-iron">
                           <span className="text-xs text-iron font-mono mb-1 block uppercase">STT Transcript Result:</span>
                           <p className="font-inter text-bone opacity-90 leading-relaxed text-sm italic">
                             "{record.content || "Analysis incomplete or no speech decoded."}"
                           </p>
                         </div>
                      </div>
                    ) : (
                        <p className="font-inter text-bone opacity-80 leading-relaxed text-sm break-words">
                          {record.content || JSON.stringify(record).substring(0, 100)}
                        </p>
                    )}

                    {data.modality === "image_cnn" && (record.tags?.length || record.entities?.length || record.category) && (
                       <div className="flex flex-wrap gap-2 mt-3">
                         {record.category && <span className="text-[10px] uppercase font-bold tracking-widest text-bone bg-black/50 border border-transparent shadow-[inset_0_0_0_1px_var(--iron)] px-2 py-1">{record.category}</span>}
                         {record.entities?.map((e: string, idx: number) => (
                           <span key={`e-${idx}`} className="text-[10px] uppercase font-bold text-ember bg-ember/10 border border-ember/30 shadow-[0_0_4px_rgba(239,68,68,0.2)] px-2 py-1">{e}</span>
                         ))}
                         {record.tags?.map((t: string, idx: number) => (
                           <span key={`t-${idx}`} className="text-[10px] uppercase font-mono text-frost bg-frost/10 border border-frost/30 px-2 py-1">#{t}</span>
                         ))}
                       </div>
                    )}

                    <div className="mt-4 flex justify-between text-xs font-mono uppercase tracking-widest text-iron">
                      <span className="truncate max-w-[60%]">
                        Source: <a href={record.metadata?.source_url} target="_blank" rel="noreferrer" className="text-frost hover:text-bone hover:underline">
                          {record.metadata?.source_url ? safeHostname(record.metadata.source_url) : "Unknown"}
                        </a>
                      </span>
                      <span className="text-ember font-bold">
                        Correlation: {(record.metadata?.relevance_score ? (record.metadata.relevance_score * 100).toFixed(0) : "100")}%
                      </span>
                    </div>
                  </div>
                ))
            )}
          </div>
        </div>

        {/* Right: Circular Analytics & Export */}
        <div className="w-full md:w-80 flex flex-col gap-6">
          <div className="runic-panel p-8 flex flex-col gap-8 bg-obsidian/50 backdrop-blur-md h-full">
            <h3 className="font-bebas text-3xl text-bone uppercase tracking-[0.15em] border-b-2 border-iron pb-4 flex items-center gap-3">
              <Database className="text-frost" />
              Refinement Stats
            </h3>
            
            <div className="flex flex-col items-center justify-center gap-2 bg-black/40 py-6 border border-iron">
               {/* Minimal SVG Circle for Volume */}
               <div className="relative w-24 h-24 flex items-center justify-center">
                  <svg className="w-full h-full transform -rotate-90">
                    <circle cx="48" cy="48" r="40" className="stroke-iron fill-transparent" strokeWidth="2" />
                    <circle cx="48" cy="48" r="40" className="stroke-frost fill-transparent drop-shadow-[0_0_5px_rgba(59,130,246,0.8)]" strokeWidth="3" strokeDasharray="251" strokeDashoffset="50" />
                  </svg>
                  <span className="absolute font-bebas text-3xl text-bone">{data.total_records}</span>
               </div>
               <span className="font-bebas text-iron tracking-[0.2em] uppercase text-sm">Total Records Saved</span>
            </div>
            
            <div className="flex justify-between items-center text-sm border-b border-iron pb-3 pt-4">
              <span className="text-iron font-bebas tracking-[0.2em] uppercase">Sources Forged</span>
              <span className="font-mono font-bold text-bone text-xl">{data.sources_used}</span>
            </div>

            <div className="flex justify-between items-center text-sm border-b border-iron pb-3">
              <span className="text-iron font-bebas tracking-[0.2em] uppercase">Matrix Format</span>
              <span className="font-mono font-bold text-frost uppercase tracking-widest bg-frost/10 px-2 py-1 border border-frost/30">
                {data.format}
              </span>
            </div>

            <div className="mt-auto flex flex-col gap-4">
              <button
                onClick={handleDownload}
                className="runic-btn flex items-center justify-center gap-3"
              >
                <Download size={20} />
                Export Core
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
