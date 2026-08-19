from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.domain.copilot import CopilotPlan


class OllamaCopilotProviderError(RuntimeError):
    pass


_ALLOWED_INTENTS = [
    "summary",
    "why_priority",
    "recommendations",
    "missing_evidence",
    "compare_hotspots",
    "metric_lookup",
    "scenario_scope",
    "unsupported",
]

LOCAL_ROUTE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": _ALLOWED_INTENTS},
        "primary_hotspot_rank": {"type": ["integer", "null"]},
    },
    "required": ["intent", "primary_hotspot_rank"],
    "additionalProperties": False,
}

LOCAL_SYSTEM_INSTRUCTIONS = """You are the LOCAL intent-routing layer for HeatShield AI.
You NEVER write the final factual answer and you NEVER output evidence IDs or recommendation IDs.
Choose only the user's intent and, when explicitly referenced, the hotspot rank.
Never invent medical probabilities, people counts, current heat claims, evidence IDs, or actions.
If the user asks for current/live heat, medical/clinical risk probability, or people exposure, choose scenario_scope.
Return only the two-field JSON object required by the schema."""

_REQUIRED_KEYS = {"intent", "primary_hotspot_rank"}
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.I | re.S)
_CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.I | re.S)


def _chat_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if not base:
        raise OllamaCopilotProviderError("OLLAMA_BASE_URL is not configured.")
    if base.endswith("/api"):
        return f"{base}/chat"
    return f"{base}/api/chat"


def _strict_route_shape(plan_json: Any) -> dict[str, Any]:
    if not isinstance(plan_json, dict):
        raise OllamaCopilotProviderError("Ollama local route is not a JSON object.")

    keys = set(plan_json)
    if keys != _REQUIRED_KEYS:
        missing = sorted(_REQUIRED_KEYS - keys)
        extras = sorted(keys - _REQUIRED_KEYS)
        raise OllamaCopilotProviderError(
            f"Ollama local route has an invalid key set; missing={missing}, extras={extras}."
        )

    intent = plan_json["intent"]
    primary = plan_json["primary_hotspot_rank"]
    if intent not in _ALLOWED_INTENTS:
        raise OllamaCopilotProviderError("Ollama local route intent is unsupported.")
    if primary is not None and (isinstance(primary, bool) or not isinstance(primary, int)):
        raise OllamaCopilotProviderError("Ollama primary_hotspot_rank must be integer or null.")
    return plan_json


def _decode_structured_content(content: str) -> dict[str, Any]:
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
    if parsed is None:
        raise OllamaCopilotProviderError("Ollama returned invalid structured local-route JSON.")
    return _strict_route_shape(parsed)


def _response_content(payload: Any) -> tuple[str, str | None]:
    if not isinstance(payload, dict):
        raise OllamaCopilotProviderError("Ollama response is not a JSON object.")
    message = payload.get("message")
    if not isinstance(message, dict):
        raise OllamaCopilotProviderError("Ollama response has no message object.")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaCopilotProviderError("Ollama response contains no structured route content.")
    done_reason = payload.get("done_reason")
    return content, done_reason if isinstance(done_reason, str) else None


def _router_context(compact_context: dict[str, Any]) -> dict[str, Any]:
    """Strip long opaque evidence/action IDs before the request reaches Qwen."""
    hotspots: list[dict[str, Any]] = []
    for item in compact_context.get("hotspots", []):
        if not isinstance(item, dict):
            continue
        hotspots.append(
            {
                "hotspot_rank": item.get("hotspot_rank"),
                "tile_id": item.get("tile_id"),
                "planning_priority": item.get("planning_priority"),
            }
        )
    return {
        "planning_order": compact_context.get("planning_order", []),
        "available_hotspot_ranks": compact_context.get("available_hotspot_ranks", []),
        "hotspots": hotspots,
        "constraints": compact_context.get("constraints", {}),
    }


def _request_payload(
    *,
    query: str,
    compact_context: dict[str, Any],
    model: str,
    max_output_tokens: int,
    keep_alive: str,
) -> dict[str, Any]:
    context_text = json.dumps(
        _router_context(compact_context),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return {
        "model": model.strip(),
        "messages": [
            {"role": "system", "content": LOCAL_SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": (
                    "USER QUERY:\n"
                    + query
                    + "\n\nROUTING CONTEXT:\n"
                    + context_text
                    + "\n\nReturn exactly one JSON object with only intent and primary_hotspot_rank."
                ),
            },
        ],
        "stream": False,
        "think": False,
        "format": LOCAL_ROUTE_JSON_SCHEMA,
        "keep_alive": keep_alive,
        "options": {
            "temperature": 0,
            "seed": 0,
            "num_predict": max(96, min(max_output_tokens, 192)),
        },
    }


async def ollama_plan(
    *,
    query: str,
    compact_context: dict[str, Any],
    base_url: str,
    model: str,
    timeout_seconds: float,
    max_output_tokens: int,
    keep_alive: str,
) -> CopilotPlan:
    if not model.strip():
        raise OllamaCopilotProviderError("OLLAMA_MODEL is not configured.")

    request_payload = _request_payload(
        query=query,
        compact_context=compact_context,
        model=model,
        max_output_tokens=max_output_tokens,
        keep_alive=keep_alive,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(_chat_url(base_url), json=request_payload)
    except httpx.RequestError as exc:
        raise OllamaCopilotProviderError(f"Local Ollama request failed: {exc}") from exc

    if response.status_code != 200:
        raise OllamaCopilotProviderError(
            f"Ollama chat API failed with HTTP {response.status_code}: {response.text[:500]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise OllamaCopilotProviderError("Ollama returned invalid JSON response.") from exc

    content, done_reason = _response_content(payload)
    try:
        route_json = _decode_structured_content(content)
    except OllamaCopilotProviderError as exc:
        preview = " ".join(content.split())[:240]
        raise OllamaCopilotProviderError(
            f"Ollama could not produce a valid two-field local route; "
            f"done_reason={done_reason!r}; content_preview={preview!r}; error={exc}"
        ) from exc

    return CopilotPlan(
        intent=str(route_json["intent"]),
        primary_hotspot_rank=route_json["primary_hotspot_rank"],
        planner="ollama_qwen_intent_router",
    )
