"use client";

import { useState } from "react";
import LandingScreen from "@/components/LandingScreen";
import SourceSelection from "@/components/SourceSelection";
import ScrapingProgress from "@/components/ScrapingProgress";
import ResultsScreen from "@/components/ResultsScreen";

export default function Home() {
  const [stage, setStage] = useState<"landing" | "source-selection" | "scraping" | "results">("landing");
  const [jobId, setJobId] = useState<string | null>(null);

  return (
    <main className="min-h-screen bg-bg text-text p-6 lg:p-12 flex flex-col items-center">
      {stage === "landing" && (
        <LandingScreen 
          onStart={(id: string) => {
            setJobId(id);
            setStage("source-selection");
          }} 
        />
      )}
      
      {stage === "source-selection" && jobId && (
        <SourceSelection 
          jobId={jobId}
          onProceed={() => setStage("scraping")}
        />
      )}

      {stage === "scraping" && jobId && (
        <ScrapingProgress 
          jobId={jobId}
          onComplete={() => setStage("results")}
        />
      )}

      {stage === "results" && jobId && (
        <ResultsScreen 
          jobId={jobId}
          onRestart={() => {
            setJobId(null);
            setStage("landing");
          }}
        />
      )}
    </main>
  );
}
