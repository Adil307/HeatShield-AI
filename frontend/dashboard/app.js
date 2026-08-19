const state={snapshot:null,selectedRank:null};
const $=id=>document.getElementById(id);
const fmt=(v,d=1)=>typeof v==="number"&&Number.isFinite(v)?v.toFixed(d):"—";
const esc=v=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
const metric=(v,s="",d=1)=>typeof v==="number"&&Number.isFinite(v)?`${v.toFixed(d)}${s}`:"—";

function tileId(f){const p=f?.properties||{};for(const k of["tile_id","tileId","id","tile","grid_id"]){if(p[k]!=null&&!Number.isNaN(Number(p[k])))return Number(p[k]);}return null}
function tempOf(f){const p=f?.properties||{};for(const k of["average_temperature","avg_temperature","average","avg","temperature","tcm","mean_temperature","mean"]){if(typeof p[k]==="number"&&Number.isFinite(p[k]))return p[k]}for(const[k,v]of Object.entries(p)){if(typeof v==="number"&&/temp|average|mean|tcm/i.test(k))return v}return null}
function rings(g){if(!g)return[];if(g.type==="Polygon")return g.coordinates||[];if(g.type==="MultiPolygon")return(g.coordinates||[]).flat();return[]}
function points(features){const out=[];for(const f of features)for(const r of rings(f.geometry))for(const p of r||[])if(Array.isArray(p)&&p.length>=2&&Number.isFinite(+p[0])&&Number.isFinite(+p[1]))out.push([+p[0],+p[1]]);return out}
function centroid(f){const ps=points([f]);if(!ps.length)return null;let x=0,y=0;for(const[a,b]of ps){x+=a;y+=b}return[x/ps.length,y/ps.length]}
function color(v,min,max){if(!Number.isFinite(v)||!Number.isFinite(min)||!Number.isFinite(max)||max===min)return"hsl(170 55% 38%)";const t=Math.max(0,Math.min(1,(v-min)/(max-min)));const h=210-t*205;return`hsl(${h} 78% ${40+t*12}%)`}

function drawMap(){
  const svg=$("heatmapSvg"),empty=$("mapEmpty"),features=state.snapshot?.heatmap_geojson?.features||[];svg.innerHTML="";
  if(!features.length){empty.classList.remove("hidden");return}empty.classList.add("hidden");
  const ps=points(features);if(!ps.length){empty.classList.remove("hidden");return}
  const xs=ps.map(p=>p[0]),ys=ps.map(p=>p[1]),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys),W=1100,H=650,pad=22;
  const project=([x,y])=>[pad+((x-minX)/Math.max(maxX-minX,1e-9))*(W-pad*2),H-pad-((y-minY)/Math.max(maxY-minY,1e-9))*(H-pad*2)];
  const ts=features.map(tempOf).filter(Number.isFinite),tmin=ts.length?Math.min(...ts):0,tmax=ts.length?Math.max(...ts):1;
  for(const f of features){const id=tileId(f),t=tempOf(f);for(const r of rings(f.geometry)){if(!r?.length)continue;const poly=document.createElementNS("http://www.w3.org/2000/svg","polygon");poly.setAttribute("points",r.map(p=>project(p).join(",")).join(" "));poly.setAttribute("fill",color(t,tmin,tmax));poly.setAttribute("class","heat-tile");poly.onmousemove=e=>{const tip=$("mapTooltip");tip.textContent=`Tile ${id??"—"}${Number.isFinite(t)?` • ${t.toFixed(2)} °C`:""}`;tip.style.left=`${e.offsetX+12}px`;tip.style.top=`${e.offsetY+12}px`;tip.classList.remove("hidden")};poly.onmouseleave=()=>$("mapTooltip").classList.add("hidden");svg.appendChild(poly)}}
  for(const h of state.snapshot.hotspots){const f=features.find(x=>tileId(x)===Number(h.tile_id)),c=f?centroid(f):null;if(!c)continue;const[cx,cy]=project(c),g=document.createElementNS("http://www.w3.org/2000/svg","g");g.onclick=()=>selectHotspot(h.hotspot_rank);const circle=document.createElementNS("http://www.w3.org/2000/svg","circle");circle.setAttribute("cx",cx);circle.setAttribute("cy",cy);circle.setAttribute("r",h.hotspot_rank===state.selectedRank?"18":"14");circle.setAttribute("class",h.hotspot_rank===state.selectedRank?"hotspot-marker hotspot-marker-selected":"hotspot-marker");const label=document.createElementNS("http://www.w3.org/2000/svg","text");label.setAttribute("x",cx);label.setAttribute("y",cy+4);label.setAttribute("text-anchor","middle");label.setAttribute("class","hotspot-label");label.textContent=Math.round(h.planning_priority||0);g.append(circle,label);svg.appendChild(g)}
}

