"use client";

import { useEffect, useState } from "react";
import Shell, { ErrorNote, PageTitle } from "@/components/Shell";
import { api, fmtDate } from "@/lib/api";

export default function ReviewsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [status, setStatus] = useState("pending");
  const [error, setError] = useState("");

  const load = () => api(`/v1/reviews?status=${status}`).then((d) => setItems(d.items)).catch(() => {});
  useEffect(() => { load(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  const decide = async (id: string, decision: "approved" | "rejected") => {
    setError("");
    try { await api(`/v1/reviews/${id}`, { method: "POST", body: { decision } }); load(); }
    catch (e: any) { setError(e.message); }
  };

  return (
    <Shell>
      <PageTitle kicker="Governance Plane" title="Review" accent="Queue" />
      <ErrorNote error={error} />
      <div className="flex gap-2 mb-6">
        {["pending", "approved", "rejected"].map((s) => (
          <button key={s} onClick={() => setStatus(s)}
                  className={`chip px-4 py-1.5 ${status === s ? "bg-ink text-paper" : ""}`}>
            {s}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        {items.map((item) => (
          <div key={item.id} className="panel p-5">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="chip bg-blue text-paper">{item.subject_type}</span>
              <span className="font-mono text-xs text-steel">{item.subject_id}</span>
              <span className="chip bg-yellow">priority {Number(item.priority).toFixed(2)}</span>
              <span className="text-xs text-steel ml-auto">{fmtDate(item.created_at)}</span>
            </div>
            <p className="font-display font-bold text-sm uppercase mt-3">{item.reason}</p>
            {item.subject_preview && (
              <pre className="bg-paper border-2 border-line p-3 mt-3 text-xs whitespace-pre-wrap max-h-40 overflow-y-auto">
                {item.subject_preview}
              </pre>
            )}
            {status === "pending" && (
              <div className="flex gap-3 mt-4">
                <button className="btn text-xs" style={{ background: "#1F7A33" }}
                        onClick={() => decide(item.id, "approved")}>Approve</button>
                <button className="btn text-xs" onClick={() => decide(item.id, "rejected")}>Reject</button>
              </div>
            )}
          </div>
        ))}
        {items.length === 0 && (
          <div className="panel p-8 text-center">
            <p className="font-display font-bold text-xl uppercase">Queue is empty</p>
            <p className="text-steel mt-1">Uncertain records, PII flags and publish gates land here automatically.</p>
          </div>
        )}
      </div>
    </Shell>
  );
}
