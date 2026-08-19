const state = { snapshot: null, selectedRank: null, map: null, polygonLayer: null, heatLayer: null, markerLayer: null };

const $ = (id) => document.getElementById(id);
const fmt = (v, d = 1) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";
const metric = (v, suffix = "", d = 1) => typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(d)}${suffix}` : "—";
const esc = (v) => String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");

function tileIdOf(feature) {
  const p = feature?.properties || {};
  for (const key of ["tile_id","tileId","id","tile","grid_id"]) {
    if (p[key] !== undefined && p[key] !== null && !Number.isNaN(Number(p[key]))) return Number(p[key]);
  }
  return null;
}

function featureTemperature(feature) {
  const p = feature?.properties || {};
  for (const key of ["average_temperature","avg_temperature","average","avg","temperature","tcm","mean_temperature","mean"]) {
    if (typeof p[key] === "number" && Number.isFinite(p[key])) return p[key];
  }
  for (const [key, value] of Object.entries(p)) {
    if (typeof value === "number" && /temp|average|mean|tcm/i.test(key)) return value;
  }
  return null;
}

function selectedHotspot() {
  return state.snapshot?.hotspots?.find((h) => h.hotspot_rank === state.selectedRank) || null;
}

function featureCenter(feature) {
  const layer = L.geoJSON(feature);
  const bounds = layer.getBounds();
  return bounds.isValid() ? bounds.getCenter() : null;
}

function renderMap() {
  const geo = state.snapshot?.heatmap_geojson;
  const fallback = $("mapFallback");

  if (!geo?.features?.length || typeof L === "undefined") {
    $("thermalMap").classList.add("hidden");
    fallback.classList.remove("hidden");
    return;
  }

  $("thermalMap").classList.remove("hidden");
  fallback.classList.add("hidden");

  if (!state.map) {
    state.map = L.map("thermalMap", { zoomControl: true, attributionControl: true, preferCanvas: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(state.map);
  }

  if (state.polygonLayer) state.map.removeLayer(state.polygonLayer);
  if (state.heatLayer) state.map.removeLayer(state.heatLayer);
  if (state.markerLayer) state.map.removeLayer(state.markerLayer);

  const values = geo.features.map(featureTemperature).filter(Number.isFinite);
  const tMin = values.length ? Math.min(...values) : 0;
  const tMax = values.length ? Math.max(...values) : 1;
  const span = Math.max(tMax - tMin, 1e-9);

  state.polygonLayer = L.geoJSON(geo, {
    style: () => ({ color: "#5C6C82", weight: 0.35, fillColor: "#6E63F0", fillOpacity: 0.035 }),
    onEachFeature: (feature, layer) => {
      const tile = tileIdOf(feature);
      const temp = featureTemperature(feature);
      layer.bindTooltip(
        `<strong>Tile ${tile ?? "—"}</strong><br>${Number.isFinite(temp) ? `${temp.toFixed(2)} °C historical air temperature` : "Verified FortyGuard thermal evidence"}`,
        { sticky: true, direction: "top" }
      );
    }
  }).addTo(state.map);

  if (typeof L.heatLayer === "function") {
    const heatPoints = [];
    for (const feature of geo.features) {
      const center = featureCenter(feature);
      const temp = featureTemperature(feature);
      if (!center || !Number.isFinite(temp)) continue;
      const normalized = Math.max(0.05, Math.min(1, (temp - tMin) / span));
      heatPoints.push([center.lat, center.lng, normalized]);
    }
    state.heatLayer = L.heatLayer(heatPoints, {
      radius: 48,
      blur: 34,
      maxZoom: 17,
      minOpacity: 0.22,
      gradient: {
        0.00: "#2b67b1",
        0.25: "#2fa6ca",
        0.45: "#55c778",
        0.65: "#d8ca48",
        0.82: "#ef8b3c",
        1.00: "#e8543a"
      }
    }).addTo(state.map);
  }

  state.markerLayer = L.layerGroup().addTo(state.map);
  for (const hotspot of state.snapshot.hotspots) {
    const feature = geo.features.find((f) => tileIdOf(f) === Number(hotspot.tile_id));
    if (!feature) continue;
    const center = featureCenter(feature);
    if (!center) continue;

    const position = state.snapshot.planning_order.indexOf(hotspot.hotspot_rank) + 1;
    const icon = L.divIcon({
      className: `heatshield-marker rank-${position}`,
      html: `<div>${hotspot.hotspot_rank}</div>`,
      iconSize: position === 1 ? [34,34] : [30,30],
      iconAnchor: position === 1 ? [17,17] : [15,15]
    });

    const marker = L.marker(center, { icon }).addTo(state.markerLayer);
    marker.bindTooltip(`Hotspot ${hotspot.hotspot_rank} • Priority ${fmt(hotspot.planning_priority, 2)}`, { direction: "top" });
    marker.on("click", () => selectHotspot(hotspot.hotspot_rank));
  }

  const bounds = state.polygonLayer.getBounds();
  if (bounds.isValid()) state.map.fitBounds(bounds, { padding: [24,24], maxZoom: 15 });
  setTimeout(() => state.map.invalidateSize(), 80);
}

function renderKpis() {
  const s = state.snapshot.summary;
  const heat = state.snapshot.hotspots.map((h) => h.metrics.historical_heat_index_celsius).filter(Number.isFinite);
  const humid = state.snapshot.hotspots.map((h) => h.metrics.historical_relative_humidity_percent).filter(Number.isFinite);

  $("kpiTemp").textContent = metric(s.max_historical_air_temperature_celsius, "°C", 2);
  $("kpiHeatIndex").textContent = heat.length ? `${Math.max(...heat).toFixed(1)}°C` : "—";
  $("kpiHotspots").textContent = s.hotspot_count ?? "—";
  $("kpiPriority").textContent = fmt(s.highest_priority_score, 2);
  $("kpiPriorityRank").textContent = s.highest_priority_rank ? `Hotspot ${s.highest_priority_rank}` : "Verified planning order";
  $("kpiHumidity").textContent = humid.length ? `${(humid.reduce((a,b) => a + b, 0) / humid.length).toFixed(1)}%` : "—";
  $("kpiTiles").textContent = s.heatmap_feature_count ?? "—";
}

function contributionsOf(h) {
  return Object.fromEntries((h.contributions || []).filter((x) => x?.component).map((x) => [x.component, x]));
}

function renderSelected() {
  const h = selectedHotspot();
  if (!h) return;
  const m = h.metrics;
  const status = h.evidence_status;
  const position = state.snapshot.planning_order.indexOf(h.hotspot_rank) + 1;

  $("selectedHotspotTitle").textContent = `Hotspot ${h.hotspot_rank}`;
  $("priorityBand").textContent = (h.planning_priority_band || "planning priority").toUpperCase();
  $("selectedScore").textContent = fmt(h.planning_priority, 0);
  $("selectedTile").textContent = `Tile ${h.tile_id ?? "—"}`;
  $("selectedRank").textContent = `Priority Rank #${position}`;

  const gauge = $("selectedScore").closest(".gauge");
  const circle = gauge?.querySelector("circle:nth-of-type(2)");
  if (circle) {
    const circumference = 251.3;
    circle.setAttribute("stroke-dasharray", circumference);
    circle.setAttribute("stroke-dashoffset", circumference * (1 - Math.max(0, Math.min(100, h.planning_priority || 0)) / 100));
  }

  $("selectedMetrics").innerHTML = [
    ["Historical Air Temp", metric(m.historical_air_temperature_celsius, "°C", 2), "evidence"],
    ["Historical Heat Index", metric(m.historical_heat_index_celsius, "°C", 1), "evidence"],
    ["Relative Humidity", metric(m.historical_relative_humidity_percent, "%", 1), "evidence"],
    ["Mapped Exposure Proxy", metric(m.mapped_exposure_proxy, "", 2), "evidence"],
    ["Hazard Ordinal", metric(m.hazard_planning_ordinal, "", 0), "evidence"],
    ["Evidence-adjusted Priority", status.evidence_adjusted_planning_priority === "withheld" ? "WITHHELD" : metric(m.evidence_adjusted_planning_priority, "", 2), status.evidence_adjusted_planning_priority === "withheld" ? "withheld" : "evidence"]
  ].map(([label,value,kind]) => `
      <div class="metric-row ${kind === "withheld" ? "withheld" : ""}">
        <span class="label"><span class="dot ${kind === "withheld" ? "withheld" : "evidence"}"></span>${esc(label)}</span>
        <span class="value">${esc(value)}</span>
      </div>`).join("");

  const c = contributionsOf(h);
  const hazard = c.hazard?.weighted_points;
  const exposure = c.mapped_exposure?.weighted_points;
  const context = c.context_sensitivity_proxy?.weighted_points;

  $("whyText").textContent = `Priority ${fmt(h.planning_priority, 2)}/100 is composed from hazard ${fmt(hazard, 2)} points, mapped-exposure ${fmt(exposure, 2)} points, and context-sensitivity ${fmt(context, 2)} points.`;

  $("donutScore").textContent = fmt(h.planning_priority, 2);
  const total = (hazard || 0) + (exposure || 0) + (context || 0) || 1;
  const p1 = ((hazard || 0) / total) * 100;
  const p2 = p1 + ((exposure || 0) / total) * 100;
  $("priorityDonut").style.background = `conic-gradient(var(--accent) 0 ${p1}%, var(--thermal-mid) ${p1}% ${p2}%, var(--humidity) ${p2}% 100%)`;

  $("compositionLegend").innerHTML = [
    ["var(--accent)", "Hazard", hazard],
    ["var(--thermal-mid)", "Mapped Exposure", exposure],
    ["var(--humidity)", "Context Sensitivity", context]
  ].map(([color,label,value]) => `
    <div class="dl-row">
      <span class="dl-left"><span class="dl-swatch" style="background:${color}"></span>${label}</span>
      <span class="dl-right">${fmt(value,2)} pts</span>
    </div>`).join("");

  $("evidenceRows").innerHTML = [
    ["Historical Air Temperature", metric(m.historical_air_temperature_celsius, "°C", 2)],
    ["Historical Heat Index", metric(m.historical_heat_index_celsius, "°C", 1)],
    ["Apparent Temperature", metric(m.historical_apparent_temperature_celsius, "°C", 1)],
    ["Wet-Bulb Temperature", metric(m.historical_wet_bulb_temperature_celsius, "°C", 1)],
    ["Relative Humidity", metric(m.historical_relative_humidity_percent, "%", 1)],
    ["Mapped Exposure Proxy", metric(m.mapped_exposure_proxy, "", 2)]
  ].map(([label,value]) => `<div class="evidence-row"><span class="label">${esc(label)}</span><span class="value">${esc(value)}</span></div>`).join("");

  $("vulnStatus").textContent = String(status.verified_operational_vulnerability || "unknown").toUpperCase();
  $("capacityStatus").textContent = String(status.verified_adaptive_capacity || "unknown").toUpperCase();
  $("medicalStatus").textContent = String(status.medical_risk_probability || "withheld").toUpperCase();

  renderRecommendations(h);
}

