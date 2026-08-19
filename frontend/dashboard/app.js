const state = { snapshot:null, selectedRank:null, map:null, polygonLayer:null, heatLayer:null, markerLayer:null, satelliteLayer:null, streetLayer:null, activeBasemap:"satellite", activeView:"overview" };
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

function activateView(view,{updateHash=true}={}){
  if(!VIEW_COPY[view]) view="overview";
  state.activeView=view;
  const content=document.querySelector('.content');
  content.dataset.view=view;
  document.querySelectorAll('.nav-link[data-view]').forEach(btn=>btn.classList.toggle('active',btn.dataset.view===view));
  const copy=VIEW_COPY[view];
  $("viewEyebrow").textContent=copy.eyebrow;$("viewTitle").textContent=copy.title;$("viewSubtitle").textContent=copy.subtitle;$("viewSafety").textContent=copy.safety;$("viewScopeBadge").textContent=copy.scope;
  if(updateHash&&location.hash!==`#${view}`) history.replaceState(null,"",`#${view}`);
  window.scrollTo({top:0,behavior:"smooth"});
  if(view==="thermal") setTimeout(renderMap,30);
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
  const geo=state.snapshot?.heatmap_geojson, fallback=$("mapFallback");
  if(!geo?.features?.length||typeof L==="undefined"){$("thermalMap").classList.add("hidden");fallback.classList.remove("hidden");return;}
  $("thermalMap").classList.remove("hidden");fallback.classList.add("hidden");
  if(!state.map){state.map=L.map("thermalMap",{zoomControl:true,attributionControl:true,preferCanvas:true});ensureBasemaps();}else{ensureBasemaps();}
  if(state.polygonLayer)state.map.removeLayer(state.polygonLayer);if(state.heatLayer)state.map.removeLayer(state.heatLayer);if(state.markerLayer)state.map.removeLayer(state.markerLayer);
  const vals=geo.features.map(featureTemperature).filter(Number.isFinite),min=vals.length?Math.min(...vals):0,max=vals.length?Math.max(...vals):1,span=Math.max(max-min,1e-9);
  state.polygonLayer=L.geoJSON(geo,{style:()=>({color:"#5C6C82",weight:.35,fillColor:"#6E63F0",fillOpacity:.035}),onEachFeature:(f,layer)=>{const tile=tileIdOf(f),temp=featureTemperature(f);layer.bindTooltip(`<strong>Tile ${tile??"—"}</strong><br>${Number.isFinite(temp)?`${temp.toFixed(2)} °C historical air temperature`:"Verified FortyGuard thermal evidence"}`,{sticky:true,direction:"top"});}}).addTo(state.map);
  if(typeof L.heatLayer==="function"){const points=[];for(const f of geo.features){const c=featureCenter(f),t=featureTemperature(f);if(!c||!Number.isFinite(t))continue;points.push([c.lat,c.lng,Math.max(.05,Math.min(1,(t-min)/span))]);}state.heatLayer=L.heatLayer(points,{radius:48,blur:34,maxZoom:17,minOpacity:.22,gradient:{0:"#2b67b1",.25:"#2fa6ca",.45:"#55c778",.65:"#d8ca48",.82:"#ef8b3c",1:"#e8543a"}}).addTo(state.map);}
  state.markerLayer=L.layerGroup().addTo(state.map);for(const h of state.snapshot.hotspots){const f=geo.features.find(x=>tileIdOf(x)===Number(h.tile_id));if(!f)continue;const c=featureCenter(f);if(!c)continue;const pos=state.snapshot.planning_order.indexOf(h.hotspot_rank)+1;const icon=L.divIcon({className:`heatshield-marker rank-${pos}`,html:`<div>${h.hotspot_rank}</div>`,iconSize:pos===1?[34,34]:[30,30],iconAnchor:pos===1?[17,17]:[15,15]});const marker=L.marker(c,{icon}).addTo(state.markerLayer);marker.bindTooltip(`Hotspot ${h.hotspot_rank} • Priority ${fmt(h.planning_priority,2)}`,{direction:"top"});marker.on("click",()=>selectHotspot(h.hotspot_rank));}
  const bounds=state.polygonLayer.getBounds();if(bounds.isValid())state.map.fitBounds(bounds,{padding:[24,24],maxZoom:15});setTimeout(()=>state.map.invalidateSize(),80);
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
function selectHotspot(rank){state.selectedRank=rank;renderSelected();if(state.activeView==="thermal")renderMap();}
function addMessage(role,text){const thread=$("thread"),msg=document.createElement("div");msg.className=`msg ${role}`;msg.textContent=text;thread.appendChild(msg);thread.scrollTop=thread.scrollHeight;}
async function askCopilot(query){if(!query)return;activateView("copilot");addMessage("user",query);$("sendButton").disabled=true;$("sendButton").textContent="Checking evidence…";try{const response=await fetch("/api/v1/copilot/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,mode:"auto",hotspot_rank:state.selectedRank})});const payload=await response.json();if(!response.ok)throw new Error(payload.detail||`HTTP ${response.status}`);addMessage("assistant",payload.answer||"No grounded answer was returned.");}catch(error){addMessage("assistant",`The assistant is unavailable right now: ${error.message}. The verified dashboard evidence is still available.`);}finally{$("sendButton").disabled=false;$("sendButton").textContent="Send";}}
async function loadCopilotStatus(){try{const response=await fetch("/api/v1/copilot/status"),payload=await response.json();$("copilotStatus").textContent=payload.status==="ready"?"Local assistant ready":"Assistant available";$("copilotModel").textContent=payload.model||payload.configured_model||"Configured model";}catch{$("copilotStatus").textContent="Assistant status unavailable";$("copilotModel").textContent="—";}}
async function init(){try{const response=await fetch("/api/v1/dashboard/overview"),payload=await response.json();if(!response.ok)throw new Error(payload.detail||`HTTP ${response.status}`);state.snapshot=payload;
    state.selectedRank=payload.planning_order?.[0]??payload.hotspots?.[0]?.hotspot_rank??null;
    const scenarioRaw=payload.scenario_mode??payload.summary?.scenario_mode??payload.mode??"scenario_replay";
    const scenarioText=String(scenarioRaw).replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
    if($("scenarioLabel")) $("scenarioLabel").textContent=scenarioText;const hash=payload.provenance?.day7_artifact_sha256;$("evidenceHash").textContent=hash?`Evidence SHA ${hash.slice(0,12)}…`:"Evidence lineage available";renderKpis();renderComparison();renderSelected();const initial=(location.hash||"#overview").slice(1);activateView(VIEW_COPY[initial]?initial:"overview",{updateHash:false});}catch(error){$("mapFallback").classList.remove("hidden");$("mapFallback").innerHTML=`<strong>Dashboard evidence could not be loaded.</strong><span>${esc(error.message)}</span>`;}loadCopilotStatus();}

document.querySelectorAll(".nav-link[data-view]").forEach(button=>button.addEventListener("click",()=>activateView(button.dataset.view)));
$("compareHotspotsButton")?.addEventListener("click",()=>activateView("hotspots"));
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
window.addEventListener("hashchange",()=>{const view=location.hash.slice(1);if(VIEW_COPY[view])activateView(view,{updateHash:false});});
init();
