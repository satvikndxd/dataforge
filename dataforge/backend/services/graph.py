"""Knowledge graph construction (spec §6.8).

Entity extraction via capitalization/pattern heuristics (spaCy NER is used
automatically when installed), co-occurrence relation extraction with
confidence scores, canonicalization by normalized name, persistence in the
relational store (Neo4j adapter optional).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from backend.core.ids import new_id
from backend.db.base import session_scope
from backend.db.models import GraphEntity, GraphRelation

try:
    import spacy  # type: ignore

    _NLP = None

    def _load_spacy():  # pragma: no cover
        global _NLP
        if _NLP is None:
            _NLP = spacy.load("en_core_web_sm")
        return _NLP

    HAS_SPACY = True
except ImportError:
    HAS_SPACY = False

# stop-ish words that begin sentences and masquerade as entities
_SENTENCE_STARTERS = {
    "the", "this", "that", "these", "those", "it", "he", "she", "they", "we", "you", "i",
    "a", "an", "in", "on", "at", "for", "but", "and", "or", "however", "although",
    "when", "while", "after", "before", "if", "as", "by", "with", "from", "to", "of",
    "there", "here", "its", "his", "her", "their", "our", "one", "some", "many", "most",
    "according", "meanwhile", "moreover", "furthermore", "finally", "first", "second",
}

_ENTITY_RE = re.compile(r"\b([A-Z][a-zA-Z0-9&'.-]+(?:\s+[A-Z][a-zA-Z0-9&'.-]+){0,4})\b")


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str = "concept"
    count: int = 1


def canonical_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def extract_entities(text: str, limit: int = 30) -> list[ExtractedEntity]:
    if HAS_SPACY:  # pragma: no cover - optional heavy dep
        doc = _load_spacy()(text[:100_000])
        counts: Counter = Counter()
        types: dict[str, str] = {}
        for ent in doc.ents:
            if ent.label_ in ("PERSON", "ORG", "GPE", "LOC", "PRODUCT", "EVENT", "WORK_OF_ART", "NORP"):
                counts[ent.text.strip()] += 1
                types[ent.text.strip()] = ent.label_.lower()
        return [ExtractedEntity(n, types.get(n, "concept"), c) for n, c in counts.most_common(limit)]

    counts: Counter = Counter()
    for match in _ENTITY_RE.finditer(text):
        candidate = match.group(1).strip()
        first_word = candidate.split()[0].lower()
        if first_word in _SENTENCE_STARTERS and len(candidate.split()) == 1:
            continue
        if len(candidate) < 3 or candidate.isupper() and len(candidate) > 12:
            continue
        counts[candidate] += 1
    # require repetition for single-word candidates to reduce noise
    entities = [
        ExtractedEntity(name, "concept", count)
        for name, count in counts.most_common(limit * 2)
        if count >= 2 or len(name.split()) >= 2
    ]
    return entities[:limit]


def extract_relations(text: str, entities: list[ExtractedEntity]) -> list[tuple[str, str, float]]:
    """Co-occurrence relations: entities sharing a sentence get an edge whose
    confidence grows with co-occurrence count."""
    names = [e.name for e in entities]
    if len(names) < 2:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pair_counts: Counter = Counter()
    for sentence in sentences:
        present = [n for n in names if n in sentence]
        for i, a in enumerate(present):
            for b in present[i + 1:]:
                if a != b:
                    pair_counts[tuple(sorted((a, b)))] += 1
    return [
        (a, b, min(0.95, 0.4 + 0.15 * count))
        for (a, b), count in pair_counts.most_common(60)
    ]


def upsert_graph(org_id: str, project_id: str, text: str,
                 document_id: str | None = None,
                 min_confidence: float = 0.5) -> dict:
    """Extract + link + prune + persist. Returns counts."""
    entities = extract_entities(text)
    relations = extract_relations(text, entities)

    with session_scope() as session:
        key_to_id: dict[str, str] = {}
        for ent in entities:
            key = canonical_key(ent.name)
            if not key:
                continue
            row = (
                session.query(GraphEntity)
                .filter_by(org_id=org_id, project_id=project_id, canonical_key=key)
                .one_or_none()
            )
            if row:
                row.mentions += ent.count
            else:
                row = GraphEntity(
                    id=new_id("ent"), org_id=org_id, project_id=project_id,
                    name=ent.name, entity_type=ent.entity_type,
                    canonical_key=key, mentions=ent.count,
                )
                session.add(row)
                session.flush()
            key_to_id[key] = row.id

        added_edges = 0
        for a, b, confidence in relations:
            if confidence < min_confidence:
                continue  # low-confidence edge quarantine
            ka, kb = canonical_key(a), canonical_key(b)
            if ka not in key_to_id or kb not in key_to_id:
                continue
            exists = (
                session.query(GraphRelation)
                .filter_by(org_id=org_id, project_id=project_id,
                           source_entity_id=key_to_id[ka], target_entity_id=key_to_id[kb])
                .one_or_none()
            )
            if exists:
                exists.confidence = min(0.99, max(exists.confidence, confidence))
            else:
                session.add(
                    GraphRelation(
                        id=new_id("rel"), org_id=org_id, project_id=project_id,
                        source_entity_id=key_to_id[ka], target_entity_id=key_to_id[kb],
                        relation="co_occurs_with", confidence=confidence,
                        evidence_document_id=document_id,
                    )
                )
                added_edges += 1

    return {"entities": len(entities), "relations": added_edges}


def get_graph(org_id: str, project_id: str, limit: int = 200) -> dict:
    with session_scope() as session:
        nodes = (
            session.query(GraphEntity)
            .filter_by(org_id=org_id, project_id=project_id)
            .order_by(GraphEntity.mentions.desc())
            .limit(limit)
            .all()
        )
        node_ids = {n.id for n in nodes}
        edges = (
            session.query(GraphRelation)
            .filter_by(org_id=org_id, project_id=project_id)
            .order_by(GraphRelation.confidence.desc())
            .limit(limit * 3)
            .all()
        )
        return {
            "nodes": [
                {"id": n.id, "name": n.name, "type": n.entity_type, "mentions": n.mentions}
                for n in nodes
            ],
            "edges": [
                {"source": e.source_entity_id, "target": e.target_entity_id,
                 "relation": e.relation, "confidence": e.confidence}
                for e in edges
                if e.source_entity_id in node_ids and e.target_entity_id in node_ids
            ],
        }
