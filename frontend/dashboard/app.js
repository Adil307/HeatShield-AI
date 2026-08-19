const state = { snapshot:null, selectedRank:null, map:null, polygonLayer:null, heatLayer:null, markerLayer:null, satelliteLayer:null, streetLayer:null, activeBasemap:"satellite", activeView:"overview", liveAnalysis:null, liveRequest:null, liveEnrichment:null, liveApiReady:false, replayScenarioLabel:"Scenario Replay" };
const $ = (id) => document.getElementById(id);
const fmt = (v,d=1) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "—";
const metric = (v,s="",d=1) => typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(d)}${s}` : "—";
const esc = (v) => String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");

const VIEW_COPY = {
  overview:{
    eyebrow:"Urban Heat Decision Intelligence",
    title:"Heat Priority Dashboard",
    subtitle:"Verified thermal evidence, hotspot ranking, and clear next-step guidance",
    safety:"Planning priority supports decisions; it is not a medical-risk probability",
    scope:"Historical replay · Not live current heat"
  },
  thermal:{
    eyebrow:"Verified Thermal Evidence",
    title:"Thermal Map",
    subtitle:"Explore FortyGuard thermal evidence in geographic context",
    safety:"The smooth heat surface is derived from verified tiles; source geometry remains traceable",
    scope:"Historical thermal replay"
  },
  hotspots:{
    eyebrow:"Hotspot Review",
    title:"Hotspots",
    subtitle:"Compare the verified planning priorities and inspect one hotspot at a time",
    safety:"The hottest tile is not automatically the highest planning priority",
    scope:"Verified decision candidates"
  },
  evidence:{
    eyebrow:"Evidence Review",
    title:"What the Priority Is Based On",
    subtitle:"Review verified measurements, derived values, and evidence that still needs confirmation",
    safety:"Missing evidence stays missing; HeatShield does not silently treat it as low risk",
    scope:"Evidence guard active"
  },
  actions:{
    eyebrow:"Next Checks",
    title:"Recommended Next Checks",
    subtitle:"Evidence-aware verification and assessment actions from the controlled catalog",
    safety:"Recommendations do not promise medical outcomes or guaranteed cooling effects",
    scope:"Controlled action catalog"
  },
  live:{
    eyebrow:"Fresh FortyGuard Thermal Evidence",
    title:"Live Analysis",
    subtitle:"Submit the current map viewport as a fresh provider-backed TCM analysis",
    safety:"Fresh mode adds thermal-stress evidence, but no planning priority or medical-risk score is inferred until required context is verified",
    scope:"Fresh provider request · Controlled scope"
  },
  copilot:{
    eyebrow:"Evidence-Grounded Assistant",
    title:"HeatShield Assistant",
    subtitle:"Ask a plain-language question about the evidence already on screen",
    safety:"Answers are based on verified HeatShield evidence; missing evidence is kept explicit",
    scope:"Local assistant · Evidence grounded"
  }
};

function tileIdOf(feature){const p=feature?.properties||{};for(const key of ["tile_id","tileId","id","tile","grid_id"]){if(p[key]!==undefined&&p[key]!==null&&!Number.isNaN(Number(p[key])))return Number(p[key]);}return null;}
function featureTemperature(feature){const p=feature?.properties||{};for(const key of ["average_temperature","avg_temperature","average","avg","temperature","tcm","mean_temperature","mean"]){if(typeof p[key]==="number"&&Number.isFinite(p[key]))return p[key];}for(const [key,value] of Object.entries(p)){if(typeof value==="number"&&/temp|average|mean|tcm/i.test(key))return value;}return null;}
function selectedHotspot(){return state.snapshot?.hotspots?.find(h=>h.hotspot_rank===state.selectedRank)||null;}
function featureCenter(feature){const layer=L.geoJSON(feature);const bounds=layer.getBounds();return bounds.isValid()?bounds.getCenter():null;}

function syncScenarioBar(){
  const label=$("scenarioLabel");
  if(!label)return;
  label.textContent=state.activeView==="live"?"Fresh FortyGuard Thermal Analysis":state.replayScenarioLabel;
}

function activateView(view,{updateHash=true}={}){
  if(!VIEW_COPY[view]) view="overview";
  state.activeView=view;
  const content=document.querySelector('.content');
  content.dataset.view=view;
  document.querySelectorAll('.nav-link[data-view]').forEach(btn=>btn.classList.toggle('active',btn.dataset.view===view));
  const copy=VIEW_COPY[view];
  $("viewEyebrow").textContent=copy.eyebrow;$("viewTitle").textContent=copy.title;$("viewSubtitle").textContent=copy.subtitle;$("viewSafety").textContent=copy.safety;$("viewScopeBadge").textContent=copy.scope;
  syncScenarioBar();
  if(updateHash&&location.hash!==`#${view}`) history.replaceState(null,"",`#${view}`);
  window.scrollTo({top:0,behavior:"smooth"});
  if(view==="thermal"||view==="live") setTimeout(()=>{renderMap();updateLiveViewportInfo();},30);
  if(view==="copilot") setTimeout(()=>$("copilotInput")?.focus(),80);
}


