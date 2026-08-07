"use client";

/** Typed-ish API client for the DataForge /v1 control plane. */

const TOKEN_KEY = "dataforge_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

export async function api<T = any>(
  path: string,
  options: { method?: string; body?: any; raw?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const resp = await fetch(path, {
    method: options.method || "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (resp.status === 401 && typeof window !== "undefined" && !path.includes("/auth/")) {
    setToken(null);
    window.location.href = "/login";
    throw new ApiError(401, "session expired");
  }
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const data = await resp.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {}
    throw new ApiError(resp.status, detail);
  }
  if (options.raw) return resp as unknown as T;
  return resp.json();
}

export const STAGE_COLORS: Record<string, string> = {
  pending: "bg-line",
  running: "bg-yellow",
  succeeded: "bg-green",
  failed: "bg-red",
};

export function fmtDate(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}
