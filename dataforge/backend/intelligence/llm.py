"""LLM model router.

Routes calls to Anthropic models when credentials are available and degrades
to deterministic heuristic implementations otherwise, so every pipeline stage
and agent works offline. Router policy (spec §20.3): cheap models first,
expensive models only for high-value stages.

Tiers:
- "reasoning" -> claude-opus-4-8   (research planning, evaluation rubrics)
- "cheap"     -> claude-haiku-4-5  (cleaning hints, tagging, summaries)
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

try:
    import anthropic  # official SDK

    HAS_ANTHROPIC_SDK = True
except ImportError:  # pragma: no cover
    HAS_ANTHROPIC_SDK = False


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    offline: bool = False

    @property
    def cost_usd(self) -> float:
        # claude-opus-4-8: $5/M in, $25/M out; claude-haiku-4-5: $1/M in, $5/M out
        rates = {
            "claude-opus-4-8": (5.0, 25.0),
            "claude-haiku-4-5": (1.0, 5.0),
        }
        rin, rout = rates.get(self.model, (5.0, 25.0))
        return (self.input_tokens * rin + self.output_tokens * rout) / 1_000_000


class LLMRouter:
    """Multi-provider-ready router with an offline deterministic fallback."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None
        if HAS_ANTHROPIC_SDK and self.settings.anthropic_api_key:
            self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)

    @property
    def online(self) -> bool:
        return self._client is not None

    def _model_for(self, tier: str) -> str:
        return self.settings.llm_default_model if tier == "reasoning" else self.settings.llm_cheap_model

    def complete(self, prompt: str, *, system: str = "", tier: str = "cheap",
                 max_tokens: int | None = None) -> LLMResult:
        model = self._model_for(tier)
        if self._client is not None:
            try:
                kwargs: dict = {
                    "model": model,
                    "max_tokens": max_tokens or self.settings.llm_max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system:
                    kwargs["system"] = system
                if tier == "reasoning":
                    kwargs["thinking"] = {"type": "adaptive"}
                response = self._client.messages.create(**kwargs)
                text = next((b.text for b in response.content if b.type == "text"), "")
                return LLMResult(
                    text=text,
                    model=model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )
            except Exception as exc:  # provider failure -> degrade gracefully
                logger.warning("LLM call failed (%s); falling back to offline heuristics", exc)
        return LLMResult(text=self._offline_complete(prompt), model="offline-heuristic", offline=True)

    def complete_json(self, prompt: str, *, tier: str = "cheap") -> dict | list | None:
        result = self.complete(
            prompt + "\n\nRespond with valid JSON only — no prose, no markdown fences.",
            tier=tier,
        )
        text = result.text.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Offline heuristics — deterministic and cheap, keyed off the prompt
    # ------------------------------------------------------------------

    @staticmethod
    def _offline_complete(prompt: str) -> str:
        lower = prompt.lower()
        if "summar" in lower:
            body = prompt.split("\n\n")[-1]
            sentences = re.split(r"(?<=[.!?])\s+", body.strip())
            return " ".join(sentences[:3])[:600]
        if "keyword" in lower or "topic" in lower or "tag" in lower:
            words = re.findall(r"[a-zA-Z]{5,}", prompt)
            common = [w for w, _ in Counter(w.lower() for w in words).most_common(8)]
            return ", ".join(common)
        return "OFFLINE: no LLM provider configured; heuristic pipeline stages remain fully functional."


_router: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


def reset_llm_router() -> None:
    global _router
    _router = None
