const state={snapshot:null,selectedRank:null,map:null,heatLayer:null,markerLayer:null};
const $=id=>document.getElementById(id);
const fmt=(v,d=1)=>typeof v==="number"&&Number.isFinite(v)?v.toFixed(d):"—";
const metric=(v,s="",d=1)=>typeof v==="number"&&Number.isFinite(v)?`${v.toFixed(d)}${s}`:"—";
const esc=v=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");

function tileIdOf(feature){const p=feature?.properties||{};for(const k of["tile_id","tileId","id","tile","grid_id"]){if(p[k]!=null&&!Number.isNaN(Number(p[k])))return Number(p[k]);}return null}
function featureTemperature(feature){const p=feature?.properties||{};for(const k of["average_temperature","avg_temperature","average","avg","temperature","tcm","mean_temperature","mean"]){if(typeof p[k]==="number"&&Number.isFinite(p[k]))return p[k]}for(const[k,v]of Object.entries(p)){if(typeof v==="number"&&/temp|average|mean|tcm/i.test(k))return v}return null}
function thermalColor(v,min,max){if(!Number.isFinite(v)||!Number.isFinite(min)||!Number.isFinite(max)||max===min)return"#2389b9";const t=Math.max(0,Math.min(1,(v-min)/(max-min)));if(t<.25)return`hsl(${205-t*80} 72% 43%)`;if(t<.5)return`hsl(${165-(t-.25)*80} 72% 44%)`;if(t<.75)return`hsl(${110-(t-.5)*120} 78% 47%)`;return`hsl(${45-(t-.75)*120} 78% 50%)`}
function selected(){return state.snapshot.hotspots.find(h=>h.hotspot_rank===state.selectedRank)}

function renderMap(){
  const geo=state.snapshot?.heatmap_geojson;
  if(!geo?.features?.length||typeof L==="undefined"){$("realMap").classList.add("hidden");$("mapFallback").classList.remove("hidden");return}
  $("realMap").classList.remove("hidden");$("mapFallback").classList.add("hidden");
  if(!state.map){
    state.map=L.map("realMap",{zoomControl:true,attributionControl:true,preferCanvas:true});
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(state.map);
    L.control.scale({imperial:false,position:"bottomleft"}).addTo(state.map);
  }
  if(state.heatLayer)state.map.removeLayer(state.heatLayer);
  if(state.markerLayer)state.map.removeLayer(state.markerLayer);

  const temps=geo.features.map(featureTemperature).filter(Number.isFinite),min=temps.length?Math.min(...temps):0,max=temps.length?Math.max(...temps):1;
  state.heatLayer=L.geoJSON(geo,{
    style:f=>({color:"#111f2e",weight:.55,fillColor:thermalColor(featureTemperature(f),min,max),fillOpacity:.48}),
    onEachFeature:(f,layer)=>{
      const tid=tileIdOf(f),t=featureTemperature(f);
      layer.bindTooltip(`<div class="heat-tooltip"><strong>Tile ${tid??"—"}</strong>${Number.isFinite(t)?`${t.toFixed(2)} °C historical air temperature`:"Verified thermal evidence"}</div>`,{sticky:true,direction:"top"});
    }
  }).addTo(state.map);

  state.markerLayer=L.layerGroup().addTo(state.map);
  for(const h of state.snapshot.hotspots){
    const feature=geo.features.find(f=>tileIdOf(f)===Number(h.tile_id));
    if(!feature)continue;
    const center=L.geoJSON(feature).getBounds().getCenter();
    const icon=L.divIcon({className:"hotspot-pin",html:`<div class="hotspot-pin-inner"><span>${Math.round(h.planning_priority||0)}</span></div>`,iconSize:[42,42],iconAnchor:[21,38]});
    const marker=L.marker(center,{icon}).addTo(state.markerLayer);
    marker.bindTooltip(`Hotspot ${h.hotspot_rank} • Priority ${fmt(h.planning_priority,2)}`,{direction:"top"});
    marker.on("click",()=>selectHotspot(h.hotspot_rank));
  }
  const bounds=state.heatLayer.getBounds();
  if(bounds.isValid())state.map.fitBounds(bounds,{padding:[24,24],maxZoom:15});
  setTimeout(()=>state.map.invalidateSize(),80);
}

