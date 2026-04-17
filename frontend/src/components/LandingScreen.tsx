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
      setError(err.message || "Forge instability detected.");
      setLoading(false);
    }
  };

  return (
    <div className="w-full min-h-[90vh] flex items-center justify-center relative overflow-hidden">
      {/* Background Ambience */}
      <div className="absolute inset-0 pointer-events-none flex items-center justify-center mix-blend-screen opacity-40">
        <div className="w-[800px] h-[800px] bg-frost/5 rounded-full blur-[120px]" />
        <div className="absolute w-[400px] h-[400px] bg-ember/5 rounded-full blur-[80px] -translate-y-20" />
      </div>

      {/* Rotating Geo Rings */}
      <div className="absolute inset-0 pointer-events-none flex items-center justify-center opacity-[0.03]">
        <div className="w-[600px] h-[600px] border-2 border-bone rounded-full animate-[spin_60s_linear_infinite]" />
        <div className="absolute w-[800px] h-[800px] border border-bone rounded-full animate-[spin_120s_linear_reverse_infinite] border-dashed" />
      </div>

      <div className="relative z-10 flex flex-col items-center gap-10 max-w-3xl text-center w-full px-4">
        {/* Core Emblem */}
        <div className="w-16 h-16 rounded-xl border border-ember/40 bg-ember/10 flex items-center justify-center shadow-[0_0_30px_rgba(255,42,42,0.3)] mb-2 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-tr from-burnt/20 to-transparent" />
          <div className="w-6 h-6 border-2 border-bone rotate-45 relative z-10" />
        </div>

        <div className="space-y-4">
          <h1 className="font-bebas text-6xl md:text-8xl tracking-[0.15em] text-transparent bg-clip-text bg-gradient-to-b from-bone to-bone/60 uppercase drop-shadow-2xl">
            Forge Knowledge
          </h1>
          <p className="text-lg md:text-xl text-frost/90 font-inter tracking-[0.25em] font-light uppercase">
            Initialize parameter extraction sequence
          </p>
        </div>

        <form onSubmit={handleStart} className="runic-panel p-8 md:p-12 flex flex-col gap-8 mt-4 w-full text-left">

          <div className="flex flex-col gap-3 relative">
            <label className="font-bebas text-bone/60 text-sm tracking-[0.2em] uppercase pl-1">Target Domain</label>
            <input
              type="text"
              placeholder="e.g. Nordic Runology, Quantum Mechanics..."
              className="runic-input text-lg md:text-xl tracking-wider placeholder:text-bone/20 font-light"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={loading}
              autoComplete="off"
            />
            {error && <span className="text-ember font-inter text-sm tracking-wide mt-1 pl-1">{error}</span>}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="flex flex-col gap-3">
              <label className="font-bebas text-bone/60 text-sm tracking-[0.2em] uppercase pl-1">Data Architecture</label>
              <div className="relative">
                <select
                  className="runic-input w-full appearance-none cursor-pointer text-bone/90 bg-obsidian/70"
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
                <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none opacity-50">
                  ▼
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <label className="font-bebas text-bone/60 text-sm tracking-[0.2em] uppercase pl-1">Matrix Format</label>
              <div className="flex gap-3">
                <button
                  type="button"
                  className={`flex-1 py-4 font-bebas text-xl md:text-2xl tracking-[0.15em] rounded-lg border transition-all duration-300 ${format === "csv" ? "border-frost bg-frost/20 text-frost shadow-[0_0_15px_rgba(77,159,255,0.3)]" : "border-iron-light bg-obsidian/40 text-bone/50 hover:bg-iron/60"}`}
                  onClick={() => setFormat("csv")}
                  disabled={loading}
                >
                  CSV
                </button>
                <button
                  type="button"
                  className={`flex-1 py-4 font-bebas text-xl md:text-2xl tracking-[0.15em] rounded-lg border transition-all duration-300 ${format === "json" ? "border-frost bg-frost/20 text-frost shadow-[0_0_15px_rgba(77,159,255,0.3)]" : "border-iron-light bg-obsidian/40 text-bone/50 hover:bg-iron/60"}`}
                  onClick={() => setFormat("json")}
                  disabled={loading}
                >
                  JSON
                </button>
                {(modality === "image_cnn" || modality === "audio") && (
                  <button
                    type="button"
                    className={`flex-1 py-4 font-bebas text-xl md:text-2xl tracking-[0.15em] rounded-lg border transition-all duration-300 ${format === "zip" ? "border-ember bg-ember/20 text-ember shadow-[0_0_15px_rgba(255,68,68,0.3)]" : "border-iron-light bg-obsidian/40 text-bone/50 hover:bg-iron/60"}`}
                    onClick={() => setFormat("zip")}
                    disabled={loading}
                  >
                    ZIP
                  </button>
                )}
              </div>
            </div>
          </div>

          <button
            type="submit"
            className="runic-btn mt-6 h-[72px] w-full"
            disabled={loading}
          >
            {loading ? (
              <span className="flex items-center gap-4 text-bone/90 text-[1.4rem]">
                <Loader2 className="animate-spin" size={26} /> INITIATING SEQUENCE...
              </span>
            ) : (
              "COMMENCE EXTRACTION"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
