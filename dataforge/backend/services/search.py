"""Source discovery (spec §6.5).

Built-in source adapters: Wikipedia (API), arXiv (API), DuckDuckGo
(when duckduckgo-search is installed), plus user-provided seed URLs and
inline documents. Adapters share a common candidate shape and are selected
by the Search Agent based on modality/domain policy. Additional adapters
ship as source plugins.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SourceCandidate:
    url: str
    title: str = ""
    snippet: str = ""
    provider: str = ""
    authority: float = 0.5
    meta: dict = field(default_factory=dict)


def search_wikipedia(query: str, limit: int = 5) -> list[SourceCandidate]:
    try:
        resp = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "search", "srsearch": query,
                "srlimit": limit, "format": "json", "utf8": 1,
            },
            timeout=get_settings().fetch_timeout_seconds,
            headers={"User-Agent": get_settings().user_agent},
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        return [
            SourceCandidate(
                url=f"https://en.wikipedia.org/wiki/{r['title'].replace(' ', '_')}",
                title=r["title"],
                snippet=r.get("snippet", ""),
                provider="wikipedia",
                authority=0.92,
            )
            for r in results
        ]
    except Exception as exc:
        logger.warning("wikipedia search failed: %s", exc)
        return []


def search_arxiv(query: str, limit: int = 5) -> list[SourceCandidate]:
    try:
        resp = httpx.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "max_results": limit},
            timeout=get_settings().fetch_timeout_seconds,
        )
        resp.raise_for_status()
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(resp.text)
        out = []
        for entry in root.findall("a:entry", ns):
            link = entry.findtext("a:id", "", ns)
            out.append(
                SourceCandidate(
                    url=link,
                    title=(entry.findtext("a:title", "", ns) or "").strip(),
                    snippet=(entry.findtext("a:summary", "", ns) or "").strip()[:400],
                    provider="arxiv",
                    authority=0.95,
                )
            )
        return out
    except Exception as exc:
        logger.warning("arxiv search failed: %s", exc)
        return []


def search_duckduckgo(query: str, limit: int = 8) -> list[SourceCandidate]:
    try:
        from duckduckgo_search import DDGS  # type: ignore

        with DDGS() as ddgs:
            return [
                SourceCandidate(
                    url=r.get("href", ""),
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                    provider="duckduckgo",
                    authority=0.5,
                )
                for r in ddgs.text(query, max_results=limit)
                if r.get("href")
            ]
    except Exception as exc:
        logger.warning("duckduckgo search unavailable: %s", exc)
        return []


PROVIDERS = {
    "wikipedia": search_wikipedia,
    "arxiv": search_arxiv,
    "duckduckgo": search_duckduckgo,
}


def discover(queries: list[str], providers: list[str] | None = None,
             limit_per_query: int = 5) -> list[SourceCandidate]:
    """Fan a query set across providers, dedupe by URL, rank by authority."""
    providers = providers or ["wikipedia", "duckduckgo"]
    seen: dict[str, SourceCandidate] = {}
    for query in queries:
        for name in providers:
            fn = PROVIDERS.get(name)
            if not fn:
                continue
            for cand in fn(query, limit_per_query):
                if cand.url and cand.url not in seen:
                    seen[cand.url] = cand
    ranked = sorted(seen.values(), key=lambda c: c.authority, reverse=True)
    return ranked
