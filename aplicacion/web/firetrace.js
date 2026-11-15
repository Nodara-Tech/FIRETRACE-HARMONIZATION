/* FIRETRACE presentation interface. Uses the intact, real Nodara Tech v3.6 datasets.
   No values from the PDF mockups are presented as actual NASA measurements. */
(()=>{'use strict';
const $=id=>document.getElementById(id);
const number=v=>Number(v||0).toLocaleString('en-US',{maximumFractionDigits:1});
const escapeHTML=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const elapsedDays=(a,b)=>Math.floor((new Date(b+'T12:00:00Z')-new Date(a+'T12:00:00Z'))/86400000)+1;
const fmtDate=s=>{if(!s)return '—';const d=new Date(s+'T12:00:00Z');return d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'})};
const state={catalog:[],id:null,profile:null,from:null,to:null,method:'square',mode:'points',map:null,layer:null,base:null,labels:null,baseType:'satellite',seq:0,last:null,allRegions:[],showHome:true,hasMoved:false,coordMode:false};
let toastHandle=null;
const toast=m=>{const el=$('ftToast');el.textContent=m;el.classList.add('visible');clearTimeout(toastHandle);toastHandle=setTimeout(()=>el.classList.remove('visible'),4200)};
async function get(url){const r=await fetch(url);let obj;try{obj=await r.json()}catch{throw Error('Unexpected response from local server')};if(!r.ok)throw Error(obj.error||'HTTP '+r.status);return obj}
const q=v=>encodeURIComponent(String(v));
function updateClock(){const d=new Date();$('ftClock').textContent=[d.getHours(),d.getMinutes(),d.getSeconds()].map(v=>String(v).padStart(2,'0')).join(':')};updateClock();setInterval(updateClock,1000);
function setView(view){state.showHome=view==='home';$('firetraceApp').classList.toggle('is-home',state.showHome);$('firetraceApp').classList.toggle('is-harmonization',!state.showHome);$('ftMenu').hidden=true;$('ftMenuBtn').setAttribute('aria-expanded','false');setTimeout(()=>state.map?.invalidateSize(),100)}
function setMenu(show){$('ftMenu').hidden=!show;$('ftMenuBtn').setAttribute('aria-expanded',String(show))}
function baseLayer(which){if(!window.L||!state.map)return;state.baseType=which;if(state.base){state.map.removeLayer(state.base);state.base=null}if(state.labels){state.map.removeLayer(state.labels);state.labels=null}
 if(which==='nasa'){
  state.base=L.tileLayer.wms('https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi',{layers:'MODIS_Terra_CorrectedReflectance_TrueColor',format:'image/jpeg',transparent:false,version:'1.1.1',time:state.from||'2024-03-31',attribution:'NASA GIBS / Terra MODIS',maxZoom:11});
 } else if(which==='streets'){
  state.base=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'});
 } else {
  state.base=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:18,attribution:'Tiles © Esri, Earthstar Geographics, Maxar'});
  // No CARTO labels overlay: that service now requires an API key and visibly renders a warning.
  // Use the authorized Esri World Imagery base with its attribution intact.
 }
 state.base.addTo(state.map);state.base.bringToBack();if(state.labels)state.labels.addTo(state.map);
}
function setupMap(){if(!window.L){$('ftMapMessage').hidden=false;$('ftMapMessage').textContent='Map library not loaded. Connect to the Internet to view satellite tiles and map markers.';return}
 state.map=L.map('ftMap',{zoomControl:false,preferCanvas:true,worldCopyJump:true}).setView([38.5,-121.5],6);
 L.control.zoom({position:'bottomright'}).addTo(state.map);
 L.control.scale({position:'bottomleft',metric:true,imperial:false,maxWidth:105}).addTo(state.map);
 state.layer=L.layerGroup().addTo(state.map);baseLayer('satellite');
 state.map.on('click',ev=>{if(!state.coordMode)return;$('ftCoordLat').value=ev.latlng.lat.toFixed(5);$('ftCoordLon').value=ev.latlng.lng.toFixed(5);toast('Coordinates selected. Click Search Detections.');});
 setTimeout(()=>state.map.invalidateSize(),200);
}
function regionArea(region){if(region==='California')return 'Area: 423,970 km²';return 'Processed NASA FIRMS dataset'}
function sortRegions(a,b){const us=val=>!['Costa Rica','Afghanistan'].includes(val);return Number(us(b.region))-Number(us(a.region))||a.region.localeCompare(b.region)||b.year-a.year}
async function initCatalog(){const data=await get('/api/catalogo');state.catalog=data.slice().sort(sortRegions);if(!data.length){$('ftState').innerHTML='<option>No processed datasets</option>';toast('No data available; import NASA FIRMS processing results.');return}
 state.allRegions=data;
 const available=data.slice().sort(sortRegions);const opts=available.map(d=>`<option value="${escapeHTML(d.id)}">${escapeHTML(d.region)} · ${d.year}</option>`).join('');
 $('ftState').innerHTML=opts;$('ftOtherDataset').innerHTML=opts;
 const def=available.find(d=>d.region==='California')||available.find(d=>d.region==='Costa Rica')||available[0];await selectDataset(def.id,true);
}
function updateDateUI(){const days=elapsedDays(state.from,state.to);$('ftDateText').textContent=`${fmtDate(state.from)} - ${fmtDate(state.to)} (${days} days)`;$('ftFrom').value=state.from;$('ftTo').value=state.to;}
function showRegion(){const d=state.catalog.find(x=>x.id===state.id);if(!d)return;
 $('ftRegionName').textContent=d.region;$('ftRegionArea').textContent=regionArea(d.region);
 $('ftStateIcon').textContent=d.region==='California'?'♧':d.region==='Costa Rica'?'✥':d.region==='Afghanistan'?'◇':'♧';
 $('ftState').value=state.id;$('ftOtherDataset').value=state.id;
 if(!['Costa Rica','Afghanistan'].includes(d.region)){$('ftCountryBtn').textContent='United States'}else{$('ftCountryBtn').textContent='Region'}
}
async function selectDataset(id,initialize=false){const dataset=state.catalog.find(x=>x.id===id);if(!dataset)return;state.id=id;showRegion();
 try{const profile=await get('/api/perfil?id='+q(id)+'&metodo=square');state.profile=profile;
 if(Array.isArray(profile.center)&&profile.center.length>=2){$('ftCoordLat').placeholder=Number(profile.center[0]).toFixed(4);$('ftCoordLon').placeholder=Number(profile.center[1]).toFixed(4);}
 const peak=profile.default_date||`${dataset.year}-07-01`;const yearStart=new Date(`${dataset.year}-01-01T12:00:00Z`);const yearEnd=new Date(`${dataset.year}-12-31T12:00:00Z`);
 let d2=new Date(peak+'T12:00:00Z');d2.setUTCDate(d2.getUTCDate()+45);if(d2>yearEnd)d2=yearEnd;
 let d1=new Date(d2);d1.setUTCDate(d1.getUTCDate()-91);if(d1<yearStart)d1=yearStart;
 const iso=d=>d.toISOString().slice(0,10);state.from=iso(d1);state.to=iso(d2);
 $('ftFrom').min=$('ftTo').min=`${dataset.year}-01-01`;$('ftFrom').max=$('ftTo').max=`${dataset.year}-12-31`;
 updateDateUI();if(state.map){state.map.setView(profile.center,profile.zoom);state.hasMoved=false;}
 if(initialize&&dataset.region!=='California'){$('ftSidebarMessage').textContent=`Showing ${dataset.region} ${dataset.year}: California is available when its processed results are added. All data are real.`}
 else $('ftSidebarMessage').textContent='';
 await refresh();
 }catch(e){toast('Could not load dataset: '+e.message);$('ftSidebarMessage').textContent=e.message}
}
function dateValid(){const a=$('ftFrom').value,b=$('ftTo').value;
 if(!a||!b||a>b||a.slice(0,4)!==String(state.profile?.year)||b.slice(0,4)!==String(state.profile?.year)){toast('Choose dates within the selected dataset year.');return false}
 if(elapsedDays(a,b)>366){toast('Select a range of up to one year.');return false}
 state.from=a;state.to=b;updateDateUI();$('ftDatePopup').hidden=true;return true}
function selectedSources(){return Array.from(document.querySelectorAll('.ft-source:checked')).map(n=>n.value)}
function parameters(){const p=new URLSearchParams({id:state.id,desde:state.from,hasta:state.to,metodo:$('ftMethod').value,modo:$('ftMode').value,
    fuentes:selectedSources().join(','),dia_noche:$('ftDayNight').value,solo_vegetacion:$('ftVeg').checked?'1':'0',limite:'1400'});
 if(state.coordMode){const lat=$('ftCoordLat').value,lon=$('ftCoordLon').value,radio=$('ftRadius').value;if(lat&&lon){p.set('lat',lat);p.set('lon',lon);p.set('radio',radio||'80')}}return p;
}
function heatColor(n,max){if(n<=0)return '#283454';const v=n/Math.max(1,max);if(v<.15)return '#fff356';if(v<.35)return '#ffd538';if(v<.55)return '#ffab24';if(v<.75)return '#ff7720';if(v<.9)return '#fa461e';return '#f32222'}
function markerColor(frp){if(frp===null||frp===undefined)return '#ffb63d';const v=Number(frp);return v>=80?'#f22228':v>=35?'#ff4f21':v>=12?'#ff8a20':'#ffe353'}
function drawMap(data){if(!state.map||!window.L)return;
 state.layer.clearLayers();const renderer=L.canvas({padding:.5});const mode=data.mode;
 if(mode==='points'){
  data.features.forEach(item=>{
   const col=markerColor(item.frp);const radius=6.2;
   const shape=L.circleMarker([item.lat,item.lon],{renderer,radius,color:'#7f2c1f',weight:1,fillColor:col,fillOpacity:.95});
   const html=`<strong>${escapeHTML(item.platform||item.source)}</strong><div>${escapeHTML(item.date)} ${escapeHTML(item.time||'')} UTC</div><div>FRP: ${item.frp==null?'not available':number(item.frp)+' MW'}</div><div>Original confidence: ${escapeHTML(item.confidence)}</div><small>Satellite pixel center, not individual fire.</small>`;
   shape.bindPopup(html,{maxWidth:260});shape.addTo(state.layer);
  });
 }else{
  data.features.forEach(item=>{
    if(!item.polygon)return;const color=item.category==='ambos'?'#ff4e28':item.category==='solo_modis'?'#ffd02f':'#ff8c20';
    L.polygon(item.polygon,{color,weight:1.7,fillColor:color,fillOpacity:.31}).bindPopup(`<strong>${escapeHTML(item.category)}</strong><div>${number(item.total)} detections in the period</div><small>Grid cell, not burned-area perimeter.</small>`).addTo(state.layer)
  });
 }
 $('ftLayerLabel').textContent=mode==='points'?'Satellite detections · FRP intensity':$('ftMethod').value==='h3'?'H3 hexagons · resolution 7':'Regular square cells';
 $('ftSampleLabel').textContent=data.limited?`Map sample: ${number(data.features.length)} of ${number(data.total_features)}`:`${number(data.features.length)} elements`;
 if(data.limited){$('ftSidebarMessage').textContent='Map shows a geographic sample to keep navigation responsive. Statistics include all selected records.'}
 if(state.baseType==='nasa'&&state.base){state.base.setParams({time:state.from},false)}
}
function buildPath(vals,color,w,h,pad,max){const n=vals.length;if(!n)return '';
 const xy=vals.map((v,i)=>[(pad.left+i/(Math.max(1,n-1))*(w-pad.left-pad.right)).toFixed(2),(h-pad.bottom-v/Math.max(1,max)*(h-pad.top-pad.bottom)).toFixed(2)]);
 if(xy.length===1)return `M ${xy[0][0]} ${xy[0][1]}`;
 let d=`M ${xy[0][0]} ${xy[0][1]}`;
 for(let i=0;i<xy.length-1;i++){const p0=xy[Math.max(0,i-1)],p1=xy[i],p2=xy[i+1],p3=xy[Math.min(xy.length-1,i+2)];
 const c1x=(+p1[0]+(+p2[0]-(+p0[0]))/6).toFixed(2), c1y=(+p1[1]+(+p2[1]-(+p0[1]))/6).toFixed(2);
 const c2x=(+p2[0]-(+p3[0]-(+p1[0]))/6).toFixed(2),c2y=(+p2[1]-(+p3[1]-(+p1[1]))/6).toFixed(2);
 d+=` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2[0]} ${p2[1]}`;
 }return d}
function smoothed(xs,n=7){return xs.map((_,i)=>{let sum=0,ct=0;for(let j=Math.max(0,i-n+1);j<=i;j++){sum+=xs[j];ct++}return sum/ct})}
function drawChart(data){const daily=data.daily,from=data.range.from,to=data.range.to;
 $('ftChartTitle').textContent=`Daily Detections · 7-day moving average (${fmtDate(from)} - ${fmtDate(to)})`;
 const width=700,height=215,pad={left:45,right:14,top:29,bottom:31};const series=[{key:'modis',color:'#ffd536'},{key:'viirs',color:'#ff8526'},{key:'total',color:'#f83827'}];
 const values=series.map(s=>smoothed(daily.map(d=>d[s.key])));
 const mx=Math.max(1,...values.flat());const max=Math.ceil(mx/(mx>1000?1000:Math.max(1,Math.ceil(mx/5))))*(mx>1000?1000:Math.max(1,Math.ceil(mx/5)));
 let svg='';for(let i=0;i<=5;i++){const y=pad.top+i/5*(height-pad.top-pad.bottom);const val=max*(1-i/5);
  svg+=`<line x1="${pad.left}" x2="${width-pad.right}" y1="${y}" y2="${y}" stroke="#516079" stroke-width="1"/>`+
   `<text x="${pad.left-8}" y="${y+4}" text-anchor="end" fill="#e8ebf5" font-size="12">${number(Math.round(val))}</text>`;}
 const n=daily.length;let count=Math.min(7,n),indices=Array.from({length:count},(_,i)=>Math.round((n-1)*i/Math.max(1,count-1)));
 for(const i of indices){const x=pad.left+i/Math.max(1,n-1)*(width-pad.left-pad.right);
 svg+=`<line x1="${x}" y1="${pad.top}" x2="${x}" y2="${height-pad.bottom}" stroke="#465773" stroke-width="1"/>`;
 svg+=`<text x="${x}" y="${height-8}" text-anchor="middle" fill="#f4f6fd" font-size="11">${fmtDate(daily[i].date).replace(/, \d{4}/,'')}</text>`;}
 for(let k=0;k<series.length;k++){const path=buildPath(values[k],series[k].color,width,height,pad,max);svg+=`<path d="${path}" stroke="${series[k].color}" stroke-width="2.8" stroke-linejoin="round" stroke-linecap="round" fill="none"/>`;}
 $('ftLineChart').innerHTML=svg; $('ftLineChart').setAttribute('aria-label',`Daily satellite detections from ${from} to ${to}. Lines use a trailing 7-day moving average.`);
}
function drawHeatmap(data){const daily=data.daily;const max=Math.max(1,...daily.map(x=>x.total));const dataByDate=new Map(daily.map(x=>[x.date,x]));
 const first=new Date(data.range.from+'T12:00:00Z');const last=new Date(data.range.to+'T12:00:00Z');const pad=(first.getUTCDay()+6)%7;
 const begin=new Date(first);begin.setUTCDate(begin.getUTCDate()-pad);const lastPlus=new Date(last);lastPlus.setUTCDate(lastPlus.getUTCDate()+(6-(lastPlus.getUTCDay()+6)%7));
 const cols=Math.floor((lastPlus-begin)/86400000/7)+1;const grid=$('ftHeatGrid');grid.style.gridTemplateColumns=`repeat(${cols}, minmax(4px,1fr))`;
 const frag=[];for(let day=new Date(begin);day<=lastPlus;day.setUTCDate(day.getUTCDate()+1)){
  const iso=day.toISOString().slice(0,10),r=dataByDate.get(iso),n=r?.total??0;
  const outside=iso<data.range.from||iso>data.range.to;
  frag.push(`<button type="button" class="ft-heat-cell${outside?' empty':''}" ${outside?'disabled':''} data-date="${iso}" style="background:${outside?'transparent':heatColor(n,max)}" title="${iso}: ${number(n)} detections" aria-label="${iso}: ${number(n)} detections"></button>`);
 }
 grid.innerHTML=frag.join('')+'<div class="ft-heat-day-labels">'+['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(s=>`<span>${s}</span>`).join('')+'</div>';
 grid.querySelectorAll('button:not(:disabled)').forEach(el=>el.addEventListener('click',()=>{const d=el.dataset.date;$('ftFrom').value=d;$('ftTo').value=d;if(dateValid())refresh()}));
 const months=[];for(let dt=new Date(first.getUTCFullYear(),first.getUTCMonth(),1);dt<=last;dt.setUTCMonth(dt.getUTCMonth()+1))months.push(dt.toLocaleDateString('en-US',{month:'short',timeZone:'UTC'}));
 $('ftHeatMonths').innerHTML=months.map(m=>`<span>${escapeHTML(m)}</span>`).join('');
 $('ftHeatSubtitle').textContent=`Detections per day · ${fmtDate(data.range.from)} - ${fmtDate(data.range.to)} (${data.range.days} days)`;
 $('ftHeatTotal').textContent=number(data.summary.detections)+' detections';
}
function updateStats(data){const s=data.summary;$('ftDetections').textContent=number(s.detections);$('ftMultisource').textContent=number(s.multisource_cells);
 $('ftCooccurrence').textContent=number(s.cooccurrence_pct)+'%';$('ftCellDays').textContent=number(s.cell_days);
 $('ftMultisource').title=`${number(s.multisource_cells)} distinct spatial cells with both sensor families during the entire selected period (not necessarily on the same day).`;
 $('ftCooccurrence').title=`${number(s.both_cell_days)} cell-days shared by sensor families / ${number(s.cell_days)} active cell-days. Not precision or confidence.`;
}
async function refresh(){if(!state.id||!state.from||!state.to)return;const seq=++state.seq;
 $('ftSearch').disabled=true;$('ftSearch').textContent='Searching…';$('ftMapOverlay').style.display='flex';
 try{
  const params=parameters();const data=await get('/api/firetrace/rango?'+params.toString());if(seq!==state.seq)return;state.last=data;
  updateStats(data);drawMap(data);drawChart(data);drawHeatmap(data);
  if(!data.summary.detections)toast('No detections with the current filters and date range.');
 }catch(e){if(seq!==state.seq)return;toast('Search error: '+e.message);$('ftSidebarMessage').textContent='Search error: '+e.message;console.error('FIRETRACE request',e)}
 finally{if(seq===state.seq){$('ftSearch').disabled=false;$('ftSearch').innerHTML='<span>⌕</span> Search Detections'}}
}
function reset(){document.querySelectorAll('.ft-source').forEach(el=>el.checked=true);$('ftDayNight').value='ambos';$('ftVeg').checked=true;$('ftMethod').value='square';$('ftMode').value='points';$('ftWindow').value='30';$('ftBase').value='satellite';baseLayer('satellite');state.coordMode=false;toggleCoordinates(false);
 if(state.profile){const d=state.profile.default_date?state.profile.default_date.slice(0,7):`${state.profile.year}-07`;let x=new Date(`${d}-01T12:00:00Z`);state.from=x.toISOString().slice(0,10);x.setUTCDate(x.getUTCDate()+91);if(x.getUTCFullYear()>state.profile.year)x=new Date(`${state.profile.year}-12-31T12:00:00Z`);state.to=x.toISOString().slice(0,10);updateDateUI()}refresh();}
function toggleCoordinates(on){state.coordMode=on;$('ftCoordsControls').hidden=!on;$('ftCountryControls').hidden=on;$('ftCoordsBtn').classList.toggle('active',on);$('ftCountryBtn').classList.toggle('active',!on);}
function centerMap(){if(!state.map)return;if(state.coordMode&&$('ftCoordLat').value&&$('ftCoordLon').value){state.map.setView([Number($('ftCoordLat').value),Number($('ftCoordLon').value)],9);return}
 if(state.profile)state.map.setView(state.profile.center,state.profile.zoom)}
function exportDaily(){if(!state.last){toast('Run a search first.');return};const d=state.last;let content='date,total,modis,viirs,active_cell_days,both_cell_days\r\n';for(const row of d.daily)content+=[row.date,row.total,row.modis,row.viirs,row.cell_days,row.both_cell_days].join(',')+'\r\n';const blob=new Blob(['\uFEFF'+content],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`FIRETRACE_${d.dataset.region.replace(/\W+/g,'_')}_${d.range.from}_${d.range.to}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function bind(){
 $('ftMenuBtn').addEventListener('click',()=>setMenu($('ftMenu').hidden));
 $('ftHome').addEventListener('click',()=>setView('home'));
 $('ftHarmonization').addEventListener('click',()=>setView('harmonization'));
 $('ftExport').addEventListener('click',()=>{exportDaily();setMenu(false)});
 $('ftCollapse').addEventListener('click',()=>$('firetraceApp').classList.toggle('filters-hidden'));
 $('ftDateToggle').addEventListener('click',()=>$('ftDatePopup').hidden=!$('ftDatePopup').hidden);
 $('ftDateApply').addEventListener('click',()=>{if(dateValid())refresh()});
 $('ftCountryBtn').addEventListener('click',()=>toggleCoordinates(false));
 $('ftCoordsBtn').addEventListener('click',()=>toggleCoordinates(true));
 $('ftState').addEventListener('change',e=>selectDataset(e.target.value));
 $('ftOtherDataset').addEventListener('change',e=>selectDataset(e.target.value));
 $('ftAdditionalToggle').addEventListener('click',()=>{const show=$('ftExtra').hidden;$('ftExtra').hidden=!show;$('ftAdditionalToggle').setAttribute('aria-expanded',String(show))});
 $('ftSearch').addEventListener('click',()=>{if(dateValid())refresh()});
 $('ftClear').addEventListener('click',reset);
 $('ftLocate').addEventListener('click',centerMap);
 $('ftBase').addEventListener('change',e=>baseLayer(e.target.value));
 $('ftMethod').addEventListener('change',refresh);$('ftMode').addEventListener('change',refresh);
 for(const id of ['ftVeg','ftDayNight'])$(id).addEventListener('change',refresh);
 document.querySelectorAll('.ft-source').forEach(el=>el.addEventListener('change',refresh));
 // The range view summarizes daily co-occurrence; window choices do not recalibrate the summary.
 $('ftWindow').addEventListener('change',()=>toast('This date-range view shows daily co-occurrence. Pass-window matching is a separate statistical analysis.'));
}
bind();setupMap();initCatalog().catch(e=>toast('Catalog unavailable: '+e.message));
})();
