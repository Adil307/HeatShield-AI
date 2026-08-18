from __future__ import annotations

import json
from typing import Any

import httpx

from app.domain.copilot import CopilotPlan


class CopilotProviderError(RuntimeError):
    pass


_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "summary",
                "why_priority",
                "recommendations",
                "missing_evidence",
                "compare_hotspots",
                "metric_lookup",
                "scenario_scope",
                "unsupported",
            ],
        },
        "primary_hotspot_rank": {"type": ["integer", "null"]},
        "comparison_hotspot_ranks": {"type": "array", "items": {"type": "integer"}, "maxItems": 6},
        "metric_keys": {"type": "array", "items": {"type": "string"}, "maxItems": 12},
        "recommendation_ids": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    },
    "required": [
        "intent",
        "primary_hotspot_rank",
        "comparison_hotspot_ranks",
        "metric_keys",
        "recommendation_ids",
    ],
    "additionalProperties": False,
}


SYSTEM_INSTRUCTIONS = """You are the planning layer for HeatShield AI. You NEVER write the final factual answer.
Your only job is to choose an allowed intent and select evidence metric keys / recommendation IDs from the supplied whitelist.
Never invent IDs, values, people counts, medical probabilities, current heat claims, or actions outside the supplied catalog.
Historical thermal evidence must remain historical. Current OpenStreetMap objects are mapped objects, not people or occupancy.
If the user asks for unsupported medical probability, current/live heat, or people exposure, choose scenario_scope.
Return only the structured plan required by the JSON schema."""


def _output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    output = payload.get("output")
    if not isinstance(output, list):
        raise CopilotProviderError("OpenAI Responses payload has no output content.")
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str) and part.get("text", "").strip():
                return part["text"]
    raise CopilotProviderError("OpenAI Responses payload contains no textual structured output.")


async def openai_plan(
    *,
    query: str,
    compact_context: dict[str, Any],
    api_key: str,
    model: str,
    timeout_seconds: float,
    max_output_tokens: int,
) -> CopilotPlan:
    if not api_key.strip():
        raise CopilotProviderError("OPENAI_API_KEY is not configured.")
    if not model.strip():
        raise CopilotProviderError("Copilot model is not configured.")

    request_payload = {
        "model": model,
        "store": False,
        "max_output_tokens": max_output_tokens,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": (
            "USER QUERY:\n"
            + query
            + "\n\nHEATSHIELD WHITELISTED CONTEXT:\n"
            + json.dumps(compact_context, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "heatshield_copilot_plan",
                "strict": True,
                "schema": _PLAN_SCHEMA,
            }
        },
    }

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            json=request_payload,
        )
    if response.status_code != 200:
        raise CopilotProviderError(f"OpenAI Responses API failed with HTTP {response.status_code}: {response.text[:500]}")
    try:
        payload = response.json()
        plan_json = json.loads(_output_text(payload))
    except (ValueError, TypeError) as exc:
        raise CopilotProviderError("OpenAI returned invalid structured copilot plan JSON.") from exc
    if not isinstance(plan_json, dict):
        raise CopilotProviderError("OpenAI copilot plan is not a JSON object.")
    return CopilotPlan(
        intent=str(plan_json.get("intent")),
        primary_hotspot_rank=plan_json.get("primary_hotspot_rank"),
        comparison_hotspot_ranks=tuple(plan_json.get("comparison_hotspot_ranks") or ()),
        metric_keys=tuple(plan_json.get("metric_keys") or ()),
        recommendation_ids=tuple(plan_json.get("recommendation_ids") or ()),
        planner="openai_responses_structured_planner",
    )
