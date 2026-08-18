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

For the bounded set of Day-3 hotspots, HeatShield creates one expanded bounding box and one historical Overpass query instead of one remote call per hotspot. The query uses exact tag-value filters rather than value-regex scans, reducing historical query work and payload size. Returned relevant objects are assigned locally with a meter-scale spatial grid and exact Haversine distance filtering.

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
- fallback Overpass instance for retryable transport **and semantic** service errors
- HTTP 200 is not treated as success by itself: any non-empty Overpass `remark` is rejected as a semantic provider failure
- invalid/timeout cache entries are never reused as zero-context evidence
- exact tag-value filters are used for the bounded historical query to reduce regex-scan cost
- no silent population/occupancy imputation
- no inference from missing OSM objects
- explicit OSM attribution and license metadata

## Output

`data/processed/day4_exposure_context.json`

Raw cache:

`data/raw/day4/`

Both are runtime evidence and are intentionally Git ignored.

## Day 4.1 correctness correction

A live diagnostic found an Overpass response with HTTP 200, `elements: []`, and a `remark` reporting a query timeout. The original Day-4 client accepted that transport-success response and cached it, which could incorrectly turn a provider timeout into “zero mapped context.”

Day 4.1 fixes this by separating **transport success** from **semantic success**. A valid zero-result response must have a real `elements` list and no non-empty `remark`. Timeout/runtime responses are rejected, retried, and allowed to fall back to the secondary endpoint. The raw cache records request count, rejected semantic responses, attempted endpoints, and a `response_semantically_valid` flag.

This correction does not change the scientific interpretation: mapped context presence is evidence of nearby mapped features only, while mapped absence remains unknown/not-observed rather than proof of real-world absence.

## Day 4.2 resilience correction

Historical Overpass queries are now split into five small category-specific bounding-box queries: healthcare, education, transit waiting, outdoor public, and civic/public. Each query uses exact tag values and is executed sequentially with endpoint failover. A third public global/attic Overpass endpoint is configured as an additional fallback.

Provider availability is represented per category. A category may be `observed` (including a legitimate zero count) or `unavailable_provider_failure`. An unavailable category is **unknown**, not zero, and must not be used as evidence that mapped context is absent. If every category query fails, Day 4 stops and produces no new zero-context artifact.

Only semantically valid Overpass responses are cached. HTTP 200 responses with a non-empty `remark`, malformed payloads, network failures, and other provider failures are not cached as evidence.
