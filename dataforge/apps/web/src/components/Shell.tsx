"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity, Boxes, Database, GitBranch, Hammer, LayoutDashboard,
  ListChecks, LogOut, Puzzle, Settings, Share2,
} from "lucide-react";
import { getToken, setToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/builder", label: "Builder", icon: Hammer },
  { href: "/runs", label: "Pipelines", icon: GitBranch },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/agents", label: "Agents", icon: Activity },
  { href: "/reviews", label: "Review", icon: ListChecks },
  { href: "/graph", label: "Graph", icon: Share2 },
  { href: "/plugins", label: "Plugins", icon: Puzzle },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
    else setReady(true);
  }, [router]);

  if (!ready) return <div className="min-h-screen bg-paper" />;

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-60 shrink-0 border-r-2 border-ink bg-surface flex flex-col">
        <Link href="/" className="flex items-center gap-2 px-5 py-5 border-b-2 border-ink">
          <span className="w-6 h-6 rounded-full bg-red border-2 border-ink inline-block" />
          <span className="w-6 h-6 bg-blue border-2 border-ink inline-block" />
          <span
            className="inline-block w-0 h-0"
            style={{ borderLeft: "12px solid transparent", borderRight: "12px solid transparent", borderBottom: "22px solid #F5A800" }}
          />
          <span className="font-display font-bold text-lg tracking-tight ml-1">
            DATA<span className="text-red">FORGE</span>
          </span>
        </Link>
        <nav className="flex-1 py-4">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-3 px-5 py-2.5 font-display font-bold text-sm uppercase tracking-[0.1em] border-l-4 transition-colors ${
                  active
                    ? "border-red bg-paper text-ink"
                    : "border-transparent text-steel hover:text-ink hover:bg-paper"
                }`}
              >
                <Icon size={16} /> {label}
              </Link>
            );
          })}
        </nav>
        <button
          onClick={() => { setToken(null); router.replace("/login"); }}
          className="flex items-center gap-3 px-5 py-4 border-t-2 border-ink font-display font-bold text-sm uppercase tracking-[0.1em] text-steel hover:text-red"
        >
          <LogOut size={16} /> Sign out
        </button>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 p-8 lg:p-10">{children}</main>
    </div>
  );
}

export function PageTitle({ kicker, title, accent }: { kicker?: string; title: string; accent?: string }) {
  return (
    <div className="h-rule mb-8">
      {kicker && (
        <div className="font-display font-bold text-xs uppercase tracking-[0.3em] text-steel mb-1">{kicker}</div>
      )}
      <h1 className="font-display font-bold text-4xl uppercase tracking-tight">
        {title} {accent && <span className="text-red">{accent}</span>}
      </h1>
    </div>
  );
}

export function Stat({ label, value, color = "bg-surface" }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div className="panel p-5">
      <div className={`w-8 h-2 ${color} border border-ink mb-3`} />
      <div className="font-display font-bold text-3xl">{value}</div>
      <div className="font-display font-bold text-xs uppercase tracking-[0.2em] text-steel mt-1">{label}</div>
    </div>
  );
}

export function ErrorNote({ error }: { error: string }) {
  if (!error) return null;
  return (
    <div className="border-2 border-ink bg-red text-paper font-display font-bold text-sm uppercase tracking-wide px-4 py-3 mb-6">
      {error}
    </div>
  );
}
