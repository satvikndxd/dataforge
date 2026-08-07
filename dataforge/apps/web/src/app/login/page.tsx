"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ org_name: "", email: "", password: "", name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const path = mode === "login" ? "/v1/auth/login" : "/v1/auth/register";
      const body =
        mode === "login"
          ? { email: form.email, password: form.password }
          : form;
      const data = await api(path, { method: "POST", body });
      setToken(data.access_token);
      router.replace("/");
    } catch (err: any) {
      setError(err.message || "authentication failed");
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden p-6">
      <div className="absolute -top-20 -left-20 w-64 h-64 rounded-full bg-yellow border-2 border-ink" aria-hidden />
      <div className="absolute bottom-10 -right-16 w-52 h-52 bg-blue border-2 border-ink rotate-12" aria-hidden />

      <div className="panel relative z-10 w-full max-w-md p-8">
        <div className="flex items-center gap-2 mb-6">
          <span className="w-5 h-5 rounded-full bg-red border-2 border-ink" />
          <span className="w-5 h-5 bg-blue border-2 border-ink" />
          <span className="font-display font-bold text-2xl tracking-tight ml-1">
            DATA<span className="text-red">FORGE</span> <span className="text-steel text-base">V2</span>
          </span>
        </div>

        <div className="flex gap-2 mb-6">
          {(["login", "register"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`chip flex-1 py-2 ${mode === m ? "bg-ink text-paper" : "bg-surface text-steel"}`}
            >
              {m === "login" ? "Sign in" : "Create org"}
            </button>
          ))}
        </div>

        {error && (
          <div className="border-2 border-ink bg-red text-paper text-sm font-bold px-3 py-2 mb-4">{error}</div>
        )}

        <form onSubmit={submit} className="space-y-4">
          {mode === "register" && (
            <div>
              <label className="label">Organization</label>
              <input className="input" required value={form.org_name}
                     onChange={(e) => setForm({ ...form, org_name: e.target.value })}
                     placeholder="Acme Research" />
            </div>
          )}
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" required value={form.email}
                   onChange={(e) => setForm({ ...form, email: e.target.value })}
                   placeholder="you@example.com" />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" required minLength={8} value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })}
                   placeholder="min 8 characters" />
          </div>
          <button className="btn w-full" disabled={busy}>
            {busy ? "Working…" : mode === "login" ? "Sign in" : "Create organization"}
          </button>
        </form>
      </div>
    </div>
  );
}
