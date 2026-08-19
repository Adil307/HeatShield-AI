from __future__ import annotations

import json
import re
from typing import Any

import httpx


class LiveOllamaRouterError(RuntimeError):
    """Raised when the local Day 14 intent router cannot return a safe route."""


ALLOWED_LIVE_INTENTS = [
    "summary",
    "why_priority",
    "recommendations",
    "evidence",
    "decision_readiness",
    "metric_lookup",
    "compare_scope",
    "scope_boundary",
]

LIVE_ROUTE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ALLOWED_LIVE_INTENTS},
    },
    "required": ["intent"],
    "additionalProperties": False,
}

LIVE_ROUTER_SYSTEM = """You are the LOCAL intent-routing layer for HeatShield AI Day 14.
The current packet is a fresh provider-backed live analysis, not the historical replay.
You NEVER write the final factual answer and you NEVER invent or copy numbers, evidence IDs,
coordinates, people counts, medical probabilities, or recommendations.
Choose exactly one intent from the provided schema.
- why_priority: user asks why the live planning priority has its value or asks about contributions/factors.
- recommendations: user asks what action/check is supported.
- evidence: user asks where values came from, provenance, sources, or traceability.
- decision_readiness: user asks what is verified, missing, supported, withheld, or safe to conclude.
- metric_lookup: user asks for a specific live metric.
- compare_scope: user asks to compare hotspots/tiles or rank multiple live locations.
- scope_boundary: user asks for medical/clinical risk, diagnosis, people/occupancy counts, or unsupported certainty.
- summary: everything else.
Return only the JSON object required by the schema."""

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.I | re.S)
_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.I | re.S)


def _chat_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise LiveOllamaRouterError("OLLAMA_BASE_URL is not configured.")
    if base.endswith("/api"):
        return f"{base}/chat"
    return f"{base}/api/chat"


def _decode(content: str) -> str:
    text = _THINK_BLOCK.sub("", content).strip()
    fence = _CODE_FENCE.match(text)
    if fence:
        text = fence.group(1).strip()

    def load(candidate: str) -> Any:
        try:
            return json.loads(candidate)
        except ValueError:
            return None

    parsed = load(text)
    if isinstance(parsed, str):
        parsed = load(parsed.strip())
    if parsed is None:
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            parsed = load(text[first : last + 1])
    if not isinstance(parsed, dict) or set(parsed) != {"intent"}:
        raise LiveOllamaRouterError("Ollama live route must contain exactly one 'intent' field.")
    intent = parsed.get("intent")
    if intent not in ALLOWED_LIVE_INTENTS:
        raise LiveOllamaRouterError("Ollama live route selected an unsupported intent.")
    return str(intent)


async def ollama_live_intent(
    *,
    query: str,
    compact_context: dict[str, Any],
    base_url: str,
    model: str,
    timeout_seconds: float,
    max_output_tokens: int,
    keep_alive: str,
) -> str:
    """Use local Qwen only as a semantic router for the Day 14 live copilot.

    Numeric evidence is intentionally excluded from the routing context. The final
    factual answer is always rendered deterministically from the verified ledger.
    """
    if not model.strip():
        raise LiveOllamaRouterError("OLLAMA_MODEL is not configured.")

    routing_context = {
        "mode": "fresh_verified_live_analysis",
        "planning_priority_supported": bool(compact_context.get("planning_priority_supported")),
        "controlled_actions_available": bool(compact_context.get("controlled_actions_available")),
        "available_metric_keys": list(compact_context.get("available_metric_keys") or []),
        "constraints": {
            "medical_probability_supported": False,
            "people_or_occupancy_inference_supported": False,
            "llm_writes_final_factual_answer": False,
        },
    }
    payload = {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": LIVE_ROUTER_SYSTEM},
            {
                "role": "user",
                "content": (
                    "USER QUERY:\n"
                    + query
                    + "\n\nROUTING CONTEXT (no numeric evidence):\n"
                    + json.dumps(routing_context, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                    + "\n\nReturn exactly one JSON object with only the intent field."
                ),
            },
        ],
        "stream": False,
        "think": False,
        "format": LIVE_ROUTE_JSON_SCHEMA,
        "keep_alive": keep_alive,
        "options": {
            "temperature": 0,
            "seed": 0,
            "num_predict": max(64, min(max_output_tokens, 128)),
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(_chat_url(base_url), json=payload)
    except httpx.RequestError as exc:
        raise LiveOllamaRouterError(f"Local Ollama request failed: {exc}") from exc

    if response.status_code != 200:
        raise LiveOllamaRouterError(
            f"Ollama chat API failed with HTTP {response.status_code}: {response.text[:500]}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise LiveOllamaRouterError("Ollama returned invalid JSON response.") from exc
    message = body.get("message") if isinstance(body, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise LiveOllamaRouterError("Ollama returned no structured live-route content.")
    return _decode(content)