function selected(){return state.snapshot.hotspots.find(h=>h.hotspot_rank===state.selectedRank)}

function renderKpis(){
  const s=state.snapshot.summary,his=state.snapshot.hotspots.map(h=>h.metrics.historical_heat_index_celsius).filter(Number.isFinite),hum=state.snapshot.hotspots.map(h=>h.metrics.historical_relative_humidity_percent).filter(Number.isFinite);
  $("kpiTemp").textContent=metric(s.max_historical_air_temperature_celsius,"°C",2);
  $("kpiHeatIndex").textContent=his.length?`${Math.max(...his).toFixed(1)}°C`:"—";
  $("kpiHotspots").textContent=s.hotspot_count??"—";
  $("kpiPriority").textContent=fmt(s.highest_priority_score,2);
  $("kpiPriorityRank").textContent=s.highest_priority_rank?`Hotspot rank ${s.highest_priority_rank}`:"Verified planning order";
  $("kpiHumidity").textContent=hum.length?`${(hum.reduce((a,b)=>a+b,0)/hum.length).toFixed(1)}%`:"—";
  $("kpiTiles").textContent=s.heatmap_feature_count??"—";
}

function renderSelected(){
  const h=selected();if(!h)return;const m=h.metrics;
  $("selectedScore").textContent=fmt(h.planning_priority,0);$("selectedTitle").textContent=`Hotspot ${h.hotspot_rank}`;$("selectedTile").textContent=`Tile ${h.tile_id??"—"}`;$("selectedRank").textContent=`Priority Rank: #${state.snapshot.planning_order.indexOf(h.hotspot_rank)+1}`;$("priorityBand").textContent=(h.planning_priority_band||"planning priority").toUpperCase();
  const deg=Math.max(0,Math.min(360,(h.planning_priority||0)*3.6));$("priorityRing").style.background=`conic-gradient(#ff3e50 0deg ${deg*.78}deg,#ff7a27 ${deg*.78}deg ${deg}deg,#1d2c40 ${deg}deg 360deg)`;
  $("selectedMetrics").innerHTML=[
    ["Historical Air Temp",metric(m.historical_air_temperature_celsius,"°C",2)],
    ["Historical Heat Index",metric(m.historical_heat_index_celsius,"°C",1)],
    ["Relative Humidity",metric(m.historical_relative_humidity_percent,"%",1)],
    ["Mapped Exposure Proxy",metric(m.mapped_exposure_proxy,"",2)],
    ["Hazard Ordinal",metric(m.hazard_planning_ordinal,"",0)],
    ["Adjusted Priority",h.evidence_status.evidence_adjusted_planning_priority==="withheld"?"WITHHELD":metric(m.evidence_adjusted_planning_priority,"",2)]
  ].map(([a,b])=>`<div class="metric-row"><span>${a}</span><b>${b}</b></div>`).join("");
  const comps=Object.fromEntries((h.contributions||[]).filter(x=>x?.component).map(x=>[x.component,x]));
  const hazard=comps.hazard?.weighted_points,exp=comps.mapped_exposure?.weighted_points,ctx=comps.context_sensitivity_proxy?.weighted_points;
  $("whyText").textContent=`Priority ${fmt(h.planning_priority,2)}/100 is transparently composed from hazard ${fmt(hazard,2)} points, mapped exposure ${fmt(exp,2)} points, and context sensitivity ${fmt(ctx,2)} points.`;
  $("donutScore").textContent=fmt(h.planning_priority,0);
  const total=(hazard||0)+(exp||0)+(ctx||0)||1,p1=((hazard||0)/total)*100,p2=p1+((exp||0)/total)*100;
  $("compositionDonut").style.background=`conic-gradient(#ff434f 0 ${p1}%,#ff8b28 ${p1}% ${p2}%,#6f5df0 ${p2}% 100%)`;
  $("compositionList").innerHTML=[
    ["#ff434f","Hazard",hazard],["#ff8b28","Mapped exposure",exp],["#6f5df0","Context sensitivity",ctx]
  ].map(([c,l,v])=>`<div class="comp-item"><span><i class="comp-dot" style="background:${c}"></i>${l}</span><b>${fmt(v,2)} pts</b></div>`).join("");
  $("evidenceGrid").innerHTML=[
    ["Historical air temperature",metric(m.historical_air_temperature_celsius," °C",2)],
    ["Historical heat index",metric(m.historical_heat_index_celsius," °C",1)],
    ["Apparent temperature",metric(m.historical_apparent_temperature_celsius," °C",1)],
    ["Wet-bulb temperature",metric(m.historical_wet_bulb_temperature_celsius," °C",1)],
    ["Relative humidity",metric(m.historical_relative_humidity_percent,"%",1)],
    ["Mapped exposure proxy",metric(m.mapped_exposure_proxy,"",2)]
  ].map(([l,v])=>`<div class="evidence-cell"><span>${l}</span><strong>${v}</strong></div>`).join("");
  $("vulnStatus").textContent=(h.evidence_status.verified_operational_vulnerability||"unknown").toUpperCase();$("capacityStatus").textContent=(h.evidence_status.verified_adaptive_capacity||"unknown").toUpperCase();$("medicalStatus").textContent=(h.evidence_status.medical_risk_probability||"withheld").toUpperCase();
  renderActions(h);
}

