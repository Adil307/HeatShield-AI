# Day 4.3 — Availability-Safe Operational Baseline

## Purpose

Day 4.3 builds the competition-demo evidence chain from a recent FortyGuard heatmap, deterministic thermal hotspot detection, time-aligned FortyGuard environmental parameters, and current OpenStreetMap context.

## Provider availability rule

A FortyGuard activity can reach `Completed` while returning zero GeoJSON heatmap features. That state is **not thermal evidence** and must never be interpreted as zero heat. It is retained as a negative availability artifact so the exact request is not resubmitted repeatedly.

The operational strategy uses a bounded candidate ladder:

1. near-current completed local hour (`--lag-hours`, default 1),
2. recent fallback (`--fallback-lag-hours`, default 24).

A recent completed-empty heatmap applies a short backoff to further near-current probes. This protects API credits and avoids repeated provider calls during a temporary availability gap. The number of new heatmap submissions is bounded by `--max-new-heatmap-submissions`.

If the fallback is selected, the artifact mode is `recent_operational_fallback`; downstream UI must display the selected observation time and must not call the result "live".

## Time semantics

The heatmap request documentation defines `start_time` as `HH:MM` but does not define an IANA timezone contract for that field. Therefore HeatShield does not force an external DST/UTC interpretation onto the provider response. Environmental enrichment must return the same requested local wall-clock date/hour; the provider's aware timestamp and offset are then retained as the authoritative observation timestamp.

This prevents a false mismatch when provider metadata uses an offset convention that differs from the host application's IANA timezone estimate.

## Evidence sequence

```text
bounded heatmap availability selection
  -> strict GeoJSON validation
  -> independent statistics verification
  -> O(n log k) relative hotspot selection
  -> time-aligned environmental enrichment
  -> current OSM bounded context query
  -> evidence-linked operational artifact
```

## Complexity and cost controls

- heatmap parsing/statistics: O(n)
- hotspot selection: O(n log k)
- environmental calls: O(k), with k intentionally small
- OSM context: one bounded union query plus local exact-distance checks
- completed-empty heatmap responses: cached as negative availability outcomes
- new heatmap submissions: hard bounded per run

## Scientific boundary

The operational artifact is not a clinical or individual health-risk score. Current OSM objects indicate mapped-place presence, not occupancy, population, vulnerability, or health impact. A recent fallback heatmap is clearly labeled with its actual age.