function syncBasemapButtons(){
  const satellite=$("satelliteBasemapButton"),streets=$("streetBasemapButton"),status=$("basemapStatus");
  satellite?.classList.toggle("active",state.activeBasemap==="satellite");
  streets?.classList.toggle("active",state.activeBasemap==="streets");
  if(status) status.textContent=state.activeBasemap==="satellite"?"Satellite view":"Simple map view";
}

function setBasemap(mode){
  if(!state.map)return;
  const requested=mode==="streets"?"streets":"satellite";
  const target=requested==="satellite"?state.satelliteLayer:state.streetLayer;
  const other=requested==="satellite"?state.streetLayer:state.satelliteLayer;
  if(other&&state.map.hasLayer(other))state.map.removeLayer(other);
  if(target&&!state.map.hasLayer(target))target.addTo(state.map);
  state.activeBasemap=requested;
  syncBasemapButtons();
}

function ensureBasemaps(){
  if(!state.map||state.satelliteLayer||state.streetLayer)return;

  state.satelliteLayer=L.tileLayer(
    "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom:19,
      attribution:"Tiles &copy; Esri"
    }
  );

  state.streetLayer=L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      maxZoom:19,
      attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }
  );

  let satelliteErrors=0;
  state.satelliteLayer.on("tileerror",()=>{
    satelliteErrors+=1;
    if(satelliteErrors>=4&&state.activeBasemap==="satellite"){
      setBasemap("streets");
      const status=$("basemapStatus");
      if(status)status.textContent="Satellite unavailable · Simple map active";
    }
  });

  setBasemap("satellite");
}

