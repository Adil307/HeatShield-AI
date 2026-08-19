from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.day7_artifact import Day7ArtifactError, load_day7_source
from app.services.day8_artifact import Day8ArtifactError, Day8Source, load_day8_source


class CopilotContextError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CopilotContext:
    day7_sha256: str
    day8_sha256: str
    packets_by_rank: dict[int, dict[str, Any]]
    recommendations_by_rank: dict[int, dict[str, Any]]
    planning_order: tuple[int, ...]

    @property
    def ranks(self) -> tuple[int, ...]:
        return tuple(sorted(self.packets_by_rank))


def load_copilot_context(
    *,
    day7_path: str | Path,
    day8_path: str | Path,
    day6_path: str | Path | None = None,
    day5_path: str | Path | None = None,
    day44_path: str | Path | None = None,
    catalog_path: str | Path | None = None,
) -> CopilotContext:
    try:
        day7 = load_day7_source(day7_path, day6_path=day6_path, day5_path=day5_path, day44_path=day44_path)
        day8: Day8Source = load_day8_source(day8_path, day7_path=day7_path, catalog_path=catalog_path)
    except (Day7ArtifactError, Day8ArtifactError) as exc:
        raise CopilotContextError(str(exc)) from exc

    packets_by_rank = {int(packet["hotspot_rank"]): packet for packet in day7.packets}
    recommendations_by_rank = {int(item["hotspot_rank"]): item for item in day8.hotspots}
    if set(packets_by_rank) != set(recommendations_by_rank):
        raise CopilotContextError("Day 7 and Day 8 hotspot rank sets differ.")

    planning_order = tuple(int(item["hotspot_rank"]) for item in day8.hotspots)
    return CopilotContext(
        day7_sha256=day7.sha256,
        day8_sha256=day8.sha256,
        packets_by_rank=packets_by_rank,
        recommendations_by_rank=recommendations_by_rank,
        planning_order=planning_order,
    )


def ledger_index(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ledger = packet.get("evidence_ledger")
    if not isinstance(ledger, list):
        raise CopilotContextError("Explainability packet has no evidence ledger.")
    result: dict[str, dict[str, Any]] = {}
    for item in ledger:
        if not isinstance(item, dict):
            raise CopilotContextError("Evidence ledger entries must be objects.")
        key = item.get("key")
        if not isinstance(key, str) or not key or key in result:
            raise CopilotContextError("Evidence ledger keys must be unique non-empty strings.")
        result[key] = item
    return result


def compact_llm_context(context: CopilotContext) -> dict[str, Any]:
    hotspots: list[dict[str, Any]] = []
    for rank in context.planning_order:
        packet = context.packets_by_rank[rank]
        rec_hotspot = context.recommendations_by_rank[rank]
        ledger = ledger_index(packet)
        hotspots.append(
            {
                "hotspot_rank": rank,
                "tile_id": packet.get("tile_id"),
                "planning_priority": packet.get("pre_adaptation_priority_score"),
                "planning_priority_band": packet.get("pre_adaptation_priority_band"),
                "scenario_scope": packet.get("scenario_scope"),
                "metric_keys": [
                    {
                        "key": key,
                        "label": item.get("label"),
                        "classification": item.get("classification"),
                    }
                    for key, item in ledger.items()
                ],
                "recommendations": [
                    {
                        "recommendation_id": rec.get("recommendation_id"),
                        "action_id": rec.get("action_id"),
                        "title": rec.get("title"),
                        "priority_tier": rec.get("priority_tier"),
                        "status": rec.get("status"),
                    }
                    for rec in rec_hotspot.get("recommendations", [])
                    if isinstance(rec, dict)
                ],
            }
        )
    return {
        "planning_order": list(context.planning_order),
        "available_hotspot_ranks": list(context.ranks),
        "hotspots": hotspots,
        "constraints": {
            "historical_hazard_not_current": True,
            "mapped_objects_not_people": True,
            "medical_probability_forbidden": True,
            "recommendations_catalog_only": True,
        },
    }