function renderComparison() {
  const max = Math.max(...state.snapshot.hotspots.map((h) => Number(h.planning_priority) || 0), 1);

  $("comparisonBars").innerHTML = state.snapshot.hotspots.map((h,index) => `
    <div class="bar-row">
      <div class="bar-head"><span class="name">Hotspot ${h.hotspot_rank}</span><span class="val">${fmt(h.planning_priority,2)}</span></div>
      <div class="bar-track"><div class="bar-fill ${index === 0 ? "leader" : ""}" style="width:${((h.planning_priority || 0) / max) * 100}%"></div></div>
    </div>`).join("");

  $("topHotspots").innerHTML = state.snapshot.hotspots.map((h,index) => `
    <div class="top-row" data-rank="${h.hotspot_rank}">
      <span class="rank-badge ${index === 0 ? "first" : ""}">${index + 1}</span>
      <span class="top-name">Hotspot ${h.hotspot_rank}</span>
      <span class="top-val">${fmt(h.planning_priority,2)}</span>
    </div>`).join("");

  document.querySelectorAll(".top-row[data-rank]").forEach((row) => row.addEventListener("click", () => selectHotspot(Number(row.dataset.rank))));
}

function renderRecommendations(h) {
  const recs = (h.recommendations || []).slice(0,5);
  $("compactRecommendations").innerHTML = recs.slice(0,4).map((r) => {
    const tier = String(r.priority_tier || "").toLowerCase();
    return `<div class="rec-item">
      <span class="tag ${tier}">${esc(r.priority_tier || "CONTROLLED")} — ${esc(r.action_type || "ASSESS")}</span>
      <div class="title">${esc(r.title || "Controlled action")}</div>
      ${r.recommendation ? `<div class="desc">${esc(r.recommendation)}</div>` : ""}
    </div>`;
  }).join("");

  $("allRecommendations").innerHTML = recs.map((r) => `
    <article style="background:var(--bg-card);border:1px solid var(--border-hairline);border-radius:10px;padding:14px;">
      <div style="font-size:9.5px;color:var(--accent);font-weight:700;">${esc(r.priority_tier || "CONTROLLED")} — ${esc(r.action_type || "ASSESS")}</div>
      <div style="font-size:12px;font-weight:600;margin:8px 0 6px;">${esc(r.title || "Controlled action")}</div>
      <div style="font-size:10.5px;color:var(--text-muted);line-height:1.5;">${esc(r.recommendation || "")}</div>
      <div style="font-size:9px;color:var(--text-secondary);margin-top:10px;">${esc(r.status || "guarded")}</div>
    </article>`).join("");
}