function renderMap(){
  const liveMode=state.activeView==="live"&&state.liveAnalysis;
  const geo=liveMode?state.liveAnalysis?.heatmap_geojson:state.snapshot?.heatmap_geojson;
  const fallback=$("mapFallback");
  if(!geo?.features?.length||typeof L==="undefined"){$("thermalMap").classList.add("hidden");fallback.classList.remove("hidden");return;}
  $("thermalMap").classList.remove("hidden");fallback.classList.add("hidden");
  if(!state.map){
    state.map=L.map("thermalMap",{zoomControl:true,attributionControl:true,preferCanvas:true});
    ensureBasemaps();
    state.map.on("moveend",updateLiveViewportInfo);
  }else{ensureBasemaps();}
  if(state.polygonLayer)state.map.removeLayer(state.polygonLayer);if(state.heatLayer)state.map.removeLayer(state.heatLayer);if(state.markerLayer)state.map.removeLayer(state.markerLayer);
  const vals=geo.features.map(featureTemperature).filter(Number.isFinite),min=vals.length?Math.min(...vals):0,max=vals.length?Math.max(...vals):1,span=Math.max(max-min,1e-9);
  const sourceLabel=liveMode?"Fresh FortyGuard air temperature":"Historical air temperature";
  state.polygonLayer=L.geoJSON(geo,{style:()=>({color:"#5C6C82",weight:.35,fillColor:"#6E63F0",fillOpacity:.035}),onEachFeature:(f,layer)=>{const tile=tileIdOf(f),temp=featureTemperature(f);layer.bindTooltip(`<strong>Tile ${tile??"—"}</strong><br>${Number.isFinite(temp)?`${temp.toFixed(2)} °C ${sourceLabel.toLowerCase()}`:"Verified FortyGuard thermal evidence"}`,{sticky:true,direction:"top"});}}).addTo(state.map);
  if(typeof L.heatLayer==="function"){const points=[];for(const f of geo.features){const c=featureCenter(f),t=featureTemperature(f);if(!c||!Number.isFinite(t))continue;points.push([c.lat,c.lng,Math.max(.05,Math.min(1,(t-min)/span))]);}state.heatLayer=L.heatLayer(points,{radius:48,blur:34,maxZoom:17,minOpacity:.22,gradient:{0:"#2b67b1",.25:"#2fa6ca",.45:"#55c778",.65:"#d8ca48",.82:"#ef8b3c",1:"#e8543a"}}).addTo(state.map);}
  state.markerLayer=L.layerGroup().addTo(state.map);
  if(liveMode){
    for(const h of state.liveAnalysis.hottest_tiles||[]){const f=geo.features.find(x=>tileIdOf(x)===Number(h.tile_id));if(!f)continue;const c=featureCenter(f);if(!c)continue;const pos=Number(h.hotspot_rank)||1;const icon=L.divIcon({className:`heatshield-marker rank-${pos}`,html:`<div>${pos}</div>`,iconSize:pos===1?[34,34]:[30,30],iconAnchor:pos===1?[17,17]:[15,15]});const marker=L.marker(c,{icon}).addTo(state.markerLayer);marker.bindTooltip(`Hottest tile #${pos} • ${metric(h.temperature_celsius,"°C",2)}`,{direction:"top"});}
  }else{
    for(const h of state.snapshot.hotspots){const f=geo.features.find(x=>tileIdOf(x)===Number(h.tile_id));if(!f)continue;const c=featureCenter(f);if(!c)continue;const pos=state.snapshot.planning_order.indexOf(h.hotspot_rank)+1;const icon=L.divIcon({className:`heatshield-marker rank-${pos}`,html:`<div>${h.hotspot_rank}</div>`,iconSize:pos===1?[34,34]:[30,30],iconAnchor:pos===1?[17,17]:[15,15]});const marker=L.marker(c,{icon}).addTo(state.markerLayer);marker.bindTooltip(`Hotspot ${h.hotspot_rank} • Priority ${fmt(h.planning_priority,2)}`,{direction:"top"});marker.on("click",()=>selectHotspot(h.hotspot_rank));}
  }
  const bounds=state.polygonLayer.getBounds();if(bounds.isValid())state.map.fitBounds(bounds,{padding:[24,24],maxZoom:15});
  if($("mapLayerLabelText"))$("mapLayerLabelText").textContent=liveMode?"Fresh FortyGuard Temperature":"Historical Air Temperature";
  if($("mapLegendTitle"))$("mapLegendTitle").textContent=liveMode?"Fresh FortyGuard Temperature":"Historical Air Temperature";
  if($("mapEvidenceNote"))$("mapEvidenceNote").textContent=liveMode?"Fresh FortyGuard thermal job · relative hottest tiles only":"FortyGuard thermal evidence · Satellite view: Esri World Imagery";
  setTimeout(()=>{state.map.invalidateSize();updateLiveViewportInfo();},80);
}

function renderKpis(){const s=state.snapshot.summary;const heat=state.snapshot.hotspots.map(h=>h.metrics.historical_heat_index_celsius).filter(Number.isFinite);const humid=state.snapshot.hotspots.map(h=>h.metrics.historical_relative_humidity_percent).filter(Number.isFinite);$("kpiTemp").textContent=metric(s.max_historical_air_temperature_celsius,"°C",2);$("kpiHeatIndex").textContent=heat.length?`${Math.max(...heat).toFixed(1)}°C`:"—";$("kpiHotspots").textContent=s.hotspot_count??"—";$("kpiPriority").textContent=fmt(s.highest_priority_score,2);$("kpiPriorityRank").textContent=s.highest_priority_rank?`Hotspot ${s.highest_priority_rank}`:"Verified planning order";$("kpiHumidity").textContent=humid.length?`${(humid.reduce((a,b)=>a+b,0)/humid.length).toFixed(1)}%`:"—";$("kpiTiles").textContent=s.heatmap_feature_count??"—";}
function contributionsOf(h){return Object.fromEntries((h.contributions||[]).filter(x=>x?.component).map(x=>[x.component,x]));}


function humanizeToken(value){
  const text=String(value??"").trim().replaceAll("_"," ").replaceAll("-"," ");
  if(!text)return "";
  return text.toLowerCase().replace(/\b\w/g,ch=>ch.toUpperCase());
}

function humanStatus(value,fallback){
  const raw=String(value??fallback??"").trim().toLowerCase();
  if(raw==="unknown")return "Unknown";
  if(raw==="withheld")return "Withheld";
  if(raw==="verified")return "Verified";
  if(raw==="available")return "Available";
  if(raw==="not_applicable")return "Not applicable";
  return humanizeToken(raw);
}

