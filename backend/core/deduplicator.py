"""
Deduplication Module – Exact match + near-duplicate removal.
Uses SHA1 hash for exact dedup, TF-IDF cosine similarity for fuzzy dedup.
"""

import hashlib
import logging
from typing import List, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.85  # Cosine similarity above this → duplicate


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def deduplicate(
    items: List[Tuple[str, str, float]],  # (url, text, score)
    similarity_threshold: float = SIMILARITY_THRESHOLD,
) -> List[Tuple[str, str, float]]:
    """
    Remove exact and near-duplicate text entries.
    Returns deduplicated list preserving the highest-scored copy.
    """
    if not items:
        return []

    # Step 1: Exact dedup by hash
    seen_hashes = set()
    unique = []
    for url, text, score in items:
        h = _sha1(text.strip().lower())
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append((url, text, score))

    logger.info(f"Dedup exact: {len(items)} → {len(unique)}")

    if len(unique) <= 1:
        return unique

    # Step 2: Fuzzy dedup via TF-IDF cosine similarity
    texts = [t for _, t, _ in unique]
    try:
        vec = TfidfVectorizer(stop_words="english", max_features=5000, sublinear_tf=True)
        matrix = vec.fit_transform(texts)
    except Exception as e:
        logger.warning(f"Fuzzy dedup vectorization failed: {e}")
        return unique

    n = len(unique)
    keep = [True] * n

    # Compare each pair; mark lower-scored as duplicate
    sim_matrix = cosine_similarity(matrix)

    for i in range(n):
        if not keep[i]:
            continue
        for j in range(i + 1, n):
            if not keep[j]:
                continue
            if sim_matrix[i][j] >= similarity_threshold:
                # Keep the one with higher relevance score
                if unique[i][2] >= unique[j][2]:
                    keep[j] = False
                else:
                    keep[i] = False
                    break

    result = [item for item, k in zip(unique, keep) if k]
    logger.info(f"Dedup fuzzy: {len(unique)} → {len(result)}")
    return result
