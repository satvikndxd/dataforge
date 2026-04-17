"""
Scraping Engine – Multi-threaded, multi-modal HTML scraper.
Extracts text, images, graphs, audio, or network tables based on the requested modality.
"""

import logging
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Any
import time
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

TIMEOUT = 10
MIN_PARA_LENGTH = 50


def _extract_text(soup) -> List[str]:
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    paragraphs = []
    for elem in soup.find_all(["p", "article", "section"]):
        text = elem.get_text(separator=" ", strip=True)
        if len(text) >= MIN_PARA_LENGTH:
            paragraphs.append(text)
    return paragraphs


def _extract_images(soup, base_url) -> List[Dict[str, str]]:
    images = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        full_url = urljoin(base_url, src)
        alt = img.get("alt", "")
        # Try to find contextual caption
        caption = alt
        if not caption:
             parent = img.find_parent(["figure", "div", "p"])
             if parent:
                 caption = parent.get_text(strip=True)[:200]
        if len(caption) > 5 and full_url.startswith("http"):
             images.append({"image_url": full_url, "caption": caption})
    return images


def _extract_audio(soup, base_url) -> List[Dict[str, str]]:
    audio_items = []
    for audio in soup.find_all(["audio", "source", "a"]):
        src = audio.get("src") or audio.get("href")
        if not src or not (src.split("?")[0].endswith(".mp3") or src.split("?")[0].endswith(".wav") or src.split("?")[0].endswith(".ogg")):
            continue
        full_url = urljoin(base_url, src)
        parent = audio.find_parent(["div", "p", "article"])
        transcript = parent.get_text(strip=True)[:300] if parent else ""
        if full_url.startswith("http"):
            audio_items.append({"audio_url": full_url, "context_transcript": transcript})
    return audio_items


def _extract_graph(soup) -> List[Dict[str, str]]:
    edges = []
    # Build relationships from Header -> List representations
    for h in soup.find_all(["h2", "h3", "h4"]):
        source_node = h.get_text(strip=True)
        if not source_node or len(source_node) > 50:
            continue
        sibling = h.find_next_sibling(["ul", "ol", "p"])
        if sibling and sibling.name in ["ul", "ol"]:
            for li in sibling.find_all("li"):
                target_node = li.get_text(strip=True)[:50]
                if target_node:
                    edges.append({
                        "source_node": source_node,
                        "target_node": target_node,
                        "relationship_type": "contains/relates_to"
                    })
    return edges


def _extract_network(soup) -> List[Dict[str, str]]:
    rows = []
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all(["th", "td"])[:10]]
        # Fill missing header names
        headers = [h if h else f"feature_{i}" for i, h in enumerate(headers)]
        for tr in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td"])]
            if cells and len(cells) <= len(headers):
                row_dict = {}
                for i, cell in enumerate(cells):
                    row_dict[headers[i]] = cell
                rows.append(row_dict)
    return rows


def _scrape_url(url: str, modality: str = "text") -> Tuple[str, List[Any], str]:
    """
    Scrape a single URL. Returns extracted modular items.
    status: 'ok' | 'timeout' | 'error'
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        items = []
        if modality == "image_cnn":
            items = _extract_images(soup, url)
        elif modality == "audio":
            items = _extract_audio(soup, url)
        elif modality == "graph_gnn":
            # NLP extraction requires full raw context instead of header tags
            items = _extract_text(soup)
        elif modality == "network":
            items = _extract_network(soup)
        else: # text
            items = _extract_text(soup)

        return url, items, "ok"

    except requests.exceptions.Timeout:
        logger.warning(f"Timeout: {url}")
        return url, [], "timeout"
    except requests.exceptions.TooManyRedirects:
        logger.warning(f"Too many redirects: {url}")
        return url, [], "error"
    except Exception as e:
        logger.warning(f"Error scraping {url}: {e}")
        return url, [], "error"


def scrape_urls(
    sources: List[Dict],
    progress_callback=None,
    max_workers: int = 8,
    modality: str = "text"
) -> Dict[str, List[Any]]:
    """
    Scrape all selected sources concurrently for the designated modality.
    """
    results = {}
    total = len(sources)
    completed = 0

    urls = [s["url"] for s in sources if s.get("selected", True)]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(_scrape_url, url, modality): url for url in urls}

        for future in as_completed(future_to_url):
            url, items, status = future.result()
            if items:
                results[url] = items
            completed += 1

            if progress_callback:
                pct = int((completed / total) * 100)
                progress_callback(url=url, status=status, progress=pct)

            time.sleep(0.1)

    return results
