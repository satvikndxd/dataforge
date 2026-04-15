"""
Dataset Generator – Converts processed records to CSV or JSON.
"""

import csv
import json
import io
import uuid
from datetime import datetime, timezone
from typing import List, Tuple, Any

def build_records(
    items: List[Tuple[str, Any, float]],  # (url, item, score)
    modality: str = "text"
) -> List[dict]:
    """Convert pipeline output to STRICT Universal Unified Format dicts."""
    ts = datetime.now(tz=timezone.utc).isoformat()
    records = []
    
    # standardize the type nomenclature
    stype = "text"
    if modality == "image_cnn": stype = "image"
    elif modality == "audio": stype = "audio"
    elif modality == "graph_gnn": stype = "graph"
    elif modality == "network": stype = "network"
    
    for url, item, score in items:
        
        # Extract main content organically
        content = ""
        if stype == "text":
            content = item
        elif stype == "image":
            content = item.get("caption", "")
        elif stype == "audio":
            content = item.get("transcript", "")
        elif stype == "graph":
            content = f"{item.get('source_node', '')} -> {item.get('target_node', '')}"
        
        # Build comprehensive metadata layer
        metadata = {
            "source_url": url,
            "timestamp": ts,
            "relevance_score": score
        }
        
        # New root semantic elements
        tags = []
        entities = []
        category = "general"
        
        if isinstance(item, dict):
            tags = item.pop("tags", [])
            entities = item.pop("entities", [])
            category = item.pop("category", "general")
            
            for k, v in item.items():
                if k not in ["caption", "transcript"]: # Keep generic
                    metadata[k] = v
                    
        # Strict viva-approved format
        record = {
            "id": f"{stype}_{str(uuid.uuid4())[:8]}",
            "type": stype,
            "content": content,
            "tags": tags,
            "entities": entities,
            "category": category,
            "metadata": metadata
        }
        records.append(record)
        
    return records

def to_json(records: List[dict]) -> str:
    """Serialize records to a pretty JSON string."""
    return json.dumps(records, indent=2, ensure_ascii=False)


def to_csv(records: List[dict]) -> str:
    """Serialize unified records to flattened dynamic CSV string."""
    if not records:
        return ""

    output = io.StringIO()
    
    # Collect all flattened keys safely
    fieldnames = ["id", "type", "content"]
    meta_keys = []
    for r in records:
        for k in r.get("metadata", {}).keys():
            if k not in meta_keys:
                meta_keys.append(k)
                
    ordered_fieldnames = fieldnames + [f"metadata.{k}" for k in meta_keys]

    writer = csv.DictWriter(
        output,
        fieldnames=ordered_fieldnames,
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )
    writer.writeheader()
    for record in records:
        row = {
            "id": record["id"],
            "type": record["type"],
            "content": record["content"]
        }
        for mk in meta_keys:
            row[f"metadata.{mk}"] = record.get("metadata", {}).get(mk, "")
        writer.writerow(row)

    return output.getvalue()