function renderComparison(){
  $("compareBars").innerHTML=state.snapshot.hotspots.map(h=>`<div class="compare-item"><div class="compare-item-head"><span>Hotspot ${h.hotspot_rank}</span><b>${fmt(h.planning_priority,2)}</b></div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(0,Math.min(100,h.planning_priority||0))}%"></div></div></div>`).join("");
  $("topHotspotsList").innerHTML=state.snapshot.hotspots.map((h,i)=>`<div class="top-item"><span class="top-num">${i+1}</span><strong>Hotspot ${h.hotspot_rank}</strong><span>${fmt(h.planning_priority,2)}</span></div>`).join("");
}

function renderActions(h){
  const actions=(h.recommendations||[]).slice(0,5);
  $("compactActions").innerHTML=actions.slice(0,4).map((a,i)=>`<div class="compact-action"><span class="action-icon">${["△","◇","▣","◎"][i]||"↗"}</span><div><strong>${esc(a.title||"Controlled action")}</strong><span>${esc(a.status||"guarded")}</span></div></div>`).join("");
  $("allActions").innerHTML=actions.map(a=>`<article class="action-card"><div class="action-top"><span class="action-tier">${esc(a.priority_tier||"CONTROLLED")}</span><span class="action-status">${esc(a.status||"guarded")}</span></div><h3>${esc(a.title||"Controlled action")}</h3><p>${esc(a.recommendation||"")}</p></article>`).join("");
}

function selectHotspot(rank){state.selectedRank=rank;renderSelected();drawMap()}

