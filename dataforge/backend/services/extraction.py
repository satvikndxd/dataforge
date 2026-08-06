"""Fetching + content extraction (spec §6.2 stages 2–4).

Policy-first scraping: robots.txt compliance, per-domain throttling,
paywall/captcha detection (detect → quarantine, never bypass), size limits,
raw-evidence retention. Extraction prefers trafilatura when installed and
falls back to a dependency-free readability heuristic.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

try:
    import trafilatura  # type: ignore

    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False


# ---------------------------------------------------------------------------
# Robots + rate limiting
# ---------------------------------------------------------------------------

_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_domain_last_fetch: dict[str, float] = {}
_rate_lock = threading.Lock()


def robots_allows(url: str, user_agent: str | None = None) -> bool:
    settings = get_settings()
    if not settings.respect_robots_txt:
        return True
    user_agent = user_agent or settings.user_agent
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = httpx.get(f"{base}/robots.txt", timeout=5.0, follow_redirects=True,
                             headers={"User-Agent": user_agent})
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                _robots_cache[base] = rp
            else:
                _robots_cache[base] = None  # no robots -> allowed
        except Exception:
            _robots_cache[base] = None
    rp = _robots_cache[base]
    return True if rp is None else rp.can_fetch(user_agent, url)


def _throttle(domain: str) -> None:
    settings = get_settings()
    with _rate_lock:
        last = _domain_last_fetch.get(domain, 0.0)
        wait = settings.domain_rate_limit_seconds - (time.time() - last)
        _domain_last_fetch[domain] = max(time.time(), last + settings.domain_rate_limit_seconds)
    if wait > 0:
        time.sleep(min(wait, 5.0))


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    url: str
    status: str                     # ok | robots_blocked | paywall | captcha | error | too_large
    content: bytes = b""
    mime_type: str = "text/html"
    detail: str = ""


_PAYWALL_MARKERS = ["subscribe to continue", "subscription required", "metered paywall",
                    "purchase this article", "already a subscriber"]
_CAPTCHA_MARKERS = ["recaptcha", "hcaptcha", "verify you are human", "cf-challenge",
                    "attention required! | cloudflare"]


def fetch_url(url: str) -> FetchResult:
    settings = get_settings()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return FetchResult(url=url, status="error", detail="unsupported scheme")
    if not robots_allows(url):
        return FetchResult(url=url, status="robots_blocked", detail="disallowed by robots.txt")
    _throttle(parsed.netloc)
    try:
        resp = httpx.get(
            url,
            timeout=settings.fetch_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml,*/*"},
        )
    except httpx.HTTPError as exc:
        return FetchResult(url=url, status="error", detail=str(exc))

    if resp.status_code in (401, 402):
        return FetchResult(url=url, status="paywall", detail=f"http {resp.status_code}")
    if resp.status_code == 403:
        return FetchResult(url=url, status="captcha", detail="http 403 (likely bot protection)")
    if resp.status_code >= 400:
        return FetchResult(url=url, status="error", detail=f"http {resp.status_code}")
    if len(resp.content) > settings.max_document_bytes:
        return FetchResult(url=url, status="too_large", detail=f"{len(resp.content)} bytes")

    mime = resp.headers.get("content-type", "text/html").split(";")[0].strip()
    body_lower = resp.text[:20000].lower() if mime.startswith("text") else ""
    if any(m in body_lower for m in _CAPTCHA_MARKERS):
        return FetchResult(url=url, status="captcha", detail="captcha markers detected")
    if any(m in body_lower for m in _PAYWALL_MARKERS):
        return FetchResult(url=url, status="paywall", detail="paywall markers detected")
    return FetchResult(url=url, status="ok", content=resp.content, mime_type=mime)


# ---------------------------------------------------------------------------
# HTML extraction (readability-style fallback, no external deps)
# ---------------------------------------------------------------------------

_BOILERPLATE_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript",
                     "iframe", "svg", "button", "select"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title = ""
        self.blocks: list[str] = []
        self._current: list[str] = []
        self._block_tags = {"p", "div", "article", "section", "li", "h1", "h2", "h3", "h4",
                            "blockquote", "pre", "td", "figcaption", "br"}

    def handle_starttag(self, tag, attrs):
        if tag in _BOILERPLATE_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self._block_tags:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _BOILERPLATE_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self._block_tags:
            self._flush()

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data.strip()[:300]
            return
        self._current.append(data)

    def _flush(self):
        text = " ".join("".join(self._current).split())
        if text:
            self.blocks.append(text)
        self._current = []


@dataclass
class Extracted:
    title: str = ""
    text: str = ""
    confidence: float = 0.0
    extractor: str = "readability-fallback"
    links: list[str] = field(default_factory=list)


def extract_html(html: str, url: str = "") -> Extracted:
    if HAS_TRAFILATURA:
        try:
            text = trafilatura.extract(html, url=url or None, include_comments=False) or ""
            meta = trafilatura.extract_metadata(html)
            if text.strip():
                return Extracted(
                    title=(meta.title if meta else "") or "",
                    text=text.strip(),
                    confidence=0.9,
                    extractor="trafilatura",
                )
        except Exception:
            pass

    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    # keep blocks that look like prose (drop menus/short link farms)
    blocks = [b for b in parser.blocks if len(b) > 60 or (len(b.split()) > 8)]
    text = "\n\n".join(blocks)
    conf = 0.7 if len(text) > 400 else (0.4 if text else 0.0)
    return Extracted(title=parser.title, text=text, confidence=conf)


def extract_document(content: bytes, mime_type: str, url: str = "") -> Extracted:
    """Route to the right extractor by content type (spec §6.3 supported inputs)."""
    mime = (mime_type or "").lower()
    if "html" in mime or "xml" in mime:
        return extract_html(content.decode("utf-8", errors="replace"), url)
    if mime.startswith("text/") or "json" in mime or "markdown" in mime:
        text = content.decode("utf-8", errors="replace")
        return Extracted(text=text.strip(), confidence=0.95, extractor="plaintext")
    if "pdf" in mime:
        return _extract_pdf(content)
    return Extracted(text="", confidence=0.0, extractor="unsupported",
                     title=f"unsupported mime type: {mime}")


def _extract_pdf(content: bytes) -> Extracted:
    try:  # optional dependency
        from pypdf import PdfReader  # type: ignore
        import io

        reader = PdfReader(io.BytesIO(content))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages[:200])
        return Extracted(text=text.strip(), confidence=0.85, extractor="pypdf")
    except Exception:
        return Extracted(text="", confidence=0.0, extractor="pdf-unavailable")


# ---------------------------------------------------------------------------
# Cleaning + normalization (spec §6.2 stages 4–5)
# ---------------------------------------------------------------------------

_DISCLAIMER_RE = re.compile(
    r"(all rights reserved|terms of (service|use)|privacy policy|cookie (policy|settings)"
    r"|©\s*\d{4}|subscribe to our newsletter)[^\n]*",
    re.IGNORECASE,
)


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[​‌‍﻿]", "", text)          # zero-width chars
    text = re.sub(r"[ \t]+", " ", text)
    text = _DISCLAIMER_RE.sub("", text)
    # drop repeated identical lines (footers) while preserving order
    seen: dict[str, int] = {}
    lines = text.split("\n")
    for line in lines:
        key = line.strip().lower()
        if key:
            seen[key] = seen.get(key, 0) + 1
    cleaned = [
        line for line in lines
        if not (len(line.strip()) < 80 and seen.get(line.strip().lower(), 0) > 3)
    ]
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_language(text: str) -> str:
    """Cheap language detection (en/es/fr/de/other heuristic)."""
    sample = text[:2000].lower()
    scores = {
        "en": sum(sample.count(f" {w} ") for w in ("the", "and", "of", "to", "is")),
        "es": sum(sample.count(f" {w} ") for w in ("el", "la", "los", "que", "es")),
        "fr": sum(sample.count(f" {w} ") for w in ("le", "la", "les", "des", "est")),
        "de": sum(sample.count(f" {w} ") for w in ("der", "die", "und", "das", "ist")),
    }
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 2 else "unknown"


_LICENSE_HINTS = [
    (re.compile(r"creative commons|cc[- ]by(?:[- ]sa|[- ]nc)?", re.I), "cc-by", 0.8),
    (re.compile(r"public domain|cc0", re.I), "public-domain", 0.85),
    (re.compile(r"mit license", re.I), "mit", 0.9),
    (re.compile(r"apache license", re.I), "apache-2.0", 0.9),
    (re.compile(r"all rights reserved", re.I), "proprietary", 0.7),
]


def detect_license(text: str, domain: str = "") -> tuple[str, float]:
    """Never asserts legal certainty — returns (hint, confidence)."""
    if domain.endswith("wikipedia.org"):
        return "cc-by-sa", 0.9
    if domain.endswith("arxiv.org"):
        return "arxiv-license", 0.8
    tail = text[-4000:] + text[:1000]
    for pattern, hint, conf in _LICENSE_HINTS:
        if pattern.search(tail):
            return hint, conf
    return "unknown", 0.3