function recommendationKind(recommendation){
  const action=String(recommendation?.action_type??"").toLowerCase();
  const title=String(recommendation?.title??"").toLowerCase();

  if(action.includes("verification")||action.includes("verify")||title.startsWith("verify")){
    return {label:"Verify first",className:"verify"};
  }
  if(action.includes("assessment")||action.includes("assess")||title.startsWith("assess")){
    return {label:"Assess next",className:"assess"};
  }
  if(action.includes("review")||title.includes("review")){
    return {label:"Review if applicable",className:"review"};
  }
  return {label:"Recommended check",className:""};
}

function renderSelected(){const h=selectedHotspot();if(!h)return;const m=h.metrics,status=h.evidence_status,pos=state.snapshot.planning_order.indexOf(h.hotspot_rank)+1;$("selectedHotspotTitle").textContent=`Hotspot ${h.hotspot_rank}`;$("priorityBand").textContent=humanizeToken(h.planning_priority_band||"planning priority");$("priorityBand").classList.add("human-status");$("selectedScore").textContent=fmt(h.planning_priority,0);$("selectedTile").textContent=`Tile ${h.tile_id??"—"}`;$("selectedRank").textContent=`Priority Rank #${pos}`;const gauge=$("selectedScore").closest(".gauge"),circle=gauge?.querySelector("circle:nth-of-type(2)");if(circle){const circumference=251.3;circle.setAttribute("stroke-dasharray",circumference);circle.setAttribute("stroke-dashoffset",circumference*(1-Math.max(0,Math.min(100,h.planning_priority||0))/100));}
  $("selectedMetrics").innerHTML=[["Historical Air Temp",metric(m.historical_air_temperature_celsius,"°C",2),"evidence"],["Historical Heat Index",metric(m.historical_heat_index_celsius,"°C",1),"evidence"],["Relative Humidity",metric(m.historical_relative_humidity_percent,"%",1),"evidence"],["Mapped Exposure Proxy",metric(m.mapped_exposure_proxy,"",2),"evidence"],["Hazard Ordinal",metric(m.hazard_planning_ordinal,"",0),"evidence"],["Evidence-adjusted Priority",status.evidence_adjusted_planning_priority==="withheld"?"Withheld":metric(m.evidence_adjusted_planning_priority,"",2),status.evidence_adjusted_planning_priority==="withheld"?"withheld":"evidence"]].map(([label,value,kind])=>`<div class="metric-row ${kind==="withheld"?"withheld":""}"><span class="label"><span class="dot ${kind==="withheld"?"withheld":"evidence"}"></span>${esc(label)}</span><span class="value">${esc(value)}</span></div>`).join("");
  const c=contributionsOf(h),hazard=c.hazard?.weighted_points,exposure=c.mapped_exposure?.weighted_points,context=c.context_sensitivity_proxy?.weighted_points;$("whyText").textContent=`This hotspot scores ${fmt(h.planning_priority,2)}/100. The score includes ${fmt(hazard,2)} points from thermal hazard, ${fmt(exposure,2)} from mapped exposure, and ${fmt(context,2)} from context sensitivity.`;$("donutScore").textContent=fmt(h.planning_priority,2);const total=(hazard||0)+(exposure||0)+(context||0)||1,p1=((hazard||0)/total)*100,p2=p1+((exposure||0)/total)*100;$("priorityDonut").style.background=`conic-gradient(var(--accent) 0 ${p1}%, var(--thermal-mid) ${p1}% ${p2}%, var(--humidity) ${p2}% 100%)`;$("compositionLegend").innerHTML=[["var(--accent)","Hazard",hazard],["var(--thermal-mid)","Mapped Exposure",exposure],["var(--humidity)","Context Sensitivity",context]].map(([color,label,value])=>`<div class="dl-row"><span class="dl-left"><span class="dl-swatch" style="background:${color}"></span>${label}</span><span class="dl-right">${fmt(value,2)} pts</span></div>`).join("");
  $("evidenceRows").innerHTML=[["Historical Air Temperature",metric(m.historical_air_temperature_celsius,"°C",2)],["Historical Heat Index",metric(m.historical_heat_index_celsius,"°C",1)],["Apparent Temperature",metric(m.historical_apparent_temperature_celsius,"°C",1)],["Wet-Bulb Temperature",metric(m.historical_wet_bulb_temperature_celsius,"°C",1)],["Relative Humidity",metric(m.historical_relative_humidity_percent,"%",1)],["Mapped Exposure Proxy",metric(m.mapped_exposure_proxy,"",2)]].map(([label,value])=>`<div class="evidence-row"><span class="label">${esc(label)}</span><span class="value">${esc(value)}</span></div>`).join("");$("vulnStatus").textContent=humanStatus(status.verified_operational_vulnerability,"unknown");$("capacityStatus").textContent=humanStatus(status.verified_adaptive_capacity,"unknown");$("medicalStatus").textContent=humanStatus(status.medical_risk_probability,"withheld");renderRecommendations(h);renderCopilotContext(h);}

