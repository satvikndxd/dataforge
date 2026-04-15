"""
Data Cleaning Module – HTML stripping, whitespace normalization, encoding fixes.
"""

import re
import unicodedata
import html
from typing import List, Tuple


# Patterns to strip
_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_NAV_PATTERNS = re.compile(
    r"^(home|about|contact|menu|navigation|skip to|cookie|privacy|terms|"
    r"subscribe|sign up|log in|login|search|all rights reserved|"
    r"copyright|\d{4}[-–]\d{4})",
    re.IGNORECASE,
)

_IMAGE_JUNK_PATTERNS = [
    "istock", "getty", "shutterstock", "stock images", "stock pictures", 
    "royalty-free", "premium high-res", "download free"
]

_IMAGE_BOILERPLATE_RE = re.compile(r"(stock pictures, royalty-free photos & images|royalty-free images|stock photos|high-res pictures).*", re.IGNORECASE)

MIN_CLEAN_LENGTH = 60


def clean_text(text: str) -> str:
    """Clean a single piece of text."""
    # Decode HTML entities
    text = html.unescape(text)

    # Strip HTML tags (if any remain)
    text = _HTML_TAG_RE.sub(" ", text)

    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)

    # Normalize whitespace
    text = _WHITESPACE_RE.sub(" ", text).strip()

    return text


def is_boilerplate(text: str) -> bool:
    """Return True if the text looks like nav/footer boilerplate."""
    if len(text) < MIN_CLEAN_LENGTH:
        return True
    if _NAV_PATTERNS.search(text.strip()):
        return True
    # Too many special chars → likely noise
    special_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / max(len(text), 1)
    if special_ratio > 0.35:
        return True
    return False


def clean_paragraphs(
    paragraphs: List[Tuple[str, str]],  # (url, text)
) -> List[Tuple[str, str]]:
    """
    Clean and filter a list of (url, text) pairs.
    Returns clean (url, text) pairs that pass boilerplate check.
    """
    cleaned = []
    for url, text in paragraphs:
        c = clean_text(text)
        if c and not is_boilerplate(c):
            cleaned.append((url, c))
    return cleaned


def clean_image_captions(
    items: List[Tuple[str, dict]],  # (url, item_dict)
) -> List[Tuple[str, dict]]:
    """
    Clean image captions, filtering out logo/stock image noise and stripping boilerplate.
    Returns cleaned (url, dict) pairs.
    """
    cleaned = []
    for url, item in items:
        caption = item.get("caption", "")
        if not caption:
            continue
            
        lower_cap = caption.lower()
        # Drop junk images entirely
        if any(junk in lower_cap for junk in _IMAGE_JUNK_PATTERNS):
            continue
            
        # Strip boilerplate text from the end
        clean_cap = _IMAGE_BOILERPLATE_RE.sub("", caption).strip()
        
        # Strip generic whitespace/html just in case
        clean_cap = clean_text(clean_cap)
        
        if len(clean_cap) > 3: # Must have some context
            new_item = item.copy()
            new_item["caption"] = clean_cap
            cleaned.append((url, new_item))
            
    return cleaned
