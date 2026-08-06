import { useState } from "react";
import { Loader2 } from "lucide-react";

interface Props {
  onStart: (jobId: string) => void;
}

export default function LandingScreen({ onStart }: Props) {
  const [topic, setTopic] = useState("");
  const [format, setFormat] = useState<"csv" | "json" | "zip">("csv");
  const [modality, setModality] = useState("text");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (topic.trim().length < 2) {
      setError("Domain query must be longer.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/research", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, format, num_sources: 20, modality }),
      });

      if (!res.ok) throw new Error("Failed to start research");

      const data = await res.json();
      onStart(data.job_id);
    } catch (err: any) {
      setError(err.message || "Pipeline could not be started.");
      setLoading(false);
    }
  };

  return (
    <div className="w-full min-h-[90vh] flex items-center justify-center relative overflow-hidden">
      {/* Bauhaus geometric composition — circle, square, triangle */}
      <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
        <div className="absolute -top-24 -left-24 w-72 h-72 rounded-full bg-burnt border-2 border-ink" />
        <div className="absolute top-32 right-[-60px] w-56 h-56 bg-frost border-2 border-ink rotate-12" />
        <div
          className="absolute bottom-[-40px] left-[8%] w-0 h-0"
          style={{
            borderLeft: "110px solid transparent",
            borderRight: "110px solid transparent",
            borderBottom: "190px solid var(--bau-red)",
          }}
        />
        {/* Grid lines */}
        <div className="absolute top-0 bottom-0 left-1/4 w-[2px] bg-ink/10" />
        <div className="absolute top-0 bottom-0 right-1/4 w-[2px] bg-ink/10" />
      </div>

      <div className="relative z-10 flex flex-col items-center gap-10 max-w-3xl text-center w-full px-4">
        {/* Emblem: red circle / blue square / yellow triangle */}
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-full bg-ember border-2 border-ink" />
          <div className="w-10 h-10 bg-frost border-2 border-ink" />
          <div
            className="w-0 h-0"
            style={{
              borderLeft: "20px solid transparent",
              borderRight: "20px solid transparent",
              borderBottom: "36px solid var(--bau-yellow)",
            }}
          />
        </div>

        <div className="space-y-4">
          <h1 className="font-display font-bold text-6xl md:text-8xl tracking-tight text-ink uppercase leading-[0.95]">
            Data
            <span className="text-ember">forge</span>
          </h1>
          <p className="text-sm md:text-base text-ink font-display tracking-[0.35em] uppercase border-y-2 border-ink py-2 inline-block px-6 bg-surface">
            Autonomous Dataset Curation
          </p>
        </div>

        <form
          onSubmit={handleStart}
          className="runic-panel p-8 md:p-12 flex flex-col gap-8 mt-4 w-full text-left"
        >
          {/* Corner accent */}
          <div className="absolute top-0 right-0 w-8 h-8 bg-burnt border-l-2 border-b-2 border-ink" aria-hidden="true" />

          <div className="flex flex-col gap-3 relative">
            <label className="font-display font-bold text-ink text-xs tracking-[0.25em] uppercase">
              01 — Target Domain
            </label>
            <input
              type="text"
              placeholder="e.g. Nordic Runology, Quantum Mechanics..."
              className="runic-input text-lg md:text-xl"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={loading}
              autoComplete="off"
            />
            {error && (
              <span className="text-paper bg-ember border-2 border-ink font-display text-xs uppercase tracking-[0.15em] mt-1 px-3 py-2 w-fit">
                {error}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="flex flex-col gap-3">
              <label className="font-display font-bold text-ink text-xs tracking-[0.25em] uppercase">
                02 — Data Architecture
              </label>
              <div className="relative">
                <select
                  className="runic-input w-full appearance-none cursor-pointer"
                  value={modality}
                  onChange={(e) => {
                    setModality(e.target.value);
                    if (e.target.value === "image_cnn" || e.target.value === "audio") {
                      setFormat("zip");
                    } else if (format === "zip") {
                      setFormat("csv");
                    }
                  }}
                  disabled={loading}
                >
                  <option value="text">NLP Context Lexicon</option>
                  <option value="image_cnn">Vision Index (CNN)</option>
                  <option value="graph_gnn">Entity Constellation (GNN)</option>
                  <option value="audio">Acoustic Resonance</option>
                  <option value="network">Numerical Network Bridge</option>
                </select>
                {/* Custom dropdown arrow */}
                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-ink">
                  ▼
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <label className="font-display font-bold text-ink text-xs tracking-[0.25em] uppercase">
                03 — Matrix Format
              </label>
              <div className="flex gap-3">
                <button
                  type="button"
                  className={`bau-chip flex-1 py-4 text-lg font-bold ${
                    format === "csv"
                      ? "bg-frost text-paper shadow-[4px_4px_0_0_#141414]"
                      : "text-steel hover:bg-paper"
                  }`}
                  onClick={() => setFormat("csv")}
                  disabled={loading}
                >
                  CSV
                </button>
                <button
                  type="button"
                  className={`bau-chip flex-1 py-4 text-lg font-bold ${
                    format === "json"
                      ? "bg-frost text-paper shadow-[4px_4px_0_0_#141414]"
                      : "text-steel hover:bg-paper"
                  }`}
                  onClick={() => setFormat("json")}
                  disabled={loading}
                >
                  JSON
                </button>
                {(modality === "image_cnn" || modality === "audio") && (
                  <button
                    type="button"
                    className={`bau-chip flex-1 py-4 text-lg font-bold ${
                      format === "zip"
                        ? "bg-ember text-paper shadow-[4px_4px_0_0_#141414]"
                        : "text-steel hover:bg-paper"
                    }`}
                    onClick={() => setFormat("zip")}
                    disabled={loading}
                  >
                    ZIP
                  </button>
                )}
              </div>
            </div>
          </div>

          <button type="submit" className="runic-btn mt-6 h-[72px] w-full" disabled={loading}>
            {loading ? (
              <span className="flex items-center gap-4">
                <Loader2 className="animate-spin" size={26} /> Starting Pipeline...
              </span>
            ) : (
              "Commence Extraction"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
