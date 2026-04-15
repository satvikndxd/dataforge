import { useEffect, useRef, useState } from "react";
import { Loader2, AlertTriangle } from "lucide-react";

interface StatusData {
  status: string;
  stage: string;
  progress: number;
  message: string;
  error?: string;
}

interface Props {
  jobId: string;
  onComplete: () => void;
}

export default function ScrapingProgress({ jobId, onComplete }: Props) {
  const [status, setStatus] = useState<StatusData>({
    status: "starting",
    stage: "Initializing Sequence...",
    progress: 0,
    message: "Connecting to Forge..."
  });
  const [logs, setLogs] = useState<{msg: string, type: 'info'|'warn'|'error'}[]>([]);

  // Keep a ref to onComplete so it never stales inside the interval
  const onCompleteRef = useRef(onComplete);
  useEffect(() => { onCompleteRef.current = onComplete; }, [onComplete]);

  useEffect(() => {
    // Track the last message we logged to avoid duplicates without needing `logs` in deps
    let lastLoggedMsg = "";

    const poll = setInterval(async () => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        if (!res.ok) return;
        const data: StatusData = await res.json();

        setStatus(data);

        if (data.message && data.message !== lastLoggedMsg) {
          lastLoggedMsg = data.message;
          let type: 'info'|'warn'|'error' = 'info';
          if (data.message.toLowerCase().includes('failed') || data.message.toLowerCase().includes('error')) type = 'error';
          else if (data.message.toLowerCase().includes('retry') || data.message.toLowerCase().includes('blocked')) type = 'warn';
          setLogs(prev => [{msg: data.message, type}, ...prev].slice(0, 30));
        }

        if (data.status === "done") {
          clearInterval(poll);
          setTimeout(() => onCompleteRef.current(), 1500);
        } else if (data.status === "failed") {
          clearInterval(poll);
        }
      } catch (e) {
        console.error(e);
      }
    }, 1000);

    return () => clearInterval(poll);
  }, [jobId]);  // ← only re-run when jobId changes, NOT on every log update

  // SVG Radial Math
  const radius = 90;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (status.progress / 100) * circumference;

  return (
    <div className="w-full max-w-7xl flex flex-col md:flex-row gap-8 relative mt-10">
      
      {/* Left: Extraction Core (Radial + Logs) */}
      <div className="flex-[3] flex flex-col gap-8">
        
        {/* Radial Progress */}
        <div className="runic-panel p-10 flex flex-col items-center justify-center relative overflow-hidden bg-obsidian/80 backdrop-blur-md">
          {/* Subtle spinning background rune */}
          <div className="absolute inset-0 flex items-center justify-center opacity-5 pointer-events-none">
             <div className="w-[400px] h-[400px] border border-frost rounded-full animate-[spin_60s_linear_infinite]" />
          </div>

          <div className="relative w-64 h-64 flex items-center justify-center">
            {/* Background drop shadow glow */}
            <div className="absolute inset-4 rounded-full shadow-runic-glow-frost opacity-20" />
            
            <svg className="w-full h-full transform -rotate-90">
              <circle
                cx="128"
                cy="128"
                r={radius}
                className="stroke-iron fill-transparent"
                strokeWidth="4"
                strokeDasharray="4 8"
              />
              <circle
                cx="128"
                cy="128"
                r={radius}
                className="stroke-frost fill-transparent transition-all duration-700 ease-out drop-shadow-[0_0_8px_rgba(59,130,246,0.8)]"
                strokeWidth="6"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="square"
              />
            </svg>

            <div className="absolute flex flex-col items-center text-center">
              <span className="font-bebas text-5xl text-bone drop-shadow-md">
                {status.progress}%
              </span>
              <span className="font-bebas text-frost tracking-[0.2em] text-xs uppercase mt-1">
                Extracting Streams
              </span>
            </div>
          </div>
          
          <h2 className="font-bebas text-3xl uppercase tracking-widest text-bone drop-shadow-[2px_2px_0_var(--obsidian)] mt-4">
            {status.status === "failed" ? "Sequence Failed" : status.stage}
          </h2>
        </div>

        {/* Activity Log Feed */}
        <div className="runic-panel p-4 h-64 overflow-y-hidden relative font-inter text-xs flex flex-col bg-[#08080A]">
          <div className="absolute top-0 left-0 w-full h-8 bg-gradient-to-b from-[#08080A] to-transparent pointer-events-none z-10" />
          
          {status.status === "failed" ? (
            <div className="text-ember p-4 flex gap-4 items-start bg-ember/10 border border-ember h-full">
              <AlertTriangle className="flex-shrink-0" />
              <span className="text-base font-mono">{status.error}</span>
            </div>
          ) : (
            <div className="flex flex-col gap-1 relative z-0 h-full overflow-y-auto custom-scrollbar pt-6">
              <div className="text-frost font-mono flex gap-3 pb-2 mb-2 border-b border-iron/50 items-center top-0 sticky bg-[#08080A]">
                <Loader2 size={12} className="animate-spin" /> 
                <span className="uppercase tracking-[0.2em]">Live Telemetry Feed...</span>
              </div>
              
              {logs.map((log, i) => {
                const color = log.type === 'error' ? 'text-ember' : log.type === 'warn' ? 'text-burnt' : 'text-bone';
                const opacity = i > 10 ? 'opacity-30' : i > 5 ? 'opacity-60' : 'opacity-100';
                
                return (
                  <div key={i} className={`flex gap-3 items-start transition-all font-mono ${color} ${opacity} hover:opacity-100`}>
                     {log.type === 'error' ? <span className="text-ember">⚠</span> : log.type === 'warn' ? <span className="text-burnt">⏳</span> : <span className="text-frost">✔</span>}
                    <span className="break-all leading-tight">{log.msg}</span>
                  </div>
                );
              })}
            </div>
          )}
          
          <div className="absolute bottom-0 left-0 w-full h-12 bg-gradient-to-t from-[#08080A] to-transparent pointer-events-none z-10" />
        </div>
      </div>

      {/* Right: Telemetry Side Panel */}
      <div className="w-full md:w-80 flex flex-col gap-6 sticky top-6">
        <div className="runic-panel p-8 flex flex-col gap-8 bg-obsidian/50 backdrop-blur-md h-full min-h-[400px]">
          <h3 className="font-bebas text-3xl text-bone uppercase tracking-[0.15em] border-b-2 border-iron pb-4">
            System State
          </h3>
          
          <div className="flex flex-col gap-1 border-b border-iron pb-4">
            <span className="text-iron font-bebas tracking-[0.2em] text-sm">Status</span>
            <span className="font-mono font-bold text-frost uppercase flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-frost animate-pulse" />
              {status.status}
            </span>
          </div>

          <div className="flex flex-col gap-1 border-b border-iron pb-4">
            <span className="text-iron font-bebas tracking-[0.2em] text-sm">Data Volume</span>
            <span className="font-inter font-bold text-bone text-2xl flex items-baseline gap-1">
              {Math.floor(status.progress * Math.random() * 152)} <span className="text-iron text-sm font-normal">nodes</span>
            </span>
          </div>

          <div className="flex flex-col gap-1 pb-4 border-b border-iron">
             <span className="text-iron font-bebas tracking-[0.2em] text-sm">Anomalies Detected</span>
             <span className="font-mono font-bold text-ember text-xl">
               {logs.filter(l => l.type === 'error').length}
             </span>
          </div>

        </div>
      </div>
    </div>
  );
}