function renderComparison(){const max=Math.max(...state.snapshot.hotspots.map(h=>Number(h.planning_priority)||0),1);$("comparisonBars").innerHTML=state.snapshot.hotspots.map((h,index)=>`<div class="bar-row"><div class="bar-head"><span class="name">Hotspot ${h.hotspot_rank}</span><span class="val">${fmt(h.planning_priority,2)}</span></div><div class="bar-track"><div class="bar-fill ${index===0?"leader":""}" style="width:${((h.planning_priority||0)/max)*100}%"></div></div></div>`).join("");$("topHotspots").innerHTML=state.snapshot.hotspots.map((h,index)=>`<div class="top-row" data-rank="${h.hotspot_rank}"><span class="rank-badge ${index===0?"first":""}">${index+1}</span><span class="top-name">Hotspot ${h.hotspot_rank}</span><span class="top-val">${fmt(h.planning_priority,2)}</span></div>`).join("");document.querySelectorAll(".top-row[data-rank]").forEach(row=>row.addEventListener("click",()=>selectHotspot(Number(row.dataset.rank))));}
function renderRecommendations(h){
  const recs=(h.recommendations||[]).slice(0,5);

  $("compactRecommendations").innerHTML=recs.slice(0,4).map(r=>{
    const kind=recommendationKind(r);
    return `<div class="rec-item">
      <span class="recommendation-kind ${kind.className}">${esc(kind.label)}</span>
      <div class="title">${esc(r.title||"Recommended check")}</div>
      ${r.recommendation?`<div class="desc">${esc(r.recommendation)}</div>`:""}
    </div>`;
  }).join("");

  $("allRecommendations").innerHTML=recs.map(r=>{
    const kind=recommendationKind(r);
    const statusText=humanStatus(r.status,"");
    return `<article style="background:var(--bg-card);border:1px solid var(--border-hairline);border-radius:10px;padding:14px;">
      <span class="recommendation-kind ${kind.className}">${esc(kind.label)}</span>
      <div style="font-size:12px;font-weight:600;margin:8px 0 6px;">${esc(r.title||"Recommended check")}</div>
      <div style="font-size:10.5px;color:var(--text-muted);line-height:1.5;">${esc(r.recommendation||"")}</div>
      ${statusText?`<div style="font-size:9.5px;color:var(--text-secondary);margin-top:10px;">${esc(statusText)}</div>`:""}
    </article>`;
  }).join("");
}
function renderCopilotContext(h){if(!h||!$("copilotContext"))return;const s=h.evidence_status;$("copilotContext").innerHTML=[["Selected hotspot",`Hotspot ${h.hotspot_rank}`],["Planning priority",`${fmt(h.planning_priority,2)}/100`],["Tile",String(h.tile_id??"—")],["Operational vulnerability",humanStatus(s.verified_operational_vulnerability,"unknown")],["Adaptive capacity",humanStatus(s.verified_adaptive_capacity,"unknown")],["Medical risk probability",humanStatus(s.medical_risk_probability,"withheld")]].map(([a,b])=>`<div class="context-line"><span>${esc(a)}</span><strong>${esc(b)}</strong></div>`).join("");}

function setDefaultLiveDateTime(){
  const now=new Date();
  const date=now.toISOString().slice(0,10);
  const hour=now.toISOString().slice(11,13)+":00";
  if($("liveDate")&&!$("liveDate").value)$("liveDate").value=date;
  if($("liveTime")&&!$("liveTime").value)$("liveTime").value=hour;
}

function currentViewportFeatureCollection(){
  if(!state.map)return null;
  const b=state.map.getBounds();
  if(!b?.isValid?.())return null;
  const west=b.getWest(),east=b.getEast(),south=b.getSouth(),north=b.getNorth();
  return {type:"FeatureCollection",features:[{type:"Feature",properties:{source:"heatshield_day11_map_viewport"},geometry:{type:"Polygon",coordinates:[[[west,south],[east,south],[east,north],[west,north],[west,south]]]}}]};
}

