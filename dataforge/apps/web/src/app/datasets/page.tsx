"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Shell, { PageTitle } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<any[]>([]);

  useEffect(() => {
    api("/v1/datasets?limit=100").then((d) => setDatasets(d.items)).catch(() => {});
  }, []);

  return (
    <Shell>
      <PageTitle kicker="Registry" title="Datasets" />
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {datasets.map((d) => (
          <Link key={d.id} href={`/datasets/${d.id}`}
                className="panel p-5 hover:-translate-y-0.5 transition-transform relative">
            <div className="absolute top-0 right-0 w-6 h-6 bg-blue border-l-2 border-b-2 border-ink" />
            <div className="font-display font-bold text-lg uppercase truncate">{d.name}</div>
            <div className="font-mono text-[11px] text-steel mt-1 truncate">{d.id}</div>
            <div className="flex items-center justify-between mt-4 text-xs">
              <span className="chip">{d.current_version_id ? "versioned" : "empty"}</span>
              <span className="text-steel">{fmtDate(d.created_at)}</span>
            </div>
          </Link>
        ))}
        {datasets.length === 0 && (
          <div className="panel p-8 col-span-full text-center">
            <p className="font-display font-bold text-xl uppercase mb-2">No datasets yet</p>
            <p className="text-steel mb-4">Run a pipeline to produce your first versioned dataset.</p>
            <Link href="/builder" className="btn">Open builder</Link>
          </div>
        )}
      </div>
    </Shell>
  );
}
