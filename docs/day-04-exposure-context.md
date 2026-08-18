# Day 4 — Exposure Context Intelligence

## Objective

Add mapped, time-aligned context around Day-3 hotspot evidence without claiming population exposure, occupancy, vulnerability, or health risk.

## Data source

Day 4 uses OpenStreetMap data through the Overpass API. The query requests the OSM database state at the Day-3 environmental observation timestamp when available. The raw response is cached locally and remains Git ignored.

Required attribution when presenting OSM-derived context: **© OpenStreetMap contributors**. OSM data are provided under the Open Database License (ODbL).

## Context taxonomy

Deterministic categories:

- healthcare: hospital, clinic, doctors, social facility
- education: school, kindergarten, college, university
- transit_waiting: bus stop, bus station, public-transport platform/station
- outdoor_public: park, playground, garden, pitch
- civic_public: community centre, library, town hall, marketplace

These categories identify **exposure-context candidates only**. They do not assign epidemiological weights and do not imply that people are present.

## Query strategy and complexity

For the bounded set of Day-3 hotspots, HeatShield creates one expanded bounding box and one historical Overpass query instead of one remote call per hotspot. Returned relevant objects are assigned locally with a meter-scale spatial grid and exact Haversine distance filtering.

Approximate local complexity:

- query-bounds construction: `O(k)`
- response parsing/deduplication: `O(p)`
- spatial index build: `O(k)`
- spatial candidate assignment: approximately `O(p + a)` for local candidate checks, followed by exact distance tests
- per-hotspot display ordering: `O(sum(m_i log m_i))`

Where `k` is the small hotspot count, `p` is returned relevant OSM objects, `a` is local candidate assignments, and `m_i` is nearby context objects for hotspot `i`. Network latency remains dominant.

## Reliability controls

- historical snapshot alignment using provider timestamps when possible
- SHA-256 provenance from Day 3 into Day 4
- one-query local cache keyed by deterministic query fingerprint
- sequential Overpass use with a named User-Agent
- fallback Overpass instance for retryable service errors
- no silent population/occupancy imputation
- no inference from missing OSM objects
- explicit OSM attribution and license metadata

## Output

`data/processed/day4_exposure_context.json`

Raw cache:

`data/raw/day4/`

Both are runtime evidence and are intentionally Git ignored.
