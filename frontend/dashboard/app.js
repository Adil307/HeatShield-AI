const state = {
  snapshot: null,
  selectedRank: null,
};

const $ = (id) => document.getElementById(id);
const fmt = (value, digits = 1) =>
  typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function metricValue(value, suffix = "", digits = 1) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value.toFixed(digits)}${suffix}`
    : "—";
}

function statusText(value) {
  return value ? String(value).toUpperCase() : "UNKNOWN";
}

function tileIdOfFeature(feature) {
  const p = feature?.properties || {};
  for (const key of ["tile_id", "tileId", "id", "tile", "grid_id"]) {
    if (p[key] !== undefined && p[key] !== null && !Number.isNaN(Number(p[key]))) {
      return Number(p[key]);
    }
  }
  return null;
}

function featureTemperature(feature) {
  const p = feature?.properties || {};
  for (const key of [
    "average_temperature", "avg_temperature", "average", "avg",
    "temperature", "tcm", "mean_temperature", "mean"
  ]) {
    if (typeof p[key] === "number" && Number.isFinite(p[key])) return p[key];
  }
  for (const [key, value] of Object.entries(p)) {
    if (typeof value === "number" && /temp|average|mean|tcm/i.test(key)) return value;
  }
  return null;
}

function geometryRings(geometry) {
  if (!geometry) return [];
  if (geometry.type === "Polygon") return geometry.coordinates || [];
  if (geometry.type === "MultiPolygon") return (geometry.coordinates || []).flat();
  return [];
}

function allGeoPoints(features) {
  const points = [];
  for (const feature of features) {
    for (const ring of geometryRings(feature.geometry)) {
      for (const point of ring || []) {
        if (Array.isArray(point) && point.length >= 2 &&
            Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]))) {
          points.push([Number(point[0]), Number(point[1])]);
        }
      }
    }
  }
  return points;
}

function centroid(feature) {
  const pts = allGeoPoints([feature]);
  if (!pts.length) return null;
  let x = 0, y = 0;
  for (const [lon, lat] of pts) { x += lon; y += lat; }
  return [x / pts.length, y / pts.length];
}

function thermalColor(value, min, max) {
  if (!Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max) || max === min) {
    return "hsl(176 38% 35%)";
  }
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const hue = 208 - t * 198;
  const saturation = 70 + t * 5;
  const light = 38 + t * 13;
  return `hsl(${hue} ${saturation}% ${light}%)`;
}

function drawHeatmap() {
  const svg = $("heatmapSvg");
  const empty = $("mapEmpty");
  const geojson = state.snapshot?.heatmap_geojson;
  const features = geojson?.features || [];
  svg.innerHTML = "";

  if (!features.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  const points = allGeoPoints(features);
  if (!points.length) {
    empty.classList.remove("hidden");
    return;
  }

  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const width = 1000, height = 620, pad = 26;
  const project = ([lon, lat]) => [
    pad + ((lon - minX) / Math.max(maxX - minX, 1e-9)) * (width - pad * 2),
    height - pad - ((lat - minY) / Math.max(maxY - minY, 1e-9)) * (height - pad * 2),
  ];

  const temps = features.map(featureTemperature).filter(Number.isFinite);
  const tMin = temps.length ? Math.min(...temps) : 0;
  const tMax = temps.length ? Math.max(...temps) : 1;

  for (const feature of features) {
    const tileId = tileIdOfFeature(feature);
    const temp = featureTemperature(feature);
    for (const ring of geometryRings(feature.geometry)) {
      if (!ring?.length) continue;
      const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
      polygon.setAttribute("points", ring.map((p) => project(p).join(",")).join(" "));
      polygon.setAttribute("fill", thermalColor(temp, tMin, tMax));
      polygon.setAttribute("class", "heat-tile");
      polygon.addEventListener("mousemove", (event) => {
        const tip = $("mapTooltip");
        tip.textContent = `Tile ${tileId ?? "—"}${Number.isFinite(temp) ? ` • ${temp.toFixed(2)} °C` : ""}`;
        tip.style.left = `${event.offsetX + 12}px`;
        tip.style.top = `${event.offsetY + 12}px`;
        tip.classList.remove("hidden");
      });
      polygon.addEventListener("mouseleave", () => $("mapTooltip").classList.add("hidden"));
      svg.appendChild(polygon);
    }
  }

  for (const hotspot of state.snapshot.hotspots) {
    const feature = features.find((f) => tileIdOfFeature(f) === Number(hotspot.tile_id));
    const center = feature ? centroid(feature) : null;
    if (!center) continue;
    const [cx, cy] = project(center);

    const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
    group.addEventListener("click", () => selectHotspot(hotspot.hotspot_rank));

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", cx);
    circle.setAttribute("cy", cy);
    circle.setAttribute("r", hotspot.hotspot_rank === state.selectedRank ? "16" : "12");
    circle.setAttribute(
      "class",
      hotspot.hotspot_rank === state.selectedRank ? "hotspot-marker hotspot-marker-selected" : "hotspot-marker"
    );

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", cx);
    label.setAttribute("y", cy + 4);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute(
      "class",
      hotspot.hotspot_rank === state.selectedRank ? "hotspot-label hotspot-label-selected" : "hotspot-label"
    );
    label.textContent = hotspot.hotspot_rank;

    group.appendChild(circle);
    group.appendChild(label);
    svg.appendChild(group);
  }
}

function renderKpis() {
  const s = state.snapshot.summary;
  $("kpiHotspots").textContent = s.hotspot_count ?? "—";
  $("kpiPriority").textContent =
    typeof s.highest_priority_score === "number" ? s.highest_priority_score.toFixed(2) : "—";
  $("kpiPriorityRank").textContent =
    s.highest_priority_rank ? `Hotspot rank ${s.highest_priority_rank}` : "Verified planning order";
  $("kpiTemp").textContent =
    typeof s.max_historical_air_temperature_celsius === "number"
      ? `${s.max_historical_air_temperature_celsius.toFixed(2)} °C`
      : "—";
  $("kpiTiles").textContent = s.heatmap_feature_count ?? "0";
}

function renderRanking() {
  const list = $("rankingList");
  list.innerHTML = "";

  state.snapshot.hotspots.forEach((hotspot, index) => {
    const card = document.createElement("div");
    card.className = `rank-card${hotspot.hotspot_rank === state.selectedRank ? " active" : ""}`;
    card.innerHTML = `
      <div class="rank-head">
        <span class="rank-label">#${index + 1} PRIORITY</span>
        <span class="rank-score">${fmt(hotspot.planning_priority, 2)}</span>
      </div>
      <div class="rank-title">Hotspot ${hotspot.hotspot_rank} • Tile ${hotspot.tile_id ?? "—"}</div>
      <div class="rank-meta">
        <span>${metricValue(hotspot.metrics.historical_air_temperature_celsius, " °C", 2)} historical air</span>
        <span>${escapeHtml(hotspot.planning_priority_band || "planning priority")}</span>
      </div>
      <div class="rank-progress"><span style="width:${Math.max(0, Math.min(100, hotspot.planning_priority || 0))}%"></span></div>
    `;
    card.addEventListener("click", () => selectHotspot(hotspot.hotspot_rank));
    list.appendChild(card);
  });
}

function renderDetails() {
  const hotspot = state.snapshot.hotspots.find((h) => h.hotspot_rank === state.selectedRank);
  if (!hotspot) return;

  const m = hotspot.metrics;
  $("detailTitle").textContent = `Hotspot ${hotspot.hotspot_rank} • Tile ${hotspot.tile_id ?? "—"}`;
  $("detailBand").textContent = hotspot.planning_priority_band || "planning priority";
  $("priorityScore").textContent = fmt(hotspot.planning_priority, 2);

  const degrees = Math.max(0, Math.min(360, (hotspot.planning_priority || 0) * 3.6));
  $("scoreRing").style.background =
    `conic-gradient(var(--mint) ${degrees}deg, rgba(255,255,255,.055) ${degrees}deg)`;

  const contributions = Object.fromEntries(
    (hotspot.contributions || [])
      .filter((x) => x && x.component)
      .map((x) => [x.component, x])
  );

  const hazard = contributions.hazard?.weighted_points;
  const exposure = contributions.mapped_exposure?.weighted_points;
  const sensitivity = contributions.context_sensitivity_proxy?.weighted_points;

  $("priorityExplanation").textContent =
    `Hazard ${fmt(hazard, 2)} pts • Exposure ${fmt(exposure, 2)} pts • Context ${fmt(sensitivity, 2)} pts`;

  $("compactMetricGrid").innerHTML = [
    ["Heat index", metricValue(m.historical_heat_index_celsius, "°", 1)],
    ["Humidity", metricValue(m.historical_relative_humidity_percent, "%", 1)],
    ["Exposure", metricValue(m.mapped_exposure_proxy, "", 1)],
  ].map(([label, value]) =>
    `<div class="compact-metric"><span>${label}</span><strong>${value}</strong></div>`
  ).join("");

  const metrics = [
    ["Historical air temperature", metricValue(m.historical_air_temperature_celsius, " °C", 2)],
    ["Historical heat index", metricValue(m.historical_heat_index_celsius, " °C", 1)],
    ["Apparent temperature", metricValue(m.historical_apparent_temperature_celsius, " °C", 1)],
    ["Wet-bulb temperature", metricValue(m.historical_wet_bulb_temperature_celsius, " °C", 1)],
    ["Relative humidity", metricValue(m.historical_relative_humidity_percent, "%", 1)],
    ["Mapped exposure proxy", metricValue(m.mapped_exposure_proxy, "", 2)],
  ];

  $("metricGrid").innerHTML = metrics.map(([label, value]) =>
    `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`
  ).join("");

  $("vulnStatus").textContent = statusText(hotspot.evidence_status.verified_operational_vulnerability);
  $("capacityStatus").textContent = statusText(hotspot.evidence_status.verified_adaptive_capacity);
  $("medicalStatus").textContent = statusText(hotspot.evidence_status.medical_risk_probability);

  $("actionList").innerHTML = (hotspot.recommendations || []).slice(0, 5).map((action) => `
    <article class="action-card">
      <div class="action-top">
        <span class="action-tier">${escapeHtml(action.priority_tier || "CONTROLLED")}</span>
        <span class="action-status">${escapeHtml(action.status || "guarded")}</span>
      </div>
      <h3>${escapeHtml(action.title || "Controlled action")}</h3>
      <p>${escapeHtml(action.recommendation || "")}</p>
    </article>
  `).join("");
}

function selectHotspot(rank) {
  state.selectedRank = rank;
  renderRanking();
  renderDetails();
  drawHeatmap();
}

function openCopilot() {
  $("copilotDrawer").classList.add("open");
  $("copilotDrawer").setAttribute("aria-hidden", "false");
  $("copilotBackdrop").classList.remove("hidden");
  setTimeout(() => $("copilotInput").focus(), 120);
}

function closeCopilot() {
  $("copilotDrawer").classList.remove("open");
  $("copilotDrawer").setAttribute("aria-hidden", "true");
  $("copilotBackdrop").classList.add("hidden");
}

function addMessage(role, text) {
  const box = $("chatWindow");
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.innerHTML = `
    <div class="message-label">${role === "user" ? "YOU" : "HEATSHIELD"}</div>
    <p>${escapeHtml(text)}</p>`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

async function askCopilot(query) {
  if (!query) return;
  openCopilot();
  const button = $("sendButton");
  button.disabled = true;
  button.textContent = "Grounding…";
  addMessage("user", query);

  try {
    const response = await fetch("/api/v1/copilot/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        mode: "auto",
        hotspot_rank: state.selectedRank,
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    addMessage("assistant", payload.answer || "No grounded answer was returned.");
  } catch (error) {
    addMessage(
      "assistant",
      `Copilot unavailable: ${error.message}. Verified dashboard evidence remains available.`
    );
  } finally {
    button.disabled = false;
    button.textContent = "Ask Copilot";
  }
}

async function loadCopilotStatus() {
  try {
    const response = await fetch("/api/v1/copilot/status");
    const payload = await response.json();
    $("copilotStatus").textContent =
      payload.default_provider === "ollama"
        ? "Local Qwen ready"
        : `${payload.default_provider || "Copilot"} ready`;
    $("copilotModel").textContent =
      payload.model || (payload.default_provider === "ollama" ? "qwen3:1.7b" : "Grounded Copilot");
  } catch {
    $("copilotStatus").textContent = "Copilot status unavailable";
  }
}

function jumpToSection(name) {
  const map = {
    overview: "overviewSection",
    evidence: "evidenceSection",
    actions: "actionsSection",
  };
  const id = map[name];
  if (id) $(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function init() {
  try {
    const response = await fetch("/api/v1/dashboard/overview");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);

    state.snapshot = payload;
    state.selectedRank =
      payload.planning_order?.[0] ??
      payload.hotspots?.[0]?.hotspot_rank ??
      null;

    $("scopeText").textContent =
      payload.scenario.scope_warning ||
      payload.scenario.statement ||
      "Verified scenario replay";

    const hash = payload.provenance?.day7_artifact_sha256;
    const hashText = hash ? `SHA ${hash.slice(0, 12)}…` : "Evidence lineage available";
    $("provenanceHash").textContent = hashText;
    $("evidenceHash").textContent = hashText;

    renderKpis();
    renderRanking();
    renderDetails();
    drawHeatmap();
  } catch (error) {
    $("scopeText").textContent = `Dashboard evidence could not be loaded: ${error.message}`;
    $("mapEmpty").classList.remove("hidden");
  }

  loadCopilotStatus();
}

$("copilotForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("copilotInput");
  const query = input.value.trim();
  if (!query) return;
  input.value = "";
  askCopilot(query);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    const base = button.dataset.prompt;
    const query = state.selectedRank
      ? base.replace(/hotspot \d+/i, `hotspot ${state.selectedRank}`)
      : base;
    askCopilot(query);
  });
});

document.querySelectorAll("[data-section]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    jumpToSection(button.dataset.section);
  });
});

document.querySelectorAll("[data-section-jump]").forEach((button) => {
  button.addEventListener("click", () => jumpToSection(button.dataset.sectionJump));
});

$("openCopilotNav").addEventListener("click", openCopilot);
$("openCopilotTop").addEventListener("click", openCopilot);
$("closeCopilot").addEventListener("click", closeCopilot);
$("copilotBackdrop").addEventListener("click", closeCopilot);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeCopilot();
});

init();