function openDrawer(){ $("copilotDrawer").classList.add("open");$("drawerBackdrop").classList.remove("hidden");$("copilotDrawer").setAttribute("aria-hidden","false");setTimeout(()=>$("copilotInput").focus(),120)}
function closeDrawer(){ $("copilotDrawer").classList.remove("open");$("drawerBackdrop").classList.add("hidden");$("copilotDrawer").setAttribute("aria-hidden","true")}
function addMsg(role,text){const box=$("chatWindow"),d=document.createElement("div");d.className=`msg ${role}`;d.innerHTML=`<small>${role==="user"?"YOU":"HEATSHIELD"}</small><p>${esc(text)}</p>`;box.appendChild(d);box.scrollTop=box.scrollHeight}
async function ask(query){if(!query)return;openDrawer();addMsg("user",query);$("sendButton").disabled=true;$("sendButton").textContent="Grounding…";try{const r=await fetch("/api/v1/copilot/ask",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,mode:"auto",hotspot_rank:state.selectedRank})}),p=await r.json();if(!r.ok)throw new Error(p.detail||`HTTP ${r.status}`);addMsg("assistant",p.answer||"No grounded answer returned.")}catch(e){addMsg("assistant",`Copilot unavailable: ${e.message}. Verified dashboard evidence remains available.`)}finally{$("sendButton").disabled=false;$("sendButton").textContent="Ask Copilot"}}
async function loadCopilot(){try{const r=await fetch("/api/v1/copilot/status"),p=await r.json();$("copilotStatus").textContent=p.default_provider==="ollama"?"Local Qwen ready":`${p.default_provider||"Copilot"} ready`;$("copilotModel").textContent=p.model||(p.default_provider==="ollama"?"qwen3:1.7b":"Grounded Copilot")}catch{$("copilotStatus").textContent="Copilot status unavailable"}}

function jump(target){const ids={dashboard:"dashboardSection",map:"mapSection",hotspots:"hotspotsSection",evidence:"evidenceSection",actions:"actionsSection"};$(ids[target])?.scrollIntoView({behavior:"smooth",block:"start"})}
async function init(){try{const r=await fetch("/api/v1/dashboard/overview"),p=await r.json();if(!r.ok)throw new Error(p.detail||`HTTP ${r.status}`);state.snapshot=p;state.selectedRank=p.planning_order?.[0]??p.hotspots?.[0]?.hotspot_rank??null;const hash=p.provenance?.day7_artifact_sha256;const h=hash?`Evidence SHA ${hash.slice(0,12)}…`:"Evidence lineage available";$("evidenceHash").textContent=h;$("footerHash").textContent=h;renderKpis();renderComparison();renderSelected();drawMap()}catch(e){$("mapEmpty").classList.remove("hidden");$("mapEmpty").textContent=`Dashboard evidence could not be loaded: ${e.message}`}loadCopilot()}
document.querySelectorAll(".nav-item[data-target]").forEach(b=>b.onclick=()=>{document.querySelectorAll(".nav-item").forEach(x=>x.classList.remove("active"));b.classList.add("active");jump(b.dataset.target)});
document.querySelectorAll("[data-jump]").forEach(b=>b.onclick=()=>jump(b.dataset.jump));
["openCopilotTop","openCopilotSide","whyCopilotBtn"].forEach(id=>$(id).onclick=()=>id==="whyCopilotBtn"?ask(`Why is hotspot ${state.selectedRank} high priority?`):openDrawer());
$("compareBtn").onclick=()=>jump("hotspots");$("closeCopilot").onclick=closeDrawer;$("drawerBackdrop").onclick=closeDrawer;document.addEventListener("keydown",e=>{if(e.key==="Escape")closeDrawer()});
document.querySelectorAll("[data-prompt]").forEach(b=>b.onclick=()=>{const q=state.selectedRank?b.dataset.prompt.replace(/hotspot \d+/i,`hotspot ${state.selectedRank}`):b.dataset.prompt;ask(q)});
$("copilotForm").onsubmit=e=>{e.preventDefault();const q=$("copilotInput").value.trim();if(!q)return;$("copilotInput").value="";ask(q)};
init();