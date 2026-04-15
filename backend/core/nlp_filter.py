"""
NLP Filtering Module – TF-IDF relevance scoring.
Scores each paragraph against the research topic query.
"""

import logging
from typing import List, Tuple
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.05  # Minimum cosine similarity to keep a paragraph


def score_paragraphs(
    paragraphs: List[Tuple[str, str]],  # (url, text)
    topic: str,
    threshold: float = DEFAULT_THRESHOLD,
) -> List[Tuple[str, str, float]]:
    """
    Score all (url, text) pairs against the topic query using TF-IDF.
    Returns list of (url, text, score) for paragraphs above threshold.
    """
    if not paragraphs:
        return []

    texts = [topic] + [p[1] for p in paragraphs]

    try:
        vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=10000,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        tfidf_matrix = vectorizer.fit_transform(texts)
    except Exception as e:
        logger.error(f"TF-IDF vectorization failed: {e}")
        return []

    # Query vector is the first row (topic)
    query_vec = tfidf_matrix[0:1]
    doc_vecs = tfidf_matrix[1:]

    scores = cosine_similarity(query_vec, doc_vecs)[0]

    results = []
    for i, (url, text) in enumerate(paragraphs):
        score = float(scores[i])
        if score >= threshold:
            results.append((url, text, round(score, 4)))

    # Sort by relevance descending
    results.sort(key=lambda x: x[2], reverse=True)
    logger.info(
        f"NLP filter: {len(paragraphs)} paragraphs → {len(results)} retained "
        f"(threshold={threshold})"
    )
    return results


def enrich_image_semantics(
    items: List[Tuple[str, dict]],  # (url, item_dict)
    topic: str,
) -> List[Tuple[str, dict, float]]:
    """
    Enrich images with semantic tags, entities, and category.
    Calculates TF-IDF relevance score against the topic.
    Returns list of (url, enriched_dict, score).
    """
    import re
    from collections import Counter
    
    if not items:
        return []

    # Category heuristic mapping
    CATEGORIES = {
        "footwear": ["shoe", "sneaker", "boot", "footwear", "trainers", "heels"],
        "apparel": ["shirt", "jacket", "pants", "clothing", "apparel"],
        "nature": ["landscape", "mountain", "river", "forest", "tree", "ocean", "nature", "climate"],
        "technology": ["computer", "phone", "electronics", "circuit", "robot", "ai", "tech"],
        "person": ["man", "woman", "person", "crowd", "people", "child", "portrait"],
        "vehicle": ["car", "truck", "bike", "vehicle", "plane", "boat"]
    }

    # Common stopwords for English basic tag extraction
    STOPWORDS = {"the", "a", "an", "and", "or", "but", "is", "on", "in", "to", "for", "with", "of", "at", "by", "from", "as", "stock", "photo", "image", "picture", "royalty-free", "premium", "high-res"}

    # Compute textual scores for relevance
    texts = [topic] + [item.get("caption", "") for _, item in items]
    try:
        vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        tfidf_matrix = vectorizer.fit_transform(texts)
        scores = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
    except Exception as e:
        logger.error(f"Image semantic scoring failed: {e}")
        scores = [1.0] * len(items)

    enriched_results = []
    
    for i, (url, item) in enumerate(items):
        caption = item.get("caption", "")
        if not caption:
             continue
             
        score = float(scores[i])
        
        # 1. Extract Entities (Consecutive Capitalized Words)
        # E.g. "Nike Air Max" -> ["Nike Air Max"]
        entities = re.findall(r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b", caption)
        entities = list(set([e for e in entities if len(e) > 3 and e.lower() not in STOPWORDS]))
        
        # 2. Extract Tags (Nouns and descriptive words)
        words = re.findall(r"\b[a-zA-Z_-]+\b", caption.lower())
        tags = [w for w in words if len(w) > 2 and w not in STOPWORDS]
        tags = list(set(tags))[:5] # Max 5 unique tags
        
        # 3. Predict Category based on tags
        category = "general"
        for cat, keywords in CATEGORIES.items():
            if any(k in tags for k in keywords):
                category = cat
                break
                
        # Only keep reasonably relevant images, or boost strict topic matches
        # If it matches topic directly, boost score
        topic_words = topic.lower().split()
        if any(tw in caption.lower() for tw in topic_words if len(tw) > 3):
             score = max(score, 0.4)
             
        # Add to item
        enriched_item = item.copy()
        enriched_item["tags"] = tags
        enriched_item["entities"] = entities
        enriched_item["category"] = category
        
        enriched_results.append((url, enriched_item, round(score, 4)))

    # Sort by relevance descending
    enriched_results.sort(key=lambda x: x[2], reverse=True)
    return enriched_results
