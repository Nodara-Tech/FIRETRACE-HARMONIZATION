/* Visor Nodara Tech. Inspirado en las interacciones de NASA Worldview; no reutiliza su código. */
'use strict';
const $ = sel => document.querySelector(sel);
const $$ = sel => [...document.querySelectorAll(sel)];
const fmt = value => Number(value || 0).toLocaleString('es-CR');
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const COLORS = {modis:'#ef754d','viirs-snpp':'#20a9a5','viirs-jpss1':'#8469e3',solo_modis:'#ef754d',solo_viirs:'#20a9a5',ambos:'#e3ad4c',ambos_paso_cercano:'#ad761e',ambos_solo_dia:'#f2c77e',ambos_paso_vecina:'#856ab4',solo_modis_vecino_cercano:'#bf4932',solo_viirs_vecino_cercano:'#117f76'};
const MONTHS = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
const state = {datasets:[],id:null,profile:null,dates:[],dayIndex:0,mode:'points',temporalWindow:30,spatialMethod:'square',base:'streets',lastFeatures:[],leaflet:null,
    baseOSM:null,baseNASA:null,visualLayer:null,searchPin:null,playTimer:null,refreshNumber:0};
let toastTimer;
function toast(message){const n=$('#toast');n.textContent=message;n.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>n.classList.remove('show'),4500)}
async function jsonFetch(url,opts){const r=await fetch(url,opts);let data;try{data=await r.json()}catch{throw new Error('Respuesta inesperada del servidor')};if(!r.ok)throw new Error(data.error||`Error HTTP ${r.status}`);return data}
function qs(v){return encodeURIComponent(v)}
function selectedSources(){return $$('.sensorCheck:checked').map(el=>el.value)}
function profileDay(){return state.profile?.daily[state.dayIndex]||null}
function selectedDate(){return profileDay()?.date||''}
function setMode(mode,shouldRefresh=true){state.mode=mode;$$('[data-mode]').forEach(btn=>btn.classList.toggle('is-active',btn.dataset.mode===mode));
  const hints={points:'Centros de los píxeles térmicos detectados; cada punto pertenece a una fuente.',cells:'Una celda-día cuenta una vez. En cuadrados, el trazo distingue pareja cercana de coincidencia solo diaria; H3 también usa coincidencias por pasada en la misma celda o vecinas.',pairs:'Parejas de pasadas próximas: pueden corresponder a la misma zona, no necesariamente al mismo incendio.'};
  $('#modeHint').textContent=hints[mode];
  const cellLegend=state.spatialMethod==='square'?
      [['modis','Solo MODIS'],['snpp','Solo VIIRS'],['both','Ambos: pasadas cercanas'],['dayonly','Ambos: solo mismo día']]:
      [['modis','Solo MODIS'],['snpp','Solo VIIRS'],['both','Ambos: pasada en la celda'],['neighbor','Ambos: pasada vecina'],['dayonly','Ambos: solo mismo día']];
  const legend={points:[['modis','MODIS'],['snpp','VIIRS S-NPP'],['noaa','VIIRS NOAA-20']],cells:cellLegend,pairs:[['both','Posibles coincidencias']]};
  $('#legend').innerHTML=legend[mode].map(([id,name])=>`<span><i class="dot ${id}"></i>${name}</span>`).join('');
  updateGeometryBadge();if(shouldRefresh)refreshMap();}