function selectHotspot(rank) {
  state.selectedRank = rank;
  renderSelected();
  renderMap();
}

function openDrawer() {
  $("drawer").classList.add("open");
  $("scrim").classList.add("open");
  $("drawer").setAttribute("aria-hidden", "false");
  setTimeout(() => $("copilotInput").focus(), 100);
}

function closeDrawer() {
  $("drawer").classList.remove("open");
  $("scrim").classList.remove("open");
  $("drawer").setAttribute("aria-hidden", "true");
}

function addMessage(role, text) {
  const thread = $("thread");
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  msg.textContent = text;
  thread.appendChild(msg);
  thread.scrollTop = thread.scrollHeight;
}

async function askCopilot(query) {
  if (!query) return;
  openDrawer();
  addMessage("user", query);
  $("sendButton").disabled = true;
  $("sendButton").textContent = "Grounding…";

  try {
    const response = await fetch("/api/v1/copilot/ask", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ query, mode:"auto", hotspot_rank: state.selectedRank })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    addMessage("assistant", payload.answer || "No grounded answer was returned.");
  } catch (error) {
    addMessage("assistant", `Copilot unavailable: ${error.message}. Verified dashboard evidence remains available.`);
  } finally {
    $("sendButton").disabled = false;
    $("sendButton").textContent = "Ask";
  }
}