function approximateViewportSqMiles(){
  if(!state.map)return null;
  const b=state.map.getBounds();if(!b?.isValid?.())return null;
  const centerLat=(b.getNorth()+b.getSouth())/2;
  const latMiles=Math.abs(b.getNorth()-b.getSouth())*69.0;
  const lonMiles=Math.abs(b.getEast()-b.getWest())*69.172*Math.cos(centerLat*Math.PI/180);
  return latMiles*lonMiles;
}

function updateLiveViewportInfo(){
  const el=$("liveViewportInfo");if(!el||!state.map)return;
  const area=approximateViewportSqMiles();
  if(!Number.isFinite(area)){el.textContent="Current map viewport will be used.";return;}
  el.textContent=`Current map viewport ≈ ${area.toFixed(2)} mi². Demo-safe limit: 10 mi².`;
}

function formatApiError(payload,status){
  const detail=payload?.detail;
  if(typeof detail==="string")return detail;
  if(detail&&typeof detail==="object")return detail.message||detail.provider_response?.message||`HTTP ${status}`;
  return payload?.message||`HTTP ${status}`;
}

async function loadLiveAnalysisStatus(){
  const el=$("liveApiStatus");
  try{
    const response=await fetch("/api/v1/dashboard/live-analysis/status"),payload=await response.json();
    state.liveApiReady=Boolean(payload.api_key_configured);
    if(el)el.textContent=state.liveApiReady?`FortyGuard key ready · ${payload.cache_entries??0} cached live request(s)`:`FortyGuard API key is not configured in backend/.env`;
  }catch(error){state.liveApiReady=false;if(el)el.textContent=`Live analysis status unavailable: ${error.message}`;}
}

function renderLiveResult(payload){
  const summary=payload?.summary||{},prov=payload?.provenance||{};
  $("liveResult")?.classList.add("visible");
  if($("liveMaxTemp"))$("liveMaxTemp").textContent=metric(summary.maximum_temperature_celsius,"°C",2);
  if($("liveMeanTemp"))$("liveMeanTemp").textContent=metric(summary.mean_temperature_celsius,"°C",2);
  if($("liveTileCount"))$("liveTileCount").textContent=String(summary.tile_count??"—");
  if($("liveCacheState"))$("liveCacheState").textContent=prov.cache_hit?"Cache reused":"Fresh job";
  if($("liveHottestTiles"))$("liveHottestTiles").innerHTML=(payload.hottest_tiles||[]).map(h=>`<div class="live-hot-row"><span>#${esc(h.hotspot_rank)} · Tile ${esc(h.tile_id)}</span><strong>${esc(metric(h.temperature_celsius,"°C",2))}</strong></div>`).join("");
  if($("liveProvenance"))$("liveProvenance").textContent=`Activity ID: ${prov.activity_id||"—"} · Request ${String(prov.request_hash||"").slice(0,12)}… · Evidence ${String(prov.source_sha256||"").slice(0,12)}…`;
}

function renderLiveEnrichment(payload){
  const observed=payload?.environmental_observed||{},derived=payload?.environmental_derived||{},readiness=payload?.decision_readiness||{},prov=payload?.provenance||{};
  $("liveDecisionResult")?.classList.add("visible");
  if($("liveHeatIndex"))$("liveHeatIndex").textContent=metric(observed.heat_index_celsius,"°C",1);
  if($("liveApparent"))$("liveApparent").textContent=metric(observed.apparent_temperature_celsius,"°C",1);
  if($("liveWetBulb"))$("liveWetBulb").textContent=metric(observed.wet_bulb_temperature_celsius,"°C",1);
  if($("liveHumidity"))$("liveHumidity").textContent=metric(observed.relative_humidity_percent,"%",1);
  if($("liveHazardOrdinal"))$("liveHazardOrdinal").textContent=derived.hazard_planning_ordinal==null?"WITHHELD":`${fmt(derived.hazard_planning_ordinal,0)}/100`;
  if($("liveHazardBand"))$("liveHazardBand").textContent=derived.heat_index_band?humanizeToken(derived.heat_index_band):"Observed heat index unavailable";
  if($("livePriorityReadiness"))$("livePriorityReadiness").textContent=readiness.planning_priority==="withheld_missing_required_context"?"WITHHELD · context required":humanizeToken(readiness.planning_priority||"withheld");
  if($("liveNextChecks"))$("liveNextChecks").innerHTML=(payload.next_checks||[]).map(item=>`<div class="live-check-row"><span class="live-check-tag">NEXT CHECK</span><div><strong>${esc(item.label)}</strong><small>${esc(item.reason)}</small></div></div>`).join("");
  if($("liveDecisionProvenance"))$("liveDecisionProvenance").textContent=`Thermal activity ${prov.thermal_activity_id||"—"} · Environmental activity ${prov.environmental_activity_id||"—"} · ${prov.environmental_cache_hit?"environment cache reused":"one environmental provider job"}`;
}

