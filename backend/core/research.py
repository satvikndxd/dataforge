"""
Research Engine – DuckDuckGo/Wikipedia based web search.
Returns ranked list of source URLs for a given topic.
"""

import logging
from typing import List, Dict
from urllib.parse import urlparse
import requests

logger = logging.getLogger(__name__)


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lstrip("www.")
        return domain
    except Exception:
        return url


def search_topic(topic: str, num_results: int = 20, modality: str = "text") -> List[Dict]:
    """
    Search DuckDuckGo via HTML parsing for highly relevant source lists.
    Augments the original query strategically based on Target Modality to find specific dataset formats.
    """
    results = []
    logger.info(f"Scraping relevant sources for: {topic} (Modality: {modality})")
    
    try:
        from bs4 import BeautifulSoup
        import urllib.parse
        
        # Augment the exact query being sent to DuckDuckGo to force specific dataset sites
        query = topic
        if modality == "image_cnn":
            query += " high resolution images gallery photos"
        elif modality == "audio":
            query += " audio clips sound wav mp3 download"
        elif modality == "graph_gnn":
            query += " categories hierarchy taxonomy relationships"
        elif modality == "network":
            query += " data statistics table csv numerical"
            
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for div in soup.find_all('div', class_='result__body'):
            if len(results) >= num_results:
                break
                
            title_a = div.find('a', class_='result__a')
            url_a = div.find('a', class_='result__url')
            
            if not title_a:
                continue
                
            title = title_a.get_text(strip=True)
            # DDG markup changes frequently; title anchor is the most stable URL source.
            href = title_a.get('href', '') or (url_a.get('href', '') if url_a else '')
            
            # DuckDuckGo sometimes wraps URLs in a tracking redirect
            if href.startswith('//duckduckgo.com/l/?uddg=') or href.startswith('/l/?uddg=') or "duckduckgo.com/l/?uddg=" in href:
                try:
                    actual_url = urllib.parse.unquote(href.split('uddg=')[1].split('&')[0])
                except IndexError:
                    actual_url = href
            else:
                actual_url = href
                
            # Filter out ads and empty links
            if "duckduckgo.com" in actual_url or "bing.com/aclick" in actual_url or not actual_url.startswith("http"):
                continue
                
            score = round(1.0 - (len(results) * 0.02), 3)
            
            results.append({
                "title": title,
                "url": actual_url,
                "domain": _extract_domain(actual_url),
                "relevance_score": max(score, 0.1),
                "selected": True,
            })
            
    except Exception as e:
        logger.error(f"Search algorithm failed: {e}")

    return results
