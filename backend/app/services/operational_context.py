from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from app.services.context_intelligence import BoundingBox, expanded_bbox
from app.services.context_taxonomy import CATEGORY_ORDER, overpass_filters_for_category
from app.services.day3_artifact import Day3ContextInput


@dataclass(frozen=True, slots=True)
class OperationalContextQuery:
    query: str
    query_sha256: str
    bbox: BoundingBox


def build_current_context_query(
    hotspots: Iterable[Day3ContextInput],
    *,
    radius_meters: float,
    timeout_seconds: int = 25,
) -> OperationalContextQuery:
    """Build one bounded current-data query for all context categories.

    Current OSM data avoids the heavier attic/history lookup used by Day 4 historical mode.
    Exact tag-value filters are retained and all categories succeed or fail as one evidence query.
    """
    selected = tuple(hotspots)
    bbox = expanded_bbox(((item.latitude, item.longitude) for item in selected), radius_meters)
    if not 10 <= timeout_seconds <= 120:
        raise ValueError("timeout_seconds must be between 10 and 120.")

    statements: list[str] = []
    for category in CATEGORY_ORDER:
        statements.extend(overpass_filters_for_category(category))

    filters = "\n  ".join(statements)
    query = (
        f'[out:json][timeout:{timeout_seconds}][bbox:{bbox.as_overpass()}];\n'
        "(\n"
        f"  {filters}\n"
        ");\n"
        "out center tags qt;"
    )
    query_sha = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return OperationalContextQuery(query=query, query_sha256=query_sha, bbox=bbox)