function renderKpis(){
  const s=state.snapshot.summary;
  const heat=state.snapshot.hotspots.map(h=>h.metrics.historical_heat_index_celsius).filter(Number.isFinite);
  const humid=state.snapshot.hotspots.map(h=>h.metrics.historical_relative_humidity_percent).filter(Number.isFinite);
  $("kpiTemp").textContent=metric(s.max_historical_air_temperature_celsius,"°C",2);
  $("kpiHeatIndex").textContent=heat.length?`${Math.max(...heat).toFixed(1)}°C`:"—";
  $("kpiHotspots").textContent=s.hotspot_count??"—";
  $("kpiPriority").textContent=fmt(s.highest_priority_score,2);
  $("kpiPriorityRank").textContent=s.highest_priority_rank?`Hotspot rank ${s.highest_priority_rank}`:"Verified planning order";
  $("kpiHumidity").textContent=humid.length?`${(humid.reduce((a,b)=>a+b,0)/humid.length).toFixed(1)}%`:"—";
  $("kpiTiles").textContent=s.heatmap_feature_count??"—";
}

function renderComparison(){
  $("comparisonBars").innerHTML=state.snapshot.hotspots.map(h=>`
    <div class="comparison-row">
      <div class="comparison-head"><span>Hotspot ${h.hotspot_rank} • Tile ${h.tile_id}</span><b>${fmt(h.planning_priority,2)}</b></div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(0,Math.min(100,h.planning_priority||0))}%"></div></div>
    </div>`).join("");
  $("topHotspots").innerHTML=state.snapshot.hotspots.map((h,i)=>`
    <div class="top-hotspot" data-rank="${h.hotspot_rank}">
      <span class="rank-box">${i+1}</span><strong>Hotspot ${h.hotspot_rank}</strong><span>${fmt(h.planning_priority,2)}</span>
    </div>`).join("");
  document.querySelectorAll(".top-hotspot").forEach(el=>el.onclick=()=>selectHotspot(Number(el.dataset.rank)));
}