async function runLiveEnrichment(){
  const status=$("liveDecisionStatus"),button=$("liveEnrichButton");
  if(!state.liveRequest||!state.liveAnalysis){if(status){status.className="live-run-status error";status.textContent="Run the fresh thermal analysis first.";}return;}
  if(button){button.disabled=true;button.textContent="Enriching hottest tile…";}
  if(status){status.className="live-run-status";status.textContent="Reusing the verified thermal completion and requesting environmental parameters for the hottest tile…";}
  try{
    const response=await fetch("/api/v1/dashboard/live-analysis/top-hotspot-enrichment",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(state.liveRequest)});
    const payload=await response.json();
    if(!response.ok)throw new Error(formatApiError(payload,response.status));
    state.liveEnrichment=payload;
    renderLiveEnrichment(payload);
    if(status){status.className="live-run-status success";status.textContent=payload.provenance?.environmental_cache_hit?"Verified environmental completion reused; no new provider job was created.":"Hottest tile enriched with verified FortyGuard thermal-stress evidence.";}
  }catch(error){if(status){status.className="live-run-status error";status.textContent=`Environmental enrichment failed: ${error.message}`;}}
  finally{if(button){button.disabled=false;button.textContent="Enrich Hottest Tile";}}
}

async function runLiveAnalysis(){
  const status=$("liveRunStatus"),button=$("liveRunButton");
  const polygon=currentViewportFeatureCollection();
  if(!polygon){if(status){status.className="live-run-status error";status.textContent="Map viewport is not ready yet.";}return;}
  const area=approximateViewportSqMiles();
  if(Number.isFinite(area)&&area>10.15){if(status){status.className="live-run-status error";status.textContent=`Viewport is about ${area.toFixed(2)} mi². Zoom in below 10 mi² before submitting.`;}return;}
  const request={polygon_aoi:polygon,date_time:{start_date:$("liveDate").value,filter_type:1,start_time:$("liveTime").value},granularity:Number($("liveGranularity").value),analytic_type:"tcm"};
  if(button){button.disabled=true;button.textContent="Running FortyGuard…";}
  if(status){status.className="live-run-status";status.textContent="Submitting one controlled provider job and polling its activity ID…";}
  try{
    const response=await fetch("/api/v1/dashboard/live-analysis",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(request)});
    const payload=await response.json();
    if(!response.ok)throw new Error(formatApiError(payload,response.status));
    state.liveAnalysis=payload;
    state.liveRequest=request;
    state.liveEnrichment=null;
    $("liveDecisionResult")?.classList.remove("visible");
    if($("liveEnrichButton"))$("liveEnrichButton").disabled=false;
    renderLiveResult(payload);
    renderMap();
    if(status){status.className="live-run-status success";status.textContent=payload.provenance?.cache_hit?"Verified cached completion reused; no new provider job was created.":"Fresh FortyGuard job completed and verified thermal tiles are on the map.";}
  }catch(error){if(status){status.className="live-run-status error";status.textContent=`Live analysis failed: ${error.message}`;}}
  finally{if(button){button.disabled=false;button.textContent="Run FortyGuard Analysis";}}
}

function resetLiveAnalysis(){
  state.liveAnalysis=null;
  state.liveRequest=null;
  state.liveEnrichment=null;
  $("liveResult")?.classList.remove("visible");
  $("liveDecisionResult")?.classList.remove("visible");
  if($("liveEnrichButton"))$("liveEnrichButton").disabled=true;
  if($("liveRunStatus")){ $("liveRunStatus").className="live-run-status";$("liveRunStatus").textContent="Historical replay restored."; }
  activateView("thermal");
}

