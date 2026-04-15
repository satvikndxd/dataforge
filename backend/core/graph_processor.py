"""
NLP Graph Co-occurrence Module.
Extracts semantic entities and constructs topological datasets.
"""

import logging
from typing import List, Dict, Any, Tuple
import spacy
import networkx as nx

logger = logging.getLogger(__name__)

# Load small English model securely
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    logger.warning("spacy model 'en_core_web_sm' not found, ensure it is installed.")
    nlp = None

def extract_entities(text: str) -> List[str]:
    """Extract standard NER entities (ORG, PERSON, PRODUCT, GPE) from text."""
    if not nlp or not text:
        return []
    doc = nlp(text)
    entities = []
    for ent in doc.ents:
        if ent.label_ in ["ORG", "PERSON", "PRODUCT", "GPE", "WORK_OF_ART", "EVENT"]:
            # Clean entity text (e.g., removing trailing punctuation/newlines)
            clean_text = ent.text.strip().replace("\n", " ")
            if len(clean_text) > 2:
                entities.append(clean_text)
    return list(set(entities))

def build_graph(texts: List[str]) -> nx.Graph:
    """Builds a co-occurrence Graph."""
    G = nx.Graph()
    for text in texts:
        ents = extract_entities(text)
        # Add nodes
        for e in ents:
            if not G.has_node(e):
                G.add_node(e, weight=1)
            else:
                G.nodes[e]['weight'] += 1
                
        # Add edges (co-occurrence in same paragraph implies relationship)
        for i in range(len(ents)):
            for j in range(i+1, len(ents)):
                u, v = ents[i], ents[j]
                if G.has_edge(u, v):
                    G[u][v]['weight'] += 1
                else:
                    G.add_edge(u, v, weight=1)
    return G

def analyze_graph(G: nx.Graph) -> Dict[str, float]:
    """Runs simulated GNN behaviors via PageRank to score topological relevance."""
    if len(G) == 0:
        return {}
    try:
        # PageRank natively determines entity importance recursively!
        pagerank_scores = nx.pagerank(G, weight='weight')
        return pagerank_scores
    except Exception as e:
        logger.error(f"Graph analytics failed: {e}")
        return {}

def format_gnn_dataset(G: nx.Graph, pr_scores: Dict[str, float]) -> List[Tuple[Any, Dict, float]]:
    """Unpack networkX edges into final_items format."""
    items = []
    edges = G.edges(data=True)
    
    for u, v, data in edges:
        weight = data.get('weight', 1.0)
        u_score = pr_scores.get(u, 0.0)
        v_score = pr_scores.get(v, 0.0)
        avg_score = (u_score + v_score) / 2.0
        
        # Only keep somewhat prominent edges or nodes to avoid noise
        if weight >= 1: 
            meta = {
                "source_node": u,
                "target_node": v,
                "relationship_type": "semantic_co_occurrence",
                "edge_weight": weight,
                "source_pagerank": round(u_score, 4),
                "target_pagerank": round(v_score, 4)
            }
            # Add to tuple representing (url, item, score). URL is generic since an edge spans multiple documents.
            items.append(("Synthesized Graph", meta, round(avg_score * 100, 3)))
            
    # Sort by relevance descending
    items.sort(key=lambda x: x[2], reverse=True)
    return items
