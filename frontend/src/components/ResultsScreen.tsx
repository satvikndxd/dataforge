import { useEffect, useState, useMemo } from "react";
import dynamic from 'next/dynamic';
import { Download, RefreshCw, Activity, Database, Rows3, Network, CheckSquare, Square, Image as ImageIcon, Settings2, Package, Sparkles, Zap, ScanLine, Palette } from "lucide-react";

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

interface PreprocessingConfig {
  targetSize: [number, number];
  quality: number;
  outputFormat: "JPEG" | "PNG";
  grayscale: boolean;
  edgeEnhance: boolean;
  equalize: boolean;
  annotationFormat: "csv" | "json";
}

interface AudioExportConfig {
  exportFormat: "raw" | "spectrogram";
  annotationFormat: "csv" | "json";
}

const RESOLUTION_PRESETS: { label: string; value: [number, number] }[] = [
  { label: "224×224 (ResNet)", value: [224, 224] },
  { label: "256×256 (VGG)", value: [256, 256] },
  { label: "384×384 (ViT-L)", value: [384, 384] },
  { label: "512×512 (High-Res)", value: [512, 512] },
];

function safeHostname(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url || "Unknown";
  }
}

function getFilenameFromContentDisposition(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null;

  // RFC 5987 format: filename*=UTF-8''encoded_name.ext
  const encodedMatch = contentDisposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1].trim());
    } catch {
      return encodedMatch[1].trim();
    }
  }

  // Basic format: filename="name.ext" or filename=name.ext
  const basicMatch = contentDisposition.match(/filename\s*=\s*"?([^";]+)"?/i);
  return basicMatch?.[1]?.trim() || null;
}