function renderSelected(){
  const h=selected();if(!h)return;const m=h.metrics;
  $("selectedTitle").textContent=`Hotspot ${h.hotspot_rank}`;
  $("selectedScore").textContent=fmt(h.planning_priority,0);
  $("selectedTile").textContent=`Tile ${h.tile_id??"—"}`;
  $("selectedRank").textContent=`Priority Rank: #${state.snapshot.planning_order.indexOf(h.hotspot_rank)+1}`;
  $("priorityBand").textContent=(h.planning_priority_band||"planning priority").toUpperCase();

  const deg=Math.max(0,Math.min(360,(h.planning_priority||0)*3.6));
  $("priorityRing").style.background=`conic-gradient(#ff3e50 0deg ${deg*.78}deg,#ff8427 ${deg*.78}deg ${deg}deg,#1d2c40 ${deg}deg 360deg)`;

  $("selectedMetrics").innerHTML=[
    ["Historical Air Temp",metric(m.historical_air_temperature_celsius,"°C",2)],
    ["Historical Heat Index",metric(m.historical_heat_index_celsius,"°C",1)],
    ["Relative Humidity",metric(m.historical_relative_humidity_percent,"%",1)],
    ["Mapped Exposure Proxy",metric(m.mapped_exposure_proxy,"",2)],
    ["Hazard Ordinal",metric(m.hazard_planning_ordinal,"",0)],
    ["Adjusted Priority",h.evidence_status.evidence_adjusted_planning_priority==="withheld"?"WITHHELD":metric(m.evidence_adjusted_planning_priority,"",2)]
  ].map(([a,b])=>`<div class="metric-line"><span>${a}</span><b>${b}</b></div>`).join("");

  const comps=Object.fromEntries((h.contributions||[]).filter(x=>x?.component).map(x=>[x.component,x]));
  const hazard=comps.hazard?.weighted_points,exposure=comps.mapped_exposure?.weighted_points,context=comps.context_sensitivity_proxy?.weighted_points;
  $("whyText").textContent=`Priority ${fmt(h.planning_priority,2)}/100 is composed from hazard ${fmt(hazard,2)} points, mapped exposure ${fmt(exposure,2)} points, and context sensitivity ${fmt(context,2)} points.`;

  $("compositionScore").textContent=fmt(h.planning_priority,0);
  const total=(hazard||0)+(exposure||0)+(context||0)||1,p1=((hazard||0)/total)*100,p2=p1+((exposure||0)/total)*100;
  $("compositionRing").style.background=`conic-gradient(#ff434f 0 ${p1}%,#ff8b28 ${p1}% ${p2}%,#6f5df0 ${p2}% 100%)`;
  $("compositionLegend").innerHTML=[
    ["#ff434f","Hazard",hazard],["#ff8b28","Mapped exposure",exposure],["#6f5df0","Context sensitivity",context]
  ].map(([c,l,v])=>`<div class="composition-item"><span><i class="composition-swatch" style="background:${c}"></i>${l}</span><b>${fmt(v,2)} pts</b></div>`).join("");

  $("evidenceMetrics").innerHTML=[
    ["Historical air temperature",metric(m.historical_air_temperature_celsius," °C",2)],
    ["Historical heat index",metric(m.historical_heat_index_celsius," °C",1)],
    ["Apparent temperature",metric(m.historical_apparent_temperature_celsius," °C",1)],
    ["Wet-bulb temperature",metric(m.historical_wet_bulb_temperature_celsius," °C",1)],
    ["Relative humidity",metric(m.historical_relative_humidity_percent,"%",1)],
    ["Mapped exposure proxy",metric(m.mapped_exposure_proxy,"",2)]
  ].map(([l,v])=>`<div class="evidence-cell"><span>${l}</span><strong>${v}</strong></div>`).join("");

  $("vulnStatus").textContent=(h.evidence_status.verified_operational_vulnerability||"unknown").toUpperCase();
  $("capacityStatus").textContent=(h.evidence_status.verified_adaptive_capacity||"unknown").toUpperCase();
  $("medicalStatus").textContent=(h.evidence_status.medical_risk_probability||"withheld").toUpperCase();

  const actions=(h.recommendations||[]).slice(0,5);
  $("compactActions").innerHTML=actions.slice(0,4).map((a,i)=>`
    <div class="compact-action">
      <span class="compact-icon">${["△","◇","▣","◎"][i]||"↗"}</span>
      <div><strong>${esc(a.title||"Controlled action")}</strong><span>${esc(a.status||"guarded")}</span></div>
    </div>`).join("");
  $("allActions").innerHTML=actions.map(a=>`
    <article class="action-card">
      <div class="action-top"><span class="action-tier">${esc(a.priority_tier||"CONTROLLED")}</span><span class="action-status">${esc(a.status||"guarded")}</span></div>
      <h3>${esc(a.title||"Controlled action")}</h3>
      <p>${esc(a.recommendation||"")}</p>
    </article>`).join("");
}

function selectHotspot(rank){state.selectedRank=rank;renderSelected();renderMap()}

