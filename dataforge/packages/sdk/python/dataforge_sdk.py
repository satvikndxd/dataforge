"""DataForge V2 Python SDK — a thin, dependency-light client for /v1.

Usage:
    from dataforge_sdk import DataForge

    df = DataForge("http://localhost:8000", api_key="df_live_…")
    project = df.create_project("Legal corpus", goal="Instruction dataset for legal reasoning")
    df.add_inline_source(project["id"], title="Sample", text=open("doc.txt").read())
    run = df.run_pipeline(project["id"], auto_discover=False)
    run = df.wait_for_run(run["run_id"])
    version = df.latest_version(run["dataset_id"])
    df.export(version["id"], "jsonl", path="dataset.jsonl")
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class DataForgeError(RuntimeError):
    pass


class DataForge:
    def __init__(self, base_url: str = "http://localhost:8000",
                 api_key: str | None = None, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.token = token

    # -- transport ------------------------------------------------------
    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(f"{self.base_url}{path}", method=method)
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("X-API-Key", self.api_key)
        elif self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(req, data=data, timeout=60) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise DataForgeError(f"{exc.code} {path}: {detail}") from None

    def _download(self, path: str, dest: str) -> str:
        req = urllib.request.Request(f"{self.base_url}{path}")
        if self.api_key:
            req.add_header("X-API-Key", self.api_key)
        elif self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as fh:
            fh.write(resp.read())
        return dest

    # -- auth -----------------------------------------------------------
    def register(self, org_name: str, email: str, password: str) -> dict:
        data = self._request("POST", "/v1/auth/register",
                             {"org_name": org_name, "email": email, "password": password})
        self.token = data["access_token"]
        return data

    def login(self, email: str, password: str) -> dict:
        data = self._request("POST", "/v1/auth/login", {"email": email, "password": password})
        self.token = data["access_token"]
        return data

    # -- resources ------------------------------------------------------
    def create_project(self, name: str, goal: str = "", modality: str = "text") -> dict:
        return self._request("POST", "/v1/projects",
                             {"name": name, "goal": goal, "modality": modality})

    def add_url_source(self, project_id: str, url: str) -> dict:
        return self._request("POST", "/v1/sources",
                             {"project_id": project_id, "type": "url", "uri": url})

    def add_inline_source(self, project_id: str, title: str, text: str) -> dict:
        return self._request("POST", "/v1/sources",
                             {"project_id": project_id, "type": "inline",
                              "config": {"title": title, "text": text}})

    def run_pipeline(self, project_id: str, **config) -> dict:
        return self._request("POST", "/v1/pipelines/run",
                             {"project_id": project_id, **config})

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/v1/runs/{run_id}")

    def wait_for_run(self, run_id: str, timeout: float = 600, interval: float = 2.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.get_run(run_id)
            if run["status"] in ("succeeded", "failed", "cancelled"):
                if run["status"] != "succeeded":
                    raise DataForgeError(f"run {run_id} {run['status']}: {run.get('error')}")
                return run
            time.sleep(interval)
        raise DataForgeError(f"run {run_id} did not finish within {timeout}s")

    def latest_version(self, dataset_id: str) -> dict:
        dataset = self._request("GET", f"/v1/datasets/{dataset_id}")
        if not dataset.get("versions"):
            raise DataForgeError(f"dataset {dataset_id} has no versions")
        return dataset["versions"][0]

    def export(self, dataset_version_id: str, fmt: str = "jsonl",
               path: str | None = None, timeout: float = 300) -> str | dict:
        job = self._request("POST", "/v1/exports",
                            {"dataset_version_id": dataset_version_id, "format": fmt})
        export_id = job["export_id"]
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self._request("GET", f"/v1/exports/{export_id}")
            if job["status"] == "succeeded":
                if path:
                    return self._download(f"/v1/exports/{export_id}/download", path)
                return job
            if job["status"] == "failed":
                raise DataForgeError(f"export failed: {job.get('error')}")
            time.sleep(1.0)
        raise DataForgeError("export timed out")

    def invoke_agent(self, agent: str, params: dict, project_id: str = "") -> dict:
        return self._request("POST", f"/v1/agents/{agent}/invoke",
                             {"project_id": project_id, "params": params})