export default function ResultsScreen({ jobId, onRestart }: Props) {
  const [data, setData] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [selectedImageIds, setSelectedImageIds] = useState<Set<string>>(new Set());
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [showPreprocessPanel, setShowPreprocessPanel] = useState(false);
  const [zipProgress, setZipProgress] = useState<string>("");

  const [preprocessConfig, setPreprocessConfig] = useState<PreprocessingConfig>({
    targetSize: [224, 224],
    quality: 95,
    outputFormat: "JPEG",
    grayscale: false,
    edgeEnhance: false,
    equalize: false,
    annotationFormat: "json",
  });

  const [audioExportConfig, setAudioExportConfig] = useState<AudioExportConfig>({
    exportFormat: "raw",
    annotationFormat: "json",
  });
  const [showAudioExportPanel, setShowAudioExportPanel] = useState(false);

  const [textExportFormat, setTextExportFormat] = useState<"csv" | "json">("json");
  const [showTextExportPanel, setShowTextExportPanel] = useState(false);

  useEffect(() => {
    fetch(`/api/results/${jobId}`)
      .then((res) => res.json())
      .then((json) => {
        setData(json);
        setLoading(false);
        // Auto-show preprocess panel for image modality
        if (json.modality === "image_cnn") {
          setShowPreprocessPanel(true);
        } else if (json.modality === "audio") {
          setShowAudioExportPanel(true);
        } else {
          setShowTextExportPanel(true);
        }
      })
      .catch((e) => {
        console.error(e);
        setLoading(false);
      });
  }, [jobId]);

  const handleDownload = async () => {
    if (downloading) return;
    setDownloading(true);
    try {
      // If in selection mode and images are selected, use POST with selected IDs
      const useSelection = isSelectionMode && selectedImageIds.size > 0;

      let res: Response;
      if (useSelection) {
        res = await fetch(`/api/download/${jobId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ selected_ids: Array.from(selectedImageIds) })
        });
      } else {
        res = await fetch(`/api/download/${jobId}`);
      }

      if (!res.ok) {
        throw new Error(`Download failed (${res.status})`);
      }

      const blob = await res.blob();
      const cd = res.headers.get("content-disposition");
      const contentType = res.headers.get("content-type") || "";
      const headerFileName = getFilenameFromContentDisposition(cd);

      let fallbackExt = "json";
      if (contentType.includes("text/csv")) fallbackExt = "csv";
      else if (contentType.includes("application/zip")) fallbackExt = "zip";
      else if (contentType.includes("application/json")) fallbackExt = "json";
      else if (data?.format === "csv") fallbackExt = "csv";

      let fileName = headerFileName || `dataforge_${jobId}.${fallbackExt}`;
      if (useSelection) {
        const baseName = fileName.replace(/\.[a-z0-9]+$/i, '');
        fileName = `${baseName}_selected.${fallbackExt}`;
      }
      if (!/\.[a-z0-9]+$/i.test(fileName)) {
        fileName = `${fileName}.${fallbackExt}`;
      }

      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      console.error("Download error:", err);
      alert("Failed to create download file. Please try again.");
    } finally {
      setDownloading(false);
    }
  };

  const handleDownloadImagesZip = async () => {
    if (downloadingZip) return;
    setDownloadingZip(true);
    setZipProgress("Preparing preprocessed image bundle...");
    try {
      const payload: any = {
        target_size: preprocessConfig.targetSize,
        quality: preprocessConfig.quality,
        output_format: preprocessConfig.outputFormat,
        grayscale: preprocessConfig.grayscale,
        edge_enhance: preprocessConfig.edgeEnhance,
        equalize: preprocessConfig.equalize,
        annotation_format: preprocessConfig.annotationFormat,
      };

      if (isSelectionMode && selectedImageIds.size > 0) {
        payload.selected_ids = Array.from(selectedImageIds);
      }

      setZipProgress("Downloading & preprocessing images...");

      const res = await fetch(`/api/download_images/${jobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error(`Download failed (${res.status})`);
      }

      setZipProgress("Packaging ZIP archive...");
      const blob = await res.blob();
      const cd = res.headers.get("content-disposition");
      const headerFileName = getFilenameFromContentDisposition(cd);
      const fileName = headerFileName || `dataforge_images_${jobId}.zip`;

      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      setZipProgress("Download complete ✓");
      setTimeout(() => setZipProgress(""), 3000);
    } catch (err) {
      console.error("ZIP download error:", err);
      alert("Failed to download preprocessed images. Please try again.");
      setZipProgress("");
    } finally {
      setDownloadingZip(false);
    }
  };

  const handleDownloadAudioZip = async () => {
    if (downloadingZip) return;
    setDownloadingZip(true);
    setZipProgress("Preparing audio bundle...");
    try {
      const payload: any = {
        export_format: audioExportConfig.exportFormat,
        annotation_format: audioExportConfig.annotationFormat,
      };

      if (isSelectionMode && selectedImageIds.size > 0) {
        payload.selected_ids = Array.from(selectedImageIds);
      }

      setZipProgress("Downloading & processing audio...");

      const res = await fetch(`/api/download_audio/${jobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error(`Download failed (${res.status})`);
      }

      setZipProgress("Packaging ZIP archive...");
      const blob = await res.blob();
      const cd = res.headers.get("content-disposition");
      const headerFileName = getFilenameFromContentDisposition(cd);
      const fileName = headerFileName || `dataforge_audio_${jobId}.zip`;

      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      setZipProgress("Download complete ✓");
      setTimeout(() => setZipProgress(""), 3000);
    } catch (err) {
      console.error("ZIP download error:", err);
      alert("Failed to download audio. Please try again.");
      setZipProgress("");
    } finally {
      setDownloadingZip(false);
    }
  };

  const handleDownloadTextZip = async () => {
    if (downloadingZip) return;
    setDownloadingZip(true);
    setZipProgress("Preparing archive bundle...");
    try {
      const payload: any = {
        annotation_format: textExportFormat,
      };

      if (isSelectionMode && selectedImageIds.size > 0) {
        payload.selected_ids = Array.from(selectedImageIds);
      }

      setZipProgress("Downloading & generating documents...");

      const res = await fetch(`/api/download_archive/${jobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        throw new Error(`Download failed (${res.status})`);
      }

      setZipProgress("Packaging ZIP archive...");
      const blob = await res.blob();
      const cd = res.headers.get("content-disposition");
      const headerFileName = getFilenameFromContentDisposition(cd);
      const fileName = headerFileName || `dataforge_dataset_${jobId}.zip`;

      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
      setZipProgress("Download complete ✓");
      setTimeout(() => setZipProgress(""), 3000);
    } catch (err) {
      console.error("ZIP download error:", err);
      alert("Failed to download dataset archive. Please try again.");
      setZipProgress("");
    } finally {
      setDownloadingZip(false);
    }
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

  const toggleImageSelection = (id: string) => {
    setSelectedImageIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAllImages = () => {
    if (!data) return;
    const allIds = data.records.map((rec, i) => rec.id || `image_${i}`);
    setSelectedImageIds(new Set(allIds));
  };

  const deselectAllImages = () => {
    setSelectedImageIds(new Set());
  };

  // Compute preprocessing steps preview
  const preprocessingSteps = useMemo(() => {
    const steps: string[] = [];
    steps.push(`Resize → ${preprocessConfig.targetSize[0]}×${preprocessConfig.targetSize[1]}px (Lanczos)`);
    steps.push("RGB channel normalization");
    if (preprocessConfig.equalize) steps.push("Histogram equalization");
    if (preprocessConfig.edgeEnhance) steps.push("Edge enhancement");
    if (preprocessConfig.grayscale) steps.push("Grayscale (3-channel)");
    steps.push(`Export as ${preprocessConfig.outputFormat} (q=${preprocessConfig.quality})`);
    return steps;
  }, [preprocessConfig]);

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
              <>
                {data.modality === "image_cnn" && (
                  <div className="flex items-center justify-between mb-4 sticky top-0 z-20 bg-obsidian/95 backdrop-blur-sm py-2 border-b border-iron">
                    <button
                      onClick={() => {
                        setIsSelectionMode(!isSelectionMode);
                        if (isSelectionMode) deselectAllImages();
                      }}
                      className="flex items-center gap-2 text-sm font-mono uppercase tracking-widest text-frost hover:text-bone transition-colors"
                    >
                      {isSelectionMode ? <Square size={16} /> : <CheckSquare size={16} />}
                      {isSelectionMode ? "Exit Selection" : "Select Images"}
                    </button>
                    {isSelectionMode && (
                      <div className="flex gap-3 text-xs font-mono uppercase tracking-widest">
                        <button onClick={selectAllImages} className="text-frost hover:text-bone">Select All</button>
                        <button onClick={deselectAllImages} className="text-iron hover:text-bone">Deselect All</button>
                        <span className="text-ember">{selectedImageIds.size} selected</span>
                      </div>
                    )}
                  </div>
                )}
                {data.records.slice(0, 50).map((record, i) => {
                  const recordId = record.id || `image_${i}`;
                  const isSelected = selectedImageIds.has(recordId);
                  return (
                    <div key={i} className={`border-l-2 pl-4 pb-4 mb-4 border-b border-iron relative transition-all ${isSelectionMode && data.modality === "image_cnn" ? (isSelected ? "border-frost bg-frost/5" : "border-iron opacity-60 hover:opacity-100") : "border-frost"}`}>
                      {isSelectionMode && data.modality === "image_cnn" && (
                        <button
                          onClick={() => toggleImageSelection(recordId)}
                          className="absolute top-2 right-2 z-10 p-1"
                        >
                          {isSelected ? (
                            <CheckSquare size={20} className="text-frost" />
                          ) : (
                            <Square size={20} className="text-iron" />
                          )}
                        </button>
                      )}
                      {/* Glowing Accent Node */}
                      <div className="absolute -left-[5px] top-0 w-2 h-2 bg-frost rounded-full shadow-runic-glow-frost" />

                      {/* Image Thumbnail for image_cnn modality */}
                      {data.modality === "image_cnn" && record.metadata?.image_url && (
                        <div
                          className={`relative mb-3 rounded overflow-hidden border border-iron/40 bg-black/40 group cursor-pointer max-w-[280px] ${isSelectionMode ? 'hover:ring-2 hover:ring-frost/50' : ''}`}
                          onClick={() => isSelectionMode && toggleImageSelection(recordId)}
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={record.metadata.image_url}
                            alt={record.content || "Image"}
                            loading="lazy"
                            className="w-full h-auto max-h-[200px] object-cover transition-transform duration-300 group-hover:scale-105"
                            onError={(e) => {
                              const target = e.currentTarget;
                              target.style.display = 'none';
                              const fallback = target.nextElementSibling as HTMLElement;
                              if (fallback) fallback.style.display = 'flex';
                            }}
                          />
                          {/* Fallback for broken images */}
                          <div className="hidden items-center justify-center h-[120px] text-iron gap-2" style={{ display: 'none' }}>
                            <ImageIcon size={24} />
                            <span className="text-xs font-mono uppercase tracking-widest">Image unavailable</span>
                          </div>
                          {/* Hover overlay */}
                          <div className="absolute inset-0 bg-gradient-to-t from-obsidian/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" />
                        </div>
                      )}

                      {data.modality === "audio" ? (
                        <div className="flex flex-col gap-3">
                          <div className="flex items-center gap-4 bg-obsidian/40 border border-frost/20 p-3 rounded-sm">
                            {/* Mock Spectrogram visual */}
                            <div className="flex items-end gap-[2px] h-8 flex-1 opacity-70 overflow-hidden">
                              {Array.from({ length: 50 }).map((_, barIdx) => (
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
                              &ldquo;{record.content || "Analysis incomplete or no speech decoded."}&rdquo;
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
                  );
                })}
              </>
            )}
          </div>
        </div>

        {/* Right: Analytics & Export */}
        <div className="w-full md:w-96 flex flex-col gap-6 overflow-y-auto custom-scrollbar">
          {/* Stats Panel */}
          <div className="runic-panel p-8 flex flex-col gap-8 bg-obsidian/50 backdrop-blur-md shrink-0">
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
              {/* Legacy global export button removed. Users now use the specialized export panels below. */}
            </div>
          </div>

          {/* Image Preprocessing & ZIP Download Panel */}
          {data.modality === "image_cnn" && (
            <div className="runic-panel bg-obsidian/50 backdrop-blur-md overflow-hidden shrink-0">
              {/* Panel Header */}
              <button
                onClick={() => setShowPreprocessPanel(!showPreprocessPanel)}
                className="w-full p-6 flex items-center justify-between hover:bg-frost/5 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-ember/30 to-frost/20 border border-ember/40 flex items-center justify-center shadow-[0_0_20px_rgba(255,42,42,0.15)]">
                    <Package size={20} className="text-ember" />
                  </div>
                  <div className="text-left">
                    <h3 className="font-bebas text-2xl text-bone uppercase tracking-[0.15em]">
                      Image ZIP Export
                    </h3>
                    <p className="text-[10px] font-mono uppercase tracking-widest text-iron mt-0.5">
                      Preprocessed • {data.total_records} images
                    </p>
                  </div>
                </div>
                <Settings2 size={18} className={`text-iron transition-transform duration-300 ${showPreprocessPanel ? 'rotate-90 text-frost' : ''}`} />
              </button>

              {showPreprocessPanel && (
                <div className="px-6 pb-6 flex flex-col gap-5 border-t border-iron/30">
                  {/* Resolution Preset */}
                  <div className="flex flex-col gap-2 mt-4">
                    <label className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron flex items-center gap-2">
                      <ScanLine size={12} className="text-frost" /> Target Resolution
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      {RESOLUTION_PRESETS.map((preset) => (
                        <button
                          key={preset.label}
                          onClick={() => setPreprocessConfig(prev => ({ ...prev, targetSize: preset.value }))}
                          className={`py-2.5 px-3 text-xs font-mono uppercase tracking-wider rounded border transition-all duration-200 ${
                            preprocessConfig.targetSize[0] === preset.value[0]
                              ? "border-frost bg-frost/15 text-frost shadow-[0_0_12px_rgba(77,159,255,0.2)]"
                              : "border-iron/40 bg-black/20 text-bone/50 hover:bg-iron/20 hover:text-bone/80"
                          }`}
                        >
                          {preset.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Quality Slider */}
                  <div className="flex flex-col gap-2">
                    <label className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron flex items-center justify-between">
                      <span className="flex items-center gap-2"><Sparkles size={12} className="text-frost" /> Quality</span>
                      <span className="text-frost font-bold">{preprocessConfig.quality}%</span>
                    </label>
                    <input
                      type="range"
                      min={50}
                      max={100}
                      step={5}
                      value={preprocessConfig.quality}
                      onChange={(e) => setPreprocessConfig(prev => ({ ...prev, quality: parseInt(e.target.value) }))}
                      className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-iron/30
                        [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
                        [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-frost
                        [&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(77,159,255,0.5)]
                        [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-bone/30"
                    />
                  </div>

                  {/* Output Format */}
                  <div className="flex flex-col gap-2">
                    <label className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron flex items-center gap-2">
                      <Palette size={12} className="text-frost" /> Image Format
                    </label>
                    <div className="flex gap-2">
                      {(["JPEG", "PNG"] as const).map((fmt) => (
                        <button
                          key={fmt}
                          onClick={() => setPreprocessConfig(prev => ({ ...prev, outputFormat: fmt }))}
                          className={`flex-1 py-2.5 text-sm font-bebas tracking-[0.15em] rounded border transition-all duration-200 ${
                            preprocessConfig.outputFormat === fmt
                              ? "border-frost bg-frost/15 text-frost shadow-[0_0_12px_rgba(77,159,255,0.2)]"
                              : "border-iron/40 bg-black/20 text-bone/50 hover:bg-iron/20"
                          }`}
                        >
                          {fmt}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Augmentation Toggles */}
                  <div className="flex flex-col gap-2">
                    <label className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron flex items-center gap-2">
                      <Zap size={12} className="text-ember" /> Augmentations
                    </label>
                    <div className="flex flex-col gap-1.5">
                      {[
                        { key: "equalize" as const, label: "Histogram Equalize", desc: "Normalize contrast distribution" },
                        { key: "edgeEnhance" as const, label: "Edge Enhancement", desc: "Sharpen feature boundaries" },
                        { key: "grayscale" as const, label: "Grayscale (3-ch)", desc: "Remove color, keep channels" },
                      ].map((aug) => (
                        <button
                          key={aug.key}
                          onClick={() => setPreprocessConfig(prev => ({ ...prev, [aug.key]: !prev[aug.key] }))}
                          className={`flex items-center gap-3 py-2.5 px-3 rounded border text-left transition-all duration-200 ${
                            preprocessConfig[aug.key]
                              ? "border-ember/40 bg-ember/10 shadow-[0_0_8px_rgba(255,42,42,0.1)]"
                              : "border-iron/20 bg-black/10 hover:bg-iron/10"
                          }`}
                        >
                          <div className={`w-4 h-4 rounded-sm border-2 flex items-center justify-center transition-colors ${
                            preprocessConfig[aug.key] ? "border-ember bg-ember" : "border-iron/50"
                          }`}>
                            {preprocessConfig[aug.key] && (
                              <svg viewBox="0 0 12 12" className="w-2.5 h-2.5 text-bone">
                                <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            )}
                          </div>
                          <div className="flex flex-col">
                            <span className={`text-xs font-mono uppercase tracking-wider ${preprocessConfig[aug.key] ? "text-ember" : "text-bone/60"}`}>
                              {aug.label}
                            </span>
                            <span className="text-[9px] text-iron/70">{aug.desc}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Annotations Format */}
                  <div className="flex flex-col gap-2">
                    <label className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron">Annotations Format</label>
                    <div className="flex gap-2">
                      {(["json", "csv"] as const).map((fmt) => (
                        <button
                          key={fmt}
                          onClick={() => setPreprocessConfig(prev => ({ ...prev, annotationFormat: fmt }))}
                          className={`flex-1 py-2 text-sm font-bebas tracking-[0.15em] rounded border transition-all duration-200 ${
                            preprocessConfig.annotationFormat === fmt
                              ? "border-frost bg-frost/15 text-frost"
                              : "border-iron/40 bg-black/20 text-bone/50 hover:bg-iron/20"
                          }`}
                        >
                          {fmt.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Pipeline Preview */}
                  <div className="bg-black/30 border border-iron/20 rounded p-3 flex flex-col gap-1.5">
                    <span className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron mb-1">
                      Processing Pipeline Preview
                    </span>
                    {preprocessingSteps.map((step, i) => (
                      <div key={i} className="flex items-center gap-2 text-[11px] font-mono text-bone/70">
                        <span className="text-frost text-[10px]">▸</span>
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>

                  {/* Selection info */}
                  {isSelectionMode && selectedImageIds.size > 0 && (
                    <div className="text-xs font-mono uppercase tracking-widest text-ember text-center py-2 bg-ember/5 border border-ember/20 rounded">
                      {selectedImageIds.size} of {data.total_records} images selected
                    </div>
                  )}

                  {/* ZIP Progress */}
                  {zipProgress && (
                    <div className="text-xs font-mono uppercase tracking-widest text-frost text-center py-2 animate-pulse">
                      {zipProgress}
                    </div>
                  )}

                  {/* Download Button */}
                  <button
                    onClick={handleDownloadImagesZip}
                    disabled={downloadingZip}
                    className="w-full py-4 font-bebas text-xl tracking-[0.15em] uppercase rounded-lg border transition-all duration-300
                      border-ember bg-gradient-to-r from-ember/20 to-burnt/20 text-ember
                      hover:from-ember/30 hover:to-burnt/30 hover:shadow-[0_0_25px_rgba(255,42,42,0.3)]
                      disabled:opacity-50 disabled:cursor-not-allowed
                      flex items-center justify-center gap-3"
                  >
                    {downloadingZip ? (
                      <>
                        <div className="w-5 h-5 border-2 border-ember/30 border-t-ember rounded-full animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Package size={20} />
                        Download Preprocessed ZIP
                      </>
                    )}
                  </button>

                  {/* Size estimate */}
                  <p className="text-[9px] font-mono text-iron/50 text-center uppercase tracking-wider">
                    Est. {isSelectionMode && selectedImageIds.size > 0 ? selectedImageIds.size : data.total_records} images •{" "}
                    {preprocessConfig.targetSize[0]}×{preprocessConfig.targetSize[1]}px •{" "}
                    {preprocessConfig.outputFormat}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Audio ZIP Download Panel */}
          {data.modality === "audio" && (
            <div className="runic-panel bg-obsidian/50 backdrop-blur-md overflow-hidden shrink-0 mt-6">
              {/* Panel Header */}
              <button
                onClick={() => setShowAudioExportPanel(!showAudioExportPanel)}
                className="w-full p-6 flex items-center justify-between hover:bg-frost/5 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-frost/30 to-iron/20 border border-frost/40 flex items-center justify-center shadow-[0_0_20px_rgba(77,159,255,0.15)]">
                    <Package size={20} className="text-frost" />
                  </div>
                  <div className="text-left">
                    <h3 className="font-bebas text-2xl text-bone uppercase tracking-[0.15em]">
                      Audio ZIP Export
                    </h3>
                    <p className="text-[10px] font-mono uppercase tracking-widest text-iron mt-0.5">
                      Batch • {data.total_records} assets
                    </p>
                  </div>
                </div>
                <Settings2 size={18} className={`text-iron transition-transform duration-300 ${showAudioExportPanel ? 'rotate-90 text-frost' : ''}`} />
              </button>

              {showAudioExportPanel && (
                <div className="px-6 pb-6 flex flex-col gap-5 border-t border-iron/30">
                  
                  {/* Export Format */}
                  <div className="flex flex-col gap-2 mt-4">
                    <label className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron flex items-center gap-2">
                      <ScanLine size={12} className="text-frost" /> Export Content Type
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        onClick={() => setAudioExportConfig(prev => ({ ...prev, exportFormat: "raw" }))}
                        className={`py-2.5 px-3 text-xs font-mono uppercase tracking-wider rounded border transition-all duration-200 ${
                          audioExportConfig.exportFormat === "raw"
                            ? "border-frost bg-frost/15 text-frost shadow-[0_0_12px_rgba(77,159,255,0.2)]"
                            : "border-iron/40 bg-black/20 text-bone/50 hover:bg-iron/20 hover:text-bone/80"
                        }`}
                      >
                        Raw Audio (MP3/WAV)
                      </button>
                      <button
                        onClick={() => setAudioExportConfig(prev => ({ ...prev, exportFormat: "spectrogram" }))}
                        className={`py-2.5 px-3 text-xs font-mono uppercase tracking-wider rounded border transition-all duration-200 ${
                          audioExportConfig.exportFormat === "spectrogram"
                            ? "border-ember bg-ember/15 text-ember shadow-[0_0_12px_rgba(255,68,68,0.2)]"
                            : "border-iron/40 bg-black/20 text-bone/50 hover:bg-iron/20 hover:text-bone/80"
                        }`}
                      >
                        Spectrograms (PNG)
                      </button>
                    </div>
                  </div>

                  {/* Annotations Format */}
                  <div className="flex flex-col gap-2">
                    <label className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron">Annotations Format</label>
                    <div className="flex gap-2">
                      {(["json", "csv"] as const).map((fmt) => (
                        <button
                          key={fmt}
                          onClick={() => setAudioExportConfig(prev => ({ ...prev, annotationFormat: fmt }))}
                          className={`flex-1 py-2 text-sm font-bebas tracking-[0.15em] rounded border transition-all duration-200 ${
                            audioExportConfig.annotationFormat === fmt
                              ? "border-frost bg-frost/15 text-frost"
                              : "border-iron/40 bg-black/20 text-bone/50 hover:bg-iron/20"
                          }`}
                        >
                          {fmt.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* ZIP Progress */}
                  {zipProgress && (
                    <div className="text-xs font-mono uppercase tracking-widest text-frost text-center py-2 animate-pulse">
                      {zipProgress}
                    </div>
                  )}

                  {/* Download Button */}
                  <button
                    onClick={handleDownloadAudioZip}
                    disabled={downloadingZip}
                    className={`w-full py-4 font-bebas text-xl tracking-[0.15em] uppercase rounded-lg border transition-all duration-300
                      ${audioExportConfig.exportFormat === "spectrogram" ? "border-ember bg-gradient-to-r from-ember/20 to-burnt/20 text-ember hover:from-ember/30 hover:to-burnt/30 hover:shadow-[0_0_25px_rgba(255,42,42,0.3)]" : "border-frost bg-gradient-to-r from-frost/20 to-[#312E81]/20 text-frost hover:from-frost/30 hover:to-[#312E81]/30 hover:shadow-[0_0_25px_rgba(77,159,255,0.3)]"}
                      disabled:opacity-50 disabled:cursor-not-allowed
                      flex items-center justify-center gap-3`}
                  >
                    {downloadingZip ? (
                      <>
                        <div className={`w-5 h-5 border-2 ${audioExportConfig.exportFormat === "spectrogram" ? "border-ember/30 border-t-ember" : "border-frost/30 border-t-frost"} rounded-full animate-spin`} />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Package size={20} />
                        Download Batch ZIP
                      </>
                    )}
                  </button>
                  
                  {/* Size estimate */}
                  <p className="text-[9px] font-mono text-iron/50 text-center uppercase tracking-wider">
                     Est. {data.total_records} assets
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Dataset Archive Download Panel (Non-Multimedia) */}
          {data.modality !== "audio" && data.modality !== "image_cnn" && (
            <div className="runic-panel bg-obsidian/50 backdrop-blur-md overflow-hidden shrink-0 mt-6">
              {/* Panel Header */}
              <button
                onClick={() => setShowTextExportPanel(!showTextExportPanel)}
                className="w-full p-6 flex items-center justify-between hover:bg-frost/5 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-emerald-500/30 to-emerald-900/20 border border-emerald-500/40 flex items-center justify-center shadow-[0_0_20px_rgba(16,185,129,0.15)]">
                    <Database size={20} className="text-emerald-400" />
                  </div>
                  <div className="text-left">
                    <h3 className="font-bebas text-2xl text-bone uppercase tracking-[0.15em]">
                      Dataset ZIP Archive
                    </h3>
                    <p className="text-[10px] font-mono uppercase tracking-widest text-iron mt-0.5">
                      Structured Files • {data.total_records} documents
                    </p>
                  </div>
                </div>
                <Settings2 size={18} className={`text-iron transition-transform duration-300 ${showTextExportPanel ? 'rotate-90 text-frost' : ''}`} />
              </button>

              {showTextExportPanel && (
                <div className="px-6 pb-6 flex flex-col gap-5 border-t border-iron/30">
                  
                  {/* Annotations Format */}
                  <div className="flex flex-col gap-2 mt-4">
                    <label className="text-[10px] font-mono uppercase tracking-[0.25em] text-iron">Master Index / Annotations Format</label>
                    <div className="flex gap-2">
                      {(["json", "csv"] as const).map((fmt) => (
                        <button
                          key={fmt}
                          onClick={() => setTextExportFormat(fmt)}
                          className={`flex-1 py-2 text-sm font-bebas tracking-[0.15em] rounded border transition-all duration-200 ${
                            textExportFormat === fmt
                              ? "border-emerald-400 bg-emerald-400/15 text-emerald-400"
                              : "border-iron/40 bg-black/20 text-bone/50 hover:bg-iron/20"
                          }`}
                        >
                          {fmt.toUpperCase()}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* ZIP Progress */}
                  {zipProgress && (
                    <div className="text-xs font-mono uppercase tracking-widest text-frost text-center py-2 animate-pulse">
                      {zipProgress}
                    </div>
                  )}

                  {/* Download Button */}
                  <button
                    onClick={handleDownloadTextZip}
                    disabled={downloadingZip}
                    className="w-full py-4 font-bebas text-xl tracking-[0.15em] uppercase rounded-lg border transition-all duration-300
                      border-emerald-400 bg-gradient-to-r from-emerald-500/20 to-emerald-900/20 text-emerald-400
                      hover:from-emerald-500/30 hover:to-emerald-900/30 hover:shadow-[0_0_25px_rgba(16,185,129,0.2)]
                      disabled:opacity-50 disabled:cursor-not-allowed
                      flex items-center justify-center gap-3"
                  >
                    {downloadingZip ? (
                      <>
                        <div className="w-5 h-5 border-2 border-emerald-400/30 border-t-emerald-400 rounded-full animate-spin" />
                        Processing...
                      </>
                    ) : (
                      <>
                        <Package size={20} />
                        Download Dataset Archive
                      </>
                    )}
                  </button>
                  
                  {/* Size estimate */}
                  <p className="text-[9px] font-mono text-iron/50 text-center uppercase tracking-wider">
                     Est. {data.total_records} text files + {textExportFormat.toUpperCase()} Index
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