function openCopilot(){ $("copilotDrawer").classList.add("open");$("copilotBackdrop").classList.remove("hidden");$("copilotDrawer").setAttribute("aria-hidden","false");setTimeout(()=>$("copilotInput").focus(),120)}
function closeCopilot(){ $("copilotDrawer").classList.remove("open");$("copilotBackdrop").classList.add("hidden");$("copilotDrawer").setAttribute("aria-hidden","true")}
function addMessage(role,text){const box=$("chatWindow"),div=document.createElement("div");div.className=`message ${role}`;div.innerHTML=`<small>${role==="user"?"YOU":"HEATSHIELD"}</small><p>${esc(text)}</p>`;box.appendChild(div);box.scrollTop=box.scrollHeight}
async function askCopilot(query){if(!query)return;openCopilot();addMessage("user",query);$("sendButton").disabled=true;$("sendButton").textContent="Grounding…";try{const r=await fetch("/api/v1/copilot/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,mode:"auto",hotspot_rank:state.selectedRank})}),p=await r.json();if(!r.ok)throw new Error(p.detail||`HTTP ${r.status}`);addMessage("assistant",p.answer||"No grounded answer returned.")}catch(e){addMessage("assistant",`Copilot unavailable: ${e.message}. Verified dashboard evidence remains available.`)}finally{$("sendButton").disabled=false;$("sendButton").textContent="Ask Copilot"}}
async function loadCopilotStatus(){try{const r=await fetch("/api/v1/copilot/status"),p=await r.json();$("copilotStatus").textContent=p.default_provider==="ollama"?"Local Qwen ready":`${p.default_provider||"Copilot"} ready`;$("copilotModel").textContent=p.model||(p.default_provider==="ollama"?"qwen3:1.7b":"Grounded Copilot")}catch{$("copilotStatus").textContent="Copilot status unavailable"}}

function jump(name){const ids={overview:"overviewSection",map:"mapSection",hotspots:"hotspotsSection",evidence:"evidenceSection",actions:"actionsSection"};$(ids[name])?.scrollIntoView({behavior:"smooth",block:"start"})}

async function init(){
  try{
    const r=await fetch("/api/v1/dashboard/overview"),p=await r.json();if(!r.ok)throw new Error(p.detail||`HTTP ${r.status}`);
    state.snapshot=p;state.selectedRank=p.planning_order?.[0]??p.hotspots?.[0]?.hotspot_rank??null;
    const hash=p.provenance?.day7_artifact_sha256,txt=hash?`Evidence SHA ${hash.slice(0,12)}…`:"Evidence lineage available";$("evidenceHash").textContent=txt;$("footerHash").textContent=txt;
    renderKpis();renderComparison();renderSelected();renderMap();
  }catch(e){
    $("realMap").classList.add("hidden");$("mapFallback").classList.remove("hidden");$("mapFallback").innerHTML=`<strong>Dashboard evidence could not be loaded.</strong><span>${esc(e.message)}</span>`;
  }
  loadCopilotStatus();
}

document.querySelectorAll(".nav-item[data-jump]").forEach(b=>b.onclick=()=>{document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));b.classList.add("active");jump(b.dataset.jump)});
document.querySelectorAll("[data-jump]").forEach(b=>{if(!b.classList.contains("nav-item"))b.onclick=()=>jump(b.dataset.jump)});
$("compareButton").onclick=()=>jump("hotspots");
$("openCopilotSidebar").onclick=openCopilot;$("openCopilotTop").onclick=openCopilot;$("closeCopilot").onclick=closeCopilot;$("copilotBackdrop").onclick=closeCopilot;
$("whyCopilotButton").onclick=()=>askCopilot(`Why is hotspot ${state.selectedRank} high priority?`);
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeCopilot()});
document.querySelectorAll("[data-prompt]").forEach(b=>b.onclick=()=>{const q=state.selectedRank?b.dataset.prompt.replace(/hotspot \d+/i,`hotspot ${state.selectedRank}`):b.dataset.prompt;askCopilot(q)});
$("copilotForm").onsubmit=e=>{e.preventDefault();const q=$("copilotInput").value.trim();if(!q)return;$("copilotInput").value="";askCopilot(q)};
init();