async function loadCopilotStatus() {
  try {
    const response = await fetch("/api/v1/copilot/status");
    const payload = await response.json();
    $("copilotStatus").textContent = payload.default_provider === "ollama" ? "Local Qwen Ready" : `${payload.default_provider || "Copilot"} Ready`;
    $("copilotModel").textContent = payload.model || "qwen3:1.7b";
  } catch {
    $("copilotStatus").textContent = "Copilot Status Unavailable";
  }
}

function jump(name) {
  const ids = { overview:"overviewSection", thermal:"thermalSection", hotspots:"hotspotsSection", evidence:"evidenceSection", actions:"actionsSection" };
  $(ids[name])?.scrollIntoView({behavior:"smooth", block:"start"});
}

async function init() {
  try {
    const response = await fetch("/api/v1/dashboard/overview");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);

    state.snapshot = payload;
    state.selectedRank = payload.planning_order?.[0] ?? payload.hotspots?.[0]?.hotspot_rank ?? null;

    const hash = payload.provenance?.day7_artifact_sha256;
    $("evidenceHash").textContent = hash ? `Evidence SHA ${hash.slice(0,12)}…` : "Evidence lineage available";

    renderKpis();
    renderComparison();
    renderSelected();
    renderMap();
  } catch (error) {
    $("thermalMap").classList.add("hidden");
    $("mapFallback").classList.remove("hidden");
    $("mapFallback").innerHTML = `<strong>Dashboard evidence could not be loaded.</strong><span>${esc(error.message)}</span>`;
  }
  loadCopilotStatus();
}

document.querySelectorAll(".nav-link[data-jump]").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  jump(button.dataset.jump);
}));

$("compareHotspotsButton")?.addEventListener("click", () => jump("hotspots"));
$("openCopilotTop")?.addEventListener("click", openDrawer);
$("openCopilotSidebar")?.addEventListener("click", openDrawer);
$("viewGroundedExplanation")?.addEventListener("click", () => askCopilot(`Why is hotspot ${state.selectedRank} high priority?`));
$("viewAllRecommendations")?.addEventListener("click", () => jump("actions"));
$("scrim")?.addEventListener("click", closeDrawer);
$("closeDrawer")?.addEventListener("click", closeDrawer);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDrawer(); });

document.querySelectorAll("[data-prompt]").forEach((button) => button.addEventListener("click", () => {
  const q = state.selectedRank ? button.dataset.prompt.replace(/hotspot \d+/i, `hotspot ${state.selectedRank}`) : button.dataset.prompt;
  askCopilot(q);
}));

$("copilotForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("copilotInput");
  const q = input.value.trim();
  if (!q) return;
  input.value = "";
  askCopilot(q);
});

init();
