"""Semantic chunking for LLM/RAG use cases (spec §6.2 stage 7).

Splits on heading/paragraph boundaries, packs paragraphs into chunks within
a token budget, preserves context headers and adds configurable overlap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^(#{1,6}\s+.+|[A-Z][A-Za-z0-9 ,'\-]{2,80}:?)$")


@dataclass
class TextChunk:
    content: str
    position: int
    token_estimate: int
    meta: dict = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def chunk_text(text: str, *, target_tokens: int = 400, overlap_tokens: int = 40,
               min_tokens: int = 30) -> list[TextChunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[TextChunk] = []
    current: list[str] = []
    current_tokens = 0
    current_heading = ""

    def flush():
        nonlocal current, current_tokens
        if not current:
            return
        body = "\n\n".join(current)
        if estimate_tokens(body) >= min_tokens or not chunks:
            chunks.append(
                TextChunk(
                    content=body,
                    position=len(chunks),
                    token_estimate=estimate_tokens(body),
                    meta={"heading": current_heading} if current_heading else {},
                )
            )
        elif chunks:  # too small — merge into previous
            chunks[-1].content += "\n\n" + body
            chunks[-1].token_estimate = estimate_tokens(chunks[-1].content)
        current, current_tokens = [], 0

    for para in paragraphs:
        first_line = para.split("\n", 1)[0].strip()
        is_heading = len(para) < 120 and bool(_HEADING_RE.match(first_line))
        para_tokens = estimate_tokens(para)

        if is_heading:
            flush()
            current_heading = first_line.lstrip("# ").rstrip(":")
            current = [para]
            current_tokens = para_tokens
            continue

        if current_tokens + para_tokens > target_tokens and current:
            flush()
            # context header + overlap tail from previous chunk
            if chunks and overlap_tokens > 0:
                tail_words = chunks[-1].content.split()[-overlap_tokens:]
                if tail_words:
                    current = [" ".join(tail_words)]
                    current_tokens = estimate_tokens(current[0])
            if current_heading:
                current.insert(0, f"[{current_heading}]")
        current.append(para)
        current_tokens += para_tokens

    flush()
    return chunks
