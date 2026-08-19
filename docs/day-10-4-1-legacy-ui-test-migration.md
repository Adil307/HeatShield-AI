# Day 10.4.1 — Legacy UI Test Migration

The Day 10.4 approved production UI was successfully applied, but the repository
still contained a Day 10.3 regression test that asserted obsolete implementation
details:

- literal text `OpenStreetMap basemap`;
- asset version `10.3.0`;
- old map container id `realMap`;
- an older safety sentence.

Those assertions are not product requirements. Day 10.4 uses:

- `thermalMap`;
- Leaflet + OpenStreetMap;
- Leaflet.heat for the derived smooth thermal visualization;
- app asset version `10.4.0`;
- the approved safety language.

This patch migrates the old Day 10.3 test to stable current product contracts.
It does not change HeatShield evidence, FortyGuard integration, priority scores,
recommendations, or Qwen behavior.
