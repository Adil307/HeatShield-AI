from __future__ import annotations

from collections.abc import Mapping


# Presence of these mapped features is context evidence only. This taxonomy does
# not imply occupancy, vulnerability, health impact or risk severity.
HEALTHCARE = {"hospital", "clinic", "doctors", "social_facility"}
EDUCATION = {"school", "kindergarten", "college", "university"}
CIVIC_PUBLIC = {"community_centre", "library", "townhall", "marketplace"}
OUTDOOR_PUBLIC = {"park", "playground", "garden", "pitch"}
PUBLIC_TRANSPORT = {"platform", "station"}

CATEGORY_ORDER = (
    "healthcare",
    "education",
    "transit_waiting",
    "outdoor_public",
    "civic_public",
)


def classify_context(tags: Mapping[str, str]) -> tuple[str, str] | None:
    amenity = tags.get("amenity")
    if amenity in HEALTHCARE:
        return "healthcare", amenity
    if amenity in EDUCATION:
        return "education", amenity
    if tags.get("highway") == "bus_stop":
        return "transit_waiting", "bus_stop"
    if amenity == "bus_station":
        return "transit_waiting", "bus_station"
    public_transport = tags.get("public_transport")
    if public_transport in PUBLIC_TRANSPORT:
        return "transit_waiting", public_transport
    leisure = tags.get("leisure")
    if leisure in OUTDOOR_PUBLIC:
        return "outdoor_public", leisure
    if amenity in CIVIC_PUBLIC:
        return "civic_public", amenity
    return None


def overpass_tag_filters() -> tuple[str, ...]:
    amenity_values = sorted(HEALTHCARE | EDUCATION | CIVIC_PUBLIC | {"bus_station"})
    return (
        f'nwr["amenity"~"^({"|".join(amenity_values)})$"];',
        'nwr["highway"="bus_stop"];',
        f'nwr["public_transport"~"^({"|".join(sorted(PUBLIC_TRANSPORT))})$"];',
        f'nwr["leisure"~"^({"|".join(sorted(OUTDOOR_PUBLIC))})$"];',
    )