function updateGeometryBadge(){
  const text=state.mode==='cells'?(state.spatialMethod==='h3'?'Hexágonos H3 · r7':'Cuadrados · cuadrícula v2'):
             state.mode==='points'?'Puntos originales MODIS–VIIRS':(state.spatialMethod==='h3'?'Cruces candidatos H3':'Cruces candidatos v2');
  const badge=$('#geometryBadge');if(badge)badge.textContent=text;
  const button=$('#toggleGeometry');if(button){
    button.textContent=state.spatialMethod==='h3'?'Ver cuadrados v2':'Ver hexágonos H3';
    button.title='Cambiar geometría y mostrar las zonas en el mapa';
  }
}
async function changeSpatialMethod(method){
  if(method!=='square'&&method!=='h3')return;
  state.spatialMethod=method;$('#spatialMethod').value=method;
  // El usuario está comparando formas de agrupar zonas, no puntos sin modificar.
  setMode('cells',false);
  updateGeometryBadge();
  await loadProfile(state.id);
  toast(method==='h3'?'Mapa cambiado a hexágonos H3 (resolución 7).':'Mapa cambiado a cuadrados (cuadrícula v2).');
}
function setBase(base){state.base=base;$$('[data-base]').forEach(b=>b.classList.toggle('is-active',b.dataset.base===base));
  if(!state.leaflet){toast('Para ver la capa satelital NASA necesitas Internet y la biblioteca de mapas.');return}
  if(state.baseNASA&&state.leaflet.hasLayer(state.baseNASA))state.leaflet.removeLayer(state.baseNASA);
  if(state.baseOSM&&state.leaflet.hasLayer(state.baseOSM))state.leaflet.removeLayer(state.baseOSM);
  if(base==='nasa'){
    if(!state.baseNASA){state.baseNASA=L.tileLayer.wms('https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi',{
       layers:'MODIS_Terra_CorrectedReflectance_TrueColor',format:'image/jpeg',transparent:false,
       version:'1.1.1',time:selectedDate(),attribution:'NASA GIBS / Terra MODIS',maxZoom:11});}
    state.baseNASA.setParams({time:selectedDate()},false);state.baseNASA.addTo(state.leaflet);
    state.baseNASA.bringToBack();
    toast('Imagen Terra/MODIS de NASA GIBS para la fecha seleccionada; no representa un mapa de incendios.');
  }else{state.baseOSM.addTo(state.leaflet);state.baseOSM.bringToBack();}
}
function setupMap(){
  if(!window.L){$('#mapMessage').hidden=false;$('#mapMessage').textContent='No se pudo cargar Leaflet. Se mostrará un esquema de coordenadas de los registros; conecta a Internet para ver el mapa geográfico y las imágenes NASA.';return}
  const map=L.map('map',{zoomControl:false,preferCanvas:true,worldCopyJump:true}).setView([9.93,-84.05],7);state.leaflet=map;
  L.control.zoom({position:'bottomright'}).addTo(map);
  state.baseOSM=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19,attribution:'© OpenStreetMap contributors'});
  state.baseOSM.addTo(map);
  state.visualLayer=L.layerGroup().addTo(map);
  map.on('click',e=>{const str=`${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`;L.popup().setLatLng(e.latlng).setContent(`<b>Coordenadas</b><br>${str}`).openOn(map);});
  setTimeout(()=>map.invalidateSize(),350);
}
async function loadCatalog(keep=true){
  const list=await jsonFetch('/api/catalogo');state.datasets=list;
  const select=$('#datasetSelect');const chosen=keep && state.id && list.some(x=>x.id===state.id)?state.id:(list.find(x=>x.region==='Costa Rica'&&x.year===2024)?.id||list[0]?.id);
  select.innerHTML=list.map(d=>`<option value="${esc(d.id)}">${esc(d.region)} · ${d.year}${d.demo?' (ejemplo real)':''}</option>`).join('');
  if(!chosen){select.innerHTML='<option>No hay análisis disponibles</option>';$('#viewTitle').textContent='No hay datos todavía';return}
  select.value=chosen;await loadProfile(chosen);
}
async function loadProfile(id){
  try{
    const previous=(state.id===id)?selectedDate():null;
    state.id=id;
    $('#spatialAudit').textContent='Auditoría pendiente para el conjunto seleccionado. Pulsa comparar área y bordes.';
    $('#qualityAudit').textContent='Análisis pendiente: selecciona la ventana y pulsa comparar seis escenarios de confianza.';
    state.profile=await jsonFetch('/api/perfil?id='+qs(id)+'&metodo='+qs(state.spatialMethod));
    state.dates=state.profile.daily.map(x=>x.date);
    state.dayIndex=Math.max(0,state.dates.indexOf(previous && state.dates.includes(previous)?previous:state.profile.default_date));
    const p=state.profile;
    $('#regionHeader').textContent=p.region+' · '+p.year;
    $('#crumbRegion').textContent=p.region.toUpperCase();
    $('#viewTitle').textContent='Actividad térmica · '+p.region;
    $('#viewSubtitle').textContent=p.year+' · MODIS y VIIRS · '+p.spatial_description;
    $('#dateInput').min=state.dates[0];$('#dateInput').max=state.dates[state.dates.length-1];
    $('#daySlider').min=0;$('#daySlider').max=Math.max(0,state.dates.length-1);
    if(state.leaflet){state.leaflet.setView(p.center,p.zoom);setTimeout(()=>state.leaflet.invalidateSize(),120)}
    drawMonthly();drawSparks();updateGeometryBadge();await refreshMap();
  }catch(err){toast('No se pudo abrir el conjunto: '+err.message)}
}
function selectIndex(idx){
  if(!state.dates.length)return;
  state.dayIndex=Math.max(0,Math.min(state.dates.length-1,idx));
  refreshMap();
}
function stepDay(delta){
  const data=state.profile?.daily;if(!data)return;
  let i=state.dayIndex;
  const onlyActive=$('#skipEmpty').checked;
  do{i=(i+delta+data.length)%data.length;}while(onlyActive&&data[i].active===0&&i!==state.dayIndex);
  selectIndex(i);
}
function drawMonthly(){
  const m=state.profile.monthly;const max=Math.max(1,...m.map(x=>x.active));
  const month=selectedDate().slice(0,7);
  $('#monthlyChart').innerHTML=m.map((x,i)=>`<div class="month-item ${month===x.month?'active':''}" data-month="${esc(x.month)}" title="${MONTHS[i]}: ${fmt(x.active)} celdas-día"><i class="bar" style="height:${Math.max(2,Math.round(x.active/max*140))}px"></i><small>${MONTHS[i]}</small></div>`).join('');
  $$('.month-item').forEach(el=>el.addEventListener('click',()=>{
    const possible=state.profile.daily.filter(d=>d.date.startsWith(el.dataset.month)).sort((a,b)=>b.active-a.active);
    if(possible.length)selectIndex(state.dates.indexOf(possible[0].date));
  }));
}
function drawSparks(){
  const xs=state.profile.daily;const biggest=Math.max(1,...xs.map(x=>x.active));
  $('#timelineSparks').innerHTML=xs.map((x,i)=>`<i style="height:${Math.max(2,Math.round(x.active/biggest*31))}px" class="${state.dayIndex===i?'active':''}"></i>`).join('');
}
function updateTimeline(){
  const d=profileDay();if(!d)return;
  $('#dateInput').value=d.date;$('#daySlider').value=state.dayIndex;
  $('#slidePos').textContent=(state.dayIndex+1)+' / '+state.dates.length;
  const dateObj=new Date(d.date+'T12:00:00Z');
  $('#selectedDay').textContent=new Intl.DateTimeFormat('es-CR',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(dateObj);
  $('#dateChip').textContent=d.date+' UTC';
  $('#statCells').textContent=fmt(d.active);$('#statBoth').textContent=fmt(d.both);
  $('#bothCells').textContent=fmt(d.both);$('#onlyModis').textContent=fmt(d.only_modis);$('#onlyViirs').textContent=fmt(d.only_viirs);
  const total=d.active||1;
  $('#distributionBar').innerHTML=[[d.both,COLORS.ambos],[d.only_modis,COLORS.modis],[d.only_viirs,COLORS.solo_viirs]].map(([n,color])=>`<span style="width:${(n/total*100).toFixed(2)}%;background:${color}"></span>`).join('');
  $('.month-item.active')?.classList.remove('active');
  $$('.month-item').find(el=>el.dataset.month===d.date.slice(0,7))?.classList.add('active');
  const sparks=$$('.timeline-sparks i');sparks.forEach((x,i)=>x.classList.toggle('active',i===state.dayIndex));
  if(state.base==='nasa'&&state.baseNASA)state.baseNASA.setParams({time:d.date},false);
}
function popupTable(rows){return `<table class="popup-table">${rows.filter(x=>x[1]!==null&&x[1]!==undefined&&x[1]!=='').map(x=>`<tr><td>${esc(x[0])}</td><td>${esc(x[1])}</td></tr>`).join('')}</table>`}
function pointPopup(d){return `<b>${esc(d.platform||d.source)}</b><div class="popup-muted">Foco térmico · ${esc(selectedDate())} ${esc(d.time||'')} UTC</div>`+
 popupTable([['Latitud',Number(d.lat).toFixed(5)],['Longitud',Number(d.lon).toFixed(5)],['FRP',d.frp==null?'Sin dato':Number(d.frp).toFixed(2)+' MW'],['Brillo ~4 µm',d.t4==null?'':Number(d.t4).toFixed(1)+' K'],['Brillo ~11 µm',d.t11==null?'':Number(d.t11).toFixed(1)+' K'],['Confianza',d.confidence],['Scan / Track',`${d.scan??'—'} / ${d.track??'—'} km`],['Tipo',d.type]])+
 `<div class="popup-muted">El punto marca el centro de un píxel, no el centro del fuego.</div>`}
function cellPopup(d){const label={ambos:'MODIS y VIIRS',solo_modis:'Solo MODIS',solo_viirs:'Solo VIIRS'}[d.category]||d.category;
 const extra=d.polygon?(d.parejas_misma_celda?`H3: ${d.parejas_misma_celda} parejas candidatas dentro del mismo hexágono; intervalo de ${state.temporalWindow} min.`:
    d.parejas_vecinas?`H3: ${d.parejas_vecinas} parejas candidatas entre celdas vecinas (k=1), con control de tiempo y distancia.`:
    d.category==='ambos'?'Ambos durante el día, pero no se identificó pareja de pasada cercana con criterios H3.':'Solo una familia dentro de esta celda; ausencia de otra familia no implica ausencia de fuego.'):
    d.concordancia==='ambos_paso_cercano'?`Ambos en el día y al menos una pareja candidata cercana (${d.parejas_pasada_cercana||0}). No confirma mismo incendio.`:
    d.concordancia==='ambos_solo_dia'?'Ambos en el mismo día, sin pareja cercana dentro de los criterios del motor.':
    'Solo una familia con detección registrada; falta de detección no equivale a observación negativa.';
 return `<b>Celda con detección: ${esc(label)}</b><div class="popup-muted">${esc(selectedDate())} · Agrupación exploratoria</div>`+
 popupTable([['Método',d.polygon?'H3 hexagonal':'Cuadrícula v2'],['ID H3',d.id?.startsWith('8')?d.id:null],['Área hexágono',d.area_km2==null?null:d.area_km2.toFixed(3)+' km²'],['MODIS',d.n_modis],['VIIRS S-NPP',d.n_snpp],['VIIRS NOAA-20',d.n_noaa20],['Detecciones originales',d.total],['Pares H3 misma celda',d.polygon?d.parejas_misma_celda:null],['Pares H3 con vecino',d.polygon?d.parejas_vecinas:null]])+
 `<div class="popup-muted">${esc(extra)} La celda no es el perímetro de un incendio ni una huella satelital.</div>`}
function pairPopup(d){return `<b>Candidato MODIS ↔ VIIRS</b><div class="popup-muted">Proximidad de pasadas · ${esc(selectedDate())}</div>`+
 popupTable([['Plataformas',`${d.modis} / ${d.viirs}`],['Separación',d.distance_km==null?'—':(d.distance_km*1000).toFixed(0)+' m'],['Diferencia horaria',d.delta_minutes+' min'],['Relación espacial',d.relation_h3?(d.relation_h3==='vecinas'?'H3: hexágonos vecinos':'H3: mismo hexágono'):null],['H3 MODIS',d.h3_modis],['H3 VIIRS',d.h3_viirs],['Píxeles',`${d.n_modis} MODIS / ${d.n_viirs} VIIRS`],['FRP MODIS',d.frp_modis==null?'—':d.frp_modis.toFixed(1)+' MW'],['FRP VIIRS',d.frp_viirs==null?'—':d.frp_viirs.toFixed(1)+' MW']])+
 `<div class="popup-muted">Coincidencia candidata, no confirmación de incendio individual.</div>`}
function renderFallback(features){
  const root=$('#map');root.innerHTML='';
  const canvas=document.createElement('canvas');canvas.width=Math.max(400,root.clientWidth*devicePixelRatio);canvas.height=Math.max(340,root.clientHeight*devicePixelRatio);canvas.style.width='100%';canvas.style.height='100%';root.append(canvas);
  const ctx=canvas.getContext('2d'), w=canvas.width,h=canvas.height;ctx.fillStyle='#dfe9e9';ctx.fillRect(0,0,w,h);
  ctx.strokeStyle='#c4d4da';ctx.lineWidth=1;for(let i=1;i<10;i++){ctx.beginPath();ctx.moveTo(w*i/10,0);ctx.lineTo(w*i/10,h);ctx.stroke();ctx.beginPath();ctx.moveTo(0,h*i/10);ctx.lineTo(w,h*i/10);ctx.stroke()}
  let xs=features.map(x=>Number(x.lon)).filter(Number.isFinite),ys=features.map(x=>Number(x.lat)).filter(Number.isFinite);
  let minx=xs.length?Math.min(...xs)-.6:-86,maxx=xs.length?Math.max(...xs)+.6:-82;
  let miny=ys.length?Math.min(...ys)-.6:8,maxy=ys.length?Math.max(...ys)+.6:11;
  if(maxx-minx<1){maxx+=.5;minx-=.5}if(maxy-miny<1){maxy+=.5;miny-=.5}
  features.forEach(p=>{const x=(p.lon-minx)/(maxx-minx)*w,y=h-(p.lat-miny)/(maxy-miny)*h;ctx.beginPath();ctx.arc(x,y,state.mode==='cells'?8:5,0,Math.PI*2);ctx.fillStyle=COLORS[p.source]||COLORS[p.category]||COLORS.ambos;ctx.globalAlpha=.75;ctx.fill();ctx.globalAlpha=1});
  ctx.font=`${Math.max(13,w/65)}px Segoe UI`;ctx.fillStyle='#406377';ctx.fillText('Esquema de coordenadas · mapa base no disponible',18,28);
}
function drawMap(features){
  if(!state.leaflet){renderFallback(features);return}
  state.visualLayer.clearLayers();
  const renderer=L.canvas({padding:.5});
  if(state.mode==='points'){
    for(const f of features){let radius=f.frp==null?4:Math.min(11,4+Math.log10(Math.max(1,f.frp))*3);
      L.circleMarker([f.lat,f.lon],{renderer,radius,color:COLORS[f.source]||'#64748b',fillColor:COLORS[f.source]||'#64748b',
        fillOpacity:.68,weight:1,opacity:.88}).bindPopup(pointPopup(f),{maxWidth:280}).addTo(state.visualLayer)}
  }else if(state.mode==='cells'){
    for(const f of features){if(!f.bounds&&!f.polygon)continue;
      const key=f.polygon&&f.category==='ambos'?(f.parejas_misma_celda?'ambos_paso_cercano':f.parejas_vecinas?'ambos_paso_vecina':'ambos_solo_dia'):
        (f.concordancia||f.category);
      const opts={renderer,color:COLORS[key]||'#999',weight:(key==='ambos_paso_cercano'||key==='ambos_paso_vecina'||key.endsWith('vecino_cercano'))?2:1,
                  dashArray:(key==='ambos_solo_dia'||key==='ambos_paso_vecina')?'5 4':null,fillOpacity:key==='ambos_paso_cercano'?.40:.25,opacity:.8};
      const geom=f.polygon?L.polygon(f.polygon,opts):L.rectangle(f.bounds,opts);
      geom.bindPopup(cellPopup(f),{maxWidth:280}).addTo(state.visualLayer)}
  }else{
    for(const f of features){L.circleMarker([f.lat,f.lon],{renderer,radius:7,color:'#bd8b2d',fillColor:COLORS.ambos,
        fillOpacity:.75,weight:2}).bindPopup(pairPopup(f),{maxWidth:280}).addTo(state.visualLayer)}
  }
}
async function refreshMap(){
  if(!state.profile)return;
  const id=state.id,date=selectedDate(),mode=state.mode,seq=++state.refreshNumber;
  updateTimeline();$('#mapCount').textContent='Consultando observaciones…';
  const base=`id=${qs(id)}&fecha=${qs(date)}&metodo=${qs(state.spatialMethod)}&ventana=${state.temporalWindow}`;
  const extra=`&fuentes=${qs(selectedSources().join(','))}&solo_vegetacion=${$('#type0').checked?'1':'0'}&dia_noche=${qs($('#daynight').value)}`;
  try{
    const promises=[jsonFetch('/api/dia?'+base+'&modo='+mode+(mode==='points'?extra:''))];
    if(mode!=='points')promises.push(jsonFetch('/api/dia?'+base+'&modo=points'+extra));
    if(mode!=='pairs')promises.push(jsonFetch('/api/dia?'+base+'&modo=pairs'));
    const fetched=await Promise.all(promises);if(seq!==state.refreshNumber)return;
    const data=fetched[0];state.lastFeatures=data.features;
    const today=profileDay();$('#statCells').textContent=fmt(today?.active);$('#statBoth').textContent=fmt(today?.both);
    let pointsCount=mode==='points'?data.features.length:fetched[1].features.length;
    let pairCount=mode==='pairs'?data.features.length:fetched[fetched.length-1].features.length;
    $('#statPoints').textContent=fmt(pointsCount)+(mode==='points'&&data.limited?'+':'');
    $('#statPairs').textContent=fmt(pairCount);$('#pairStatNote').textContent=`Ventana ${state.temporalWindow} min · parejas candidatas ${state.spatialMethod==='h3'?'H3 r7':'v2'}`;
    $('#mapCount').textContent=fmt(data.features.length)+(data.limited?'+':'')+' elementos';
    $('#mapNote').textContent=data.notice+(data.limited?' Se aplicó un límite de visualización; utiliza filtros para reducir los puntos.':'');
    drawMap(data.features);
    jsonFetch('/api/temporal?'+base).then(d=>{
      if(seq!==state.refreshNumber)return;renderTemporalSensitivity(d);
    }).catch(e=>{$('#temporalSensitivity').textContent='Análisis temporal no disponible: '+e.message});
    jsonFetch('/api/concordancia?'+base).then(d=>{
      if(seq!==state.refreshNumber)return;
      const c=d.celdas;
      if(state.spatialMethod==='h3'){
        $('#concordanceSummary').innerHTML=
          `<div class="concordance-line"><span>Ambos: pareja en mismo hexágono</span><b>${fmt(c.ambos_misma_celda)}</b></div>`+
          `<div class="concordance-line"><span>Ambos: pareja entre vecinos</span><b>${fmt(c.ambos_con_pareja_vecina)}</b></div>`+
          `<div class="concordance-line"><span>Ambos: solo coincidencia diaria</span><b>${fmt(c.ambos_solo_dia)}</b></div>`+
          `<div class="concordance-line concordance-total"><span>Total compartidas H3</span><b>${fmt(d.ambos_diarios)}</b></div>`+
          `<div class="concordance-line"><span>Solo MODIS con pareja en vecino</span><b>${fmt(c.solo_modis_con_pareja_vecina)}</b></div>`+
          `<div class="concordance-line"><span>Solo VIIRS con pareja en vecino</span><b>${fmt(c.solo_viirs_con_pareja_vecina)}</b></div>`;
      }else{
        $('#concordanceSummary').innerHTML=
          `<div class="concordance-line"><span>Ambos con pasada cercana</span><b>${fmt(c.ambos_paso_cercano)}</b></div>`+
          `<div class="concordance-line"><span>Ambos solo en el día</span><b>${fmt(c.ambos_solo_dia)}</b></div>`+
          `<div class="concordance-line concordance-total"><span>Total compartidas en cuadrados</span><b>${fmt(d.ambos_diarios)}</b></div>`;
      }
      $('#concordanceMethodNote').textContent=state.spatialMethod==='h3'?
        `H3 r7: ventana ${d.pasadas_ventana_minutos} min, misma celda o vecinas k=1, y distancia de huellas aproximada. Las celdas con una sola familia NO se convierten en «ambos» por vecindad.`:
        `Se usa la ventana de ${d.pasadas_ventana_minutos} min y el criterio espacial de la v2; son candidatos, no incendios confirmados.`;
    }).catch(e=>{$('#concordanceSummary').textContent='Concordancia no disponible: '+e.message});
    jsonFetch('/api/espacial?'+base).then(d=>{
      if(seq!==state.refreshNumber)return;
      $('#spatialComparison').innerHTML=`<div class="spatial-mini"><span>Cuadrícula v2 (${d.square.km??'—'} km)</span><b>${fmt(d.square.cells)}</b><small>${fmt(d.square.both)} compartidas</small></div>`+
        `<div class="spatial-mini"><span>H3 r7</span><b>${fmt(d.h3.cells)}</b><small>${fmt(d.h3.both)} compartidas</small></div>`;
    }).catch(e=>{$('#spatialComparison').textContent='Comparación no disponible: '+e.message;});
  }catch(err){if(seq!==state.refreshNumber)return;const detail=String(err?.message||err);
    $('#mapCount').textContent='No se pudieron cargar los datos';
    $('#mapNote').textContent='Error al consultar las observaciones: '+detail+' · Ejecuta COMPROBAR.bat o diagnosticar_visor.py.';
    $('#statPoints').textContent='—';$('#statPairs').textContent='—';
    console.error('Nodara visor: fallo de datos', {id,date,mode,detail},err);toast('Error de datos: '+detail)}
}
function renderTemporalSensitivity(resp){
  const list=resp.escenarios||[];
  const rows=list.map(e=>{
    const w=e.global.ventana_min, selected=w===state.temporalWindow;
    return `<tr class="${selected?'selected-window':''}"><td>${w} min${selected?' · actual':''}</td>`+
      `<td>${fmt(e.dia.parejas_candidatas_dia)}</td>`+
      `<td>${fmt(e.dia.ambos_paso_cercano)} / ${fmt(e.dia.ambos_diarios)}</td></tr>`;
  }).join('');
  $('#temporalSensitivity').innerHTML=`<table class="temporal-table"><thead><tr>`+
       `<th>Ventana</th><th>Pares del día</th><th>Celdas próximas / compartidas</th></tr></thead>`+
       `<tbody>${rows}</tbody></table>`+
       `<div class="temporal-global"><b>Todo el año:</b> `+
       list.map(e=>`${e.global.ventana_min} min: ${fmt(e.global.celdas_con_pareja)} de ${fmt(e.global.celdas_dia_ambos)} celdas compartidas`).join(' · ')+`</div>`;
  const current=list.find(e=>e.global.ventana_min===state.temporalWindow)?.global;
  $('#temporalSensitivityNote').textContent=current?
    `Ventana ${state.temporalWindow} min: ${fmt(current.parejas_candidatas)} parejas candidatas en el año. `+
    `Proporción de celdas compartidas con pareja cercana: ${(current.proporcion_con_pareja*100).toFixed(1)} %. `+
    `Esto NO mide precisión. Bootstrap por día (estabilidad interna): `+
    (current.ic_bootstrap_dias_inf==null?'sin muestra suficiente':
    `${(current.ic_bootstrap_dias_inf*100).toFixed(1)}–${(current.ic_bootstrap_dias_sup*100).toFixed(1)} %`)+`. `+
    (state.spatialMethod==='h3'?` H3 tiene emparejamiento temporal independiente con vecinos y distancia de huellas.`:' Cuadrícula v2: coincidencias solo dentro de cada celda.'):
    'El tamaño de ventana no determina la confiabilidad científica de los pares.';
}
async function runSpatialAudit(){
  const button=$('#runSpatialAudit'),node=$('#spatialAudit');
  if(!state.id)return;
  button.disabled=true;
  button.textContent='Calculando 33 escenarios…';
  node.textContent='Analizando el año completo: H3 y 16 desplazamientos en cada escala cuadrada.';
  const originalId=state.id,win=state.temporalWindow;
  try{
    const report=await jsonFetch('/api/auditoria-espacial?id='+qs(originalId)+'&ventana='+win);
    if(state.id!==originalId||state.temporalWindow!==win){
       node.textContent='El conjunto o la ventana cambiaron. Ejecuta nuevamente la auditoría para la selección actual.';
       return;
    }
    const row=(title,area,same,neighbors,note)=>`<tr><td>${esc(title)}<small>${esc(note)}</small></td>`+
       `<td>${Number(area).toFixed(2)}</td><td>${esc(String(same))}</td><td>${esc(String(neighbors))}</td></tr>`;
    const h=report.h3,scenarios=report.resumen_desplazamientos;
    const metric=(s,name)=>{const v=s[name];return `${fmt(v.min)}–${fmt(v.max)} (media ${Number(v.media).toFixed(1)})`};
    const s1=scenarios.find(s=>s.metodo==='cuadrado_2km');
    const s2=scenarios.find(s=>s.metodo==='cuadrado_area_H3');
    node.innerHTML=`<div class="audit-info"><b>Comparación anual · ${esc(String(report.anio))} · ${win} min</b>`+
      `<span>33 escenarios: H3 r7 + 16 cuadrados de 2 km + 16 cuadrados equiparados en área.</span></div>`+
      `<div class="audit-scroll"><table class="temporal-table audit-table"><thead><tr><th>Geometría</th><th>Área km²</th><th>Pares internos</th><th>Pares con vecindad</th></tr></thead><tbody>`+
      row('H3 r7',report.promedio_area_hexagono_km2,fmt(h.pares_estrictos_misma_celda),fmt(h.pares_con_vecinos),'1 partición, 6 vecinos')+
      row('Cuadrados 2 km',4,metric(s1,'pares_estrictos_misma_celda'),metric(s1,'pares_con_vecinos'),'16 orígenes, 8 vecinos')+
      row('Cuadrados de área H3',report.promedio_area_hexagono_km2,metric(s2,'pares_estrictos_misma_celda'),metric(s2,'pares_con_vecinos'),'16 orígenes, 8 vecinos')+
      `</tbody></table></div><p>Cuadrado equivalente: <b>${Number(report.lado_cuadrado_equivalente_km).toFixed(3)} km</b> de lado. `+
      `Cada intervalo es el <b>mínimo–máximo entre 16 desplazamientos</b>, no un intervalo de confianza. `+
      `El área H3 es media global, no idéntica en cada hexágono.</p>`+
      `<p class="audit-disclaimer">Si H3 cae dentro del rango de los cuadrados, las diferencias pueden explicarse parcialmente por tamaño y bordes. `+
      `Estar fuera del rango tampoco prueba mayor exactitud; faltan referencias independientes.</p>`;
  }catch(e){node.textContent='No se pudo realizar la auditoría: '+e.message;}
  finally{button.disabled=false;button.textContent='Repetir análisis de área y bordes';}
}

async function runQualityAudit(){
  const button=$('#runQualityAudit'), node=$('#qualityAudit');
  if(!state.id||!selectedDate())return;
  const originalId=state.id, win=state.temporalWindow,day=selectedDate();
  button.disabled=true;button.textContent='Evaluando filtros y volviendo a emparejar…';
  node.textContent='Calculando seis escenarios sobre los mismos registros type=0, con H3 y cuadrados. Puede tardar la primera vez.';
  try{
    const url='/api/auditoria-calidad?id='+qs(originalId)+'&fecha='+qs(day)+'&ventana='+win;
    const data=await jsonFetch(url);
    if(state.id!==originalId||state.temporalWindow!==win||selectedDate()!==day){
      node.textContent='Cambió el conjunto, fecha o ventana durante el análisis. Repite el cálculo para la selección actual.';return;
    }
    const known=['modis','viirs-snpp','viirs-jpss1'];
    const get=(key,k)=>Number(data.distribucion?.[key]?.[k]||0);
    const low=get('viirs-snpp','l')+get('viirs-jpss1','l');
    const totalViirs=['viirs-snpp','viirs-jpss1'].reduce((acc,k)=>acc+Object.values(data.distribucion?.[k]||{}).reduce((x,v)=>x+Number(v),0),0);
    const modisLow=get('modis','<30')+get('modis','30-49');
    const lDay=Number(data.distribucion_periodo?.['viirs-snpp:D']?.l||0)+Number(data.distribucion_periodo?.['viirs-jpss1:D']?.l||0);
    const lNight=Number(data.distribucion_periodo?.['viirs-snpp:N']?.l||0)+Number(data.distribucion_periodo?.['viirs-jpss1:N']?.l||0);
    const base=data.escenarios.find(x=>x.escenario==='todas');
    const heading=`<div class="audit-info"><b>Sensibilidad anual · ${esc(String(data.anio))} · ${win} min</b>`+
      `<span>${fmt(data.registros_type0)} detecciones de vegetación originales; ${fmt(low)} VIIRS clase l (${totalViirs? (low/totalViirs*100).toFixed(1):'0'} % de VIIRS); ${fmt(modisLow)} MODIS con valor inferior a 50. VIIRS l: ${fmt(lDay)} diurnos y ${fmt(lNight)} nocturnos.</span></div>`;
    const rows=data.escenarios.map(r=>{
      const sc=r.cuadricula,h3=r.h3;
      const dr=data.diarios?.[r.escenario]||{};
      const sqDay=dr.square?.parejas??0,hDay=dr.h3?.parejas??0;
      const selected=r.escenario==='todas'?' selected-window':'';
      return `<tr class="${selected}"><td><b>${esc(r.etiqueta)}</b><small>${esc(r.escenario)}</small></td>`+
         `<td>${fmt(r.registros_type0)} <small>${Number(r.retencion_registros_pct).toFixed(1)} %</small></td>`+
         `<td>${fmt(sc.parejas)} <small>${fmt(sqDay)} en fecha</small></td>`+
         `<td>${fmt(h3.parejas)} <small>${fmt(hDay)} en fecha</small></td></tr>`;
    }).join('');
    const chosen=state.spatialMethod==='h3'?'h3':'cuadricula';
    const diffs=data.escenarios.filter(x=>x.escenario!=='todas').map(r=>{
      const b=base[chosen].parejas,n=r[chosen].parejas;
      const pct=b?(100*(n-b)/b).toFixed(1):'—';
      return `${esc(r.etiqueta)}: ${pct==='—'?'sin base':pct+' %'}`;
    }).join(' · ');
    const previousQuality=data.calidad_original_v2!=='todas'?`<p class="audit-disclaimer">Atención: el análisis v2 de este conjunto ya fue generado con el filtro ${esc(data.calidad_original_v2)}; por eso la fila sin filtros NO tiene que coincidir con las métricas base del mapa.</p>`:'';
    node.innerHTML=heading+previousQuality+`<div class="audit-scroll"><table class="temporal-table audit-table quality-table">`+
      `<thead><tr><th>Escenario</th><th>Registros type=0</th><th>Parejas cuadrados<br>(año / fecha)</th><th>Parejas H3<br>(año / fecha)</th></tr></thead><tbody>${rows}</tbody></table></div>`+
      `<p class="quality-details"><b>Variación en ${chosen==='h3'?'H3':'cuadrados'} frente a la referencia:</b> ${diffs}.</p>`+
      `<p>VIIRS l/n/h son categorías del algoritmo; VIIRS h suele corresponder a saturación. `+
      `MODIS 50 y 80 son <b>umbrales de sensibilidad elegidos para comparar</b>, no valores de confianza probabilística certificados.</p>`+
      `<p class="audit-disclaimer">La fila «sin filtro» reproduce el motor base. El conteo de parejas puede cambiar porque se recalculan las pasadas y el emparejamiento después de filtrar. `+
      `No se midieron falsos positivos, falsos negativos ni precisión. El mapa permanece en el escenario base.</p>`;
  }catch(e){node.textContent='No se pudo completar la auditoría de calidad: '+e.message;}
  finally{button.disabled=false;button.textContent='Repetir comparación de seis escenarios';}
}

function exportDay(){if(!state.lastFeatures.length){toast('No hay datos visibles para exportar.');return}
 const records=state.lastFeatures;const keys=[...new Set(records.flatMap(Object.keys))];
 const lines=[keys.join(','),...records.map(row=>keys.map(k=>{let v=String(row[k]??'');return '"'+v.replaceAll('"','""')+'"'}).join(','))];
 const blob=new Blob(['\uFEFF'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);
 const a=document.createElement('a');a.href=url;a.download=`nodara_${state.profile.region.replace(/\s+/g,'_')}_${selectedDate()}_${state.mode}.csv`;
 a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Se exportaron los datos visibles del día.');}
function searchPlace(){const text=$('#searchPlace').value.trim();if(!text)return;
 const xy=text.match(/^\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*$/);
 if(xy){const lat=Number(xy[1]),lon=Number(xy[2]);if(Math.abs(lat)>90||Math.abs(lon)>180){toast('Coordenadas fuera de rango.');return}
   if(state.leaflet){state.leaflet.setView([lat,lon],10);if(state.searchPin)state.leaflet.removeLayer(state.searchPin);
     state.searchPin=L.marker([lat,lon]).addTo(state.leaflet).bindPopup(`<b>Ubicación consultada</b><br>${lat.toFixed(5)}, ${lon.toFixed(5)}`).openPopup()}
   else toast('Ubicación: '+lat+', '+lon+' (sin cartografía conectada)');return;
 }
 const matching=state.datasets.find(d=>d.region.toLowerCase().includes(text.toLowerCase()));
 if(matching){$('#datasetSelect').value=matching.id;loadProfile(matching.id);return}
 toast('Región no disponible. Selecciona un conjunto procesado o escribe latitud, longitud.');}
function helpModal(){
 let dialog=$('#methodDialog');if(!dialog){dialog=document.createElement('dialog');dialog.id='methodDialog';
 dialog.style.cssText='max-width:580px;width:90vw;border:none;border-radius:14px;padding:26px;box-shadow:0 12px 50px #0006;color:#243747;font:14px/1.6 Segoe UI';
 dialog.innerHTML=`<h2>Metodología de Nodara Tech</h2>
 <p><b>Datos de origen:</b> registros públicos NASA FIRMS MODIS y VIIRS S-NPP / NOAA-20. Se conservan las temperaturas, FRP y confianza originales de cada sensor.</p>
 <p><b>Armonización exploratoria:</b> la v3 asigna centros de detecciones a cuadrículas v2 o hexágonos H3 r7 (opcional) y cuenta una celda-día activa una sola vez. Analiza posibles parejas de pasadas cercanas en espacio y tiempo y compara FRP agregado.</p>
 <p><b>Niveles de concordancia:</b> distinguimos «ambos en la misma celda-día» de «ambos con al menos una pareja candidata de pasada cercana», usando 30 minutos por defecto y filtros espaciales v2. H3 compara pasadas en la misma celda y celdas vecinas, exigiendo también distancia de huellas aproximada y la ventana seleccionada. El resultado sigue siendo exploratorio.</p>
 <p><b>Auditoría de calidad v3.6:</b> los escenarios conservan por separado las escalas originales MODIS y VIIRS, reagrupan pasadas y comparan pares; los filtros no miden probabilidad de incendio ni precisión.</p>
 <p><b>Limitaciones:</b> una celda-día no es un incendio; ni los hexágonos, ni la cuadrícula ni las coordenadas centrales delimitan superficie quemada. Las relaciones entre sensores <b>no están calibradas históricamente</b> ni corregidas completamente por cobertura y nubosidad.</p>
 <p><b>Fuentes:</b> <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank">NASA FIRMS</a> · <a href="https://nasa-gibs.github.io/gibs-api-docs/" target="_blank">NASA GIBS</a> · <a href="https://github.com/nasa-gibs/worldview" target="_blank">Worldview (referencia de UX)</a>.</p>
 <form method="dialog"><button style="background:#16384d;color:white;border:0;padding:10px 22px;border-radius:8px;cursor:pointer">Cerrar</button></form>`;
 document.body.appendChild(dialog)}dialog.showModal();}
async function initStates(){try{$('#processState').innerHTML=(await jsonFetch('/api/estados')).map(s=>`<option value="${esc(s)}" ${s==='California'?'selected':''}>${esc(s)}</option>`).join('')}catch{}}
let taskWatcher=null;
async function pollTask(){try{const d=await jsonFetch('/api/tarea');
 $('#processStatus').textContent=d.status==='ejecutando'?`Procesando ${d.estado}: ${d.anios}…`:d.status==='completado'?`Proceso completado para ${d.estado}.`:d.status==='error'?'El procesamiento terminó con error. Revisa el registro.':'No hay procesamiento activo.';
 $('#processLog').hidden=!d.log;$('#processLog').textContent=d.log;
 if(d.status==='ejecutando'){$('#processBtn').disabled=true;return}
 $('#processBtn').disabled=false;if(taskWatcher){clearInterval(taskWatcher);taskWatcher=null}
 if(d.status==='completado'){
   await loadCatalog(true);
   const newest=state.datasets.filter(x=>x.region===d.estado).sort((a,b)=>b.year-a.year)[0];
   if(newest){$('#datasetSelect').value=newest.id;await loadProfile(newest.id);toast('Datos nuevos disponibles: '+d.estado)}
   else toast('Proceso finalizado, pero no aparece el conjunto '+d.estado+'. Consulta el diagnóstico.');
 }
 }catch(e){console.error(e)}}
async function processState(){try{
 const estado=$('#processState').value,anios=$('#processYears').value.trim();
 if(!anios){toast('Indica los años.');return}
 await jsonFetch('/api/procesar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({estado,anios})});
 $('#processBtn').disabled=true;$('#processDetails').open=true;toast('Iniciada la descarga automática y el análisis. Puede tomar bastante tiempo.');
 if(taskWatcher)clearInterval(taskWatcher);taskWatcher=setInterval(pollTask,2000);pollTask();
 }catch(err){toast('No se pudo iniciar: '+err.message)}}
function bindUI(){
 $('#datasetSelect').addEventListener('change',e=>loadProfile(e.target.value));
 $('#spatialMethod').addEventListener('change',e=>changeSpatialMethod(e.target.value));
 $('#temporalWindow').addEventListener('change',e=>{state.temporalWindow=Number(e.target.value);$('#spatialAudit').textContent='La ventana cambió: ejecuta la auditoría para esta ventana.';$('#qualityAudit').textContent='La ventana cambió: vuelve a comparar los escenarios de calidad.';refreshMap();toast('Analizando pasadas con ventana de '+state.temporalWindow+' minutos.');});
 $('#toggleGeometry').addEventListener('click',()=>changeSpatialMethod(state.spatialMethod==='h3'?'square':'h3'));
 $$('#menuBtn').forEach(el=>el.addEventListener('click',()=>$('#sidebar').classList.toggle('open')));
 $$('#searchBtn').forEach(el=>el.addEventListener('click',searchPlace));
 $('#searchPlace').addEventListener('keydown',e=>{if(e.key==='Enter')searchPlace()});
 $$('[data-mode]').forEach(el=>el.addEventListener('click',()=>setMode(el.dataset.mode)));
 $$('[data-base]').forEach(el=>el.addEventListener('click',()=>setBase(el.dataset.base)));
 $$('.sensorCheck').forEach(el=>el.addEventListener('change',refreshMap));
 $('#daynight').addEventListener('change',refreshMap);$('#type0').addEventListener('change',refreshMap);
 $('#daySlider').addEventListener('input',e=>selectIndex(Number(e.target.value)));
 $('#dateInput').addEventListener('change',e=>{const i=state.dates.indexOf(e.target.value);if(i>=0)selectIndex(i)});
 $('#prevDay').addEventListener('click',()=>stepDay(-1));$('#nextDay').addEventListener('click',()=>stepDay(1));
 $('#playDay').addEventListener('click',()=>{if(state.playTimer){clearInterval(state.playTimer);state.playTimer=null;$('#playDay').textContent='▶'}else{
  state.playTimer=setInterval(()=>stepDay(1),1100);$('#playDay').textContent='Ⅱ'}});
 $('#resetMap').addEventListener('click',()=>{if(state.leaflet&&state.profile)state.leaflet.setView(state.profile.center,state.profile.zoom)});
 $('#exportCsv').addEventListener('click',exportDay);$('#openSources').addEventListener('click',helpModal);
 $('#processBtn').addEventListener('click',processState);
 $('#runSpatialAudit').addEventListener('click',runSpatialAudit);
 $('#runQualityAudit').addEventListener('click',runQualityAudit);
}
(async()=>{setupMap();bindUI();initStates();try{await loadCatalog(false)}catch(e){toast('Error al consultar el catálogo local: '+e.message)}
 if(!window.L)window.addEventListener('resize',()=>state.lastFeatures&&renderFallback(state.lastFeatures));
})();