function selectHotspot(rank){state.selectedRank=rank;renderSelected();if(state.activeView==="thermal")renderMap();}
function addMessage(role,text){const thread=$("thread"),msg=document.createElement("div");msg.className=`msg ${role}`;msg.textContent=text;thread.appendChild(msg);thread.scrollTop=thread.scrollHeight;}
async function askCopilot(query){if(!query)return;activateView("copilot");addMessage("user",query);$("sendButton").disabled=true;$("sendButton").textContent="Checking evidence…";try{const response=await fetch("/api/v1/copilot/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,mode:"auto",hotspot_rank:state.selectedRank})});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||`HTTP ${response.status}`);addMessage("assistant",payload.answer||"No grounded answer was returned.");}catch(error){addMessage("assistant",`The assistant is unavailable right now: ${error.message}. The verified dashboard evidence is still available.`);}finally{$("sendButton").disabled=false;$("sendButton").textContent="Send";}}
async function loadCopilotStatus(){try{const response=await fetch("/api/v1/copilot/status"),payload=await response.json();$("copilotStatus").textContent=payload.status==="ready"?"Local assistant ready":"Assistant available";$("copilotModel").textContent=payload.model||payload.configured_model||"Configured model";}catch{$("copilotStatus").textContent="Assistant status unavailable";$("copilotModel").textContent="—";}}
async function init(){try{const response=await fetch("/api/v1/dashboard/overview"),payload=await response.json();if(!response.ok)throw new Error(payload.detail||`HTTP ${response.status}`);state.snapshot=payload;
    state.selectedRank=payload.planning_order?.[0]??payload.hotspots?.[0]?.hotspot_rank??null;
    const scenarioRaw=payload.scenario_mode??payload.summary?.scenario_mode??payload.mode??"scenario_replay";
    const scenarioText=String(scenarioRaw).replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
    state.replayScenarioLabel=scenarioText;
    if($("scenarioLabel")) $("scenarioLabel").textContent=scenarioText;const hash=payload.provenance?.day7_artifact_sha256;$("evidenceHash").textContent=hash?`Evidence SHA ${hash.slice(0,12)}…`:"Evidence lineage available";renderKpis();renderComparison();renderSelected();const initial=(location.hash||"#overview").slice(1);activateView(VIEW_COPY[initial]?initial:"overview",{updateHash:false});}catch(error){$("mapFallback").classList.remove("hidden");$("mapFallback").innerHTML=`<strong>Dashboard evidence could not be loaded.</strong><span>${esc(error.message)}</span>`;}loadCopilotStatus();setDefaultLiveDateTime();loadLiveAnalysisStatus();}

document.querySelectorAll(".nav-link[data-view]").forEach(button=>button.addEventListener("click",()=>activateView(button.dataset.view)));
$("compareHotspotsButton")?.addEventListener("click",()=>activateView("hotspots"));
$("openLiveAnalysisTop")?.addEventListener("click",()=>activateView("live"));
$("historicalReplayButton")?.addEventListener("click",()=>activateView("overview"));
$("openCopilotTop")?.addEventListener("click",()=>activateView("copilot"));
$("viewGroundedExplanation")?.addEventListener("click",()=>askCopilot(`Why is hotspot ${state.selectedRank} high priority?`));
$("viewAllRecommendations")?.addEventListener("click",()=>activateView("actions"));
function queryForIntent(intent){
  const rank=state.selectedRank;
  if(intent==="why") return rank?`Why does hotspot ${rank} rank this high?`:"Why does the selected hotspot rank this high?";
  if(intent==="compare") return "Compare the verified hotspots and explain the planning order.";
  if(intent==="actions") return rank?`What should we verify or assess next for hotspot ${rank}?`:"What should we verify or assess next?";
  if(intent==="missing") return rank?`What evidence is still missing for hotspot ${rank}?`:"What evidence is still missing?";
  return "Explain the selected evidence.";
}
document.querySelectorAll("[data-intent]").forEach(button=>button.addEventListener("click",()=>askCopilot(queryForIntent(button.dataset.intent))));
$("copilotForm")?.addEventListener("submit",event=>{event.preventDefault();const input=$("copilotInput"),q=input.value.trim();if(!q)return;input.value="";askCopilot(q);});
$("satelliteBasemapButton")?.addEventListener("click",()=>setBasemap("satellite"));
$("streetBasemapButton")?.addEventListener("click",()=>setBasemap("streets"));
$("liveAnalysisForm")?.addEventListener("submit",event=>{event.preventDefault();runLiveAnalysis();});
$("liveEnrichButton")?.addEventListener("click",runLiveEnrichment);
$("liveResetButton")?.addEventListener("click",resetLiveAnalysis);
window.addEventListener("hashchange",()=>{const view=location.hash.slice(1);if(VIEW_COPY[view])activateView(view,{updateHash:false});});
init();
