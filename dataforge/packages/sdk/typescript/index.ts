/** DataForge V2 TypeScript SDK — zero-dependency client for the /v1 API. */

export interface DataForgeOptions {
  baseUrl?: string;
  apiKey?: string;
  token?: string;
}

export class DataForgeError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export class DataForge {
  private baseUrl: string;
  private apiKey?: string;
  private token?: string;

  constructor(options: DataForgeOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    this.apiKey = options.apiKey;
    this.token = options.token;
  }

  private async request<T = any>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;
    else if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!resp.ok) throw new DataForgeError(resp.status, await resp.text());
    return resp.json() as Promise<T>;
  }

  async register(orgName: string, email: string, password: string) {
    const data = await this.request<any>("POST", "/v1/auth/register", {
      org_name: orgName, email, password,
    });
    this.token = data.access_token;
    return data;
  }

  async login(email: string, password: string) {
    const data = await this.request<any>("POST", "/v1/auth/login", { email, password });
    this.token = data.access_token;
    return data;
  }

  createProject(name: string, goal = "", modality = "text") {
    return this.request("POST", "/v1/projects", { name, goal, modality });
  }

  addUrlSource(projectId: string, url: string) {
    return this.request("POST", "/v1/sources", { project_id: projectId, type: "url", uri: url });
  }

  addInlineSource(projectId: string, title: string, text: string) {
    return this.request("POST", "/v1/sources", {
      project_id: projectId, type: "inline", config: { title, text },
    });
  }

  runPipeline(projectId: string, config: Record<string, unknown> = {}) {
    return this.request("POST", "/v1/pipelines/run", { project_id: projectId, ...config });
  }

  getRun(runId: string) {
    return this.request("GET", `/v1/runs/${runId}`);
  }

  async waitForRun(runId: string, timeoutMs = 600_000, intervalMs = 2_000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const run: any = await this.getRun(runId);
      if (["succeeded", "failed", "cancelled"].includes(run.status)) {
        if (run.status !== "succeeded") throw new DataForgeError(500, run.error || run.status);
        return run;
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    throw new DataForgeError(408, `run ${runId} timed out`);
  }

  invokeAgent(agent: string, params: Record<string, unknown>, projectId = "") {
    return this.request("POST", `/v1/agents/${agent}/invoke`, {
      project_id: projectId, params,
    });
  }

  createExport(datasetVersionId: string, format = "jsonl") {
    return this.request("POST", "/v1/exports", {
      dataset_version_id: datasetVersionId, format,
    });
  }
}
