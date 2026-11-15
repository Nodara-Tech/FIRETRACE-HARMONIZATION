"""API de vista FIRETRACE sobre los indices originales de Nodara v3.6.

No altera datos ni la armonizacion; la agregacion por intervalo solo describe detecciones.
Los conteos de celdas se recalculan con los filtros seleccionados usando geometria
cuadrada v2 o H3 r7. Las parejas cientificas v3.6 siguen en el observatorio avanzado.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date, timedelta
from contextlib import closing
import math, sqlite3, random

EARTH_KM=6371.0088
COS_STD=math.cos(math.radians(30.0))
ALLOWED={'modis','viirs-snpp','viirs-jpss1'}

def _grid(lat,lon,km):
    px=EARTH_KM*COS_STD*math.radians(lon)
    py=EARTH_KM*math.sin(math.radians(lat))/COS_STD
    return (math.floor(px/km),math.floor(py/km))

def _inverse(x,y,km):
    lat=math.degrees(math.asin(max(-1,min(1,y*km*COS_STD/EARTH_KM))))
    lon=math.degrees(x*km/(EARTH_KM*COS_STD))
    return [round(lat,6),round(lon,6)]

def _haversine(a,b,c,d):
    ra,rb,rc,rd=map(math.radians,(a,b,c,d))
    x=math.sin((rc-ra)/2)**2+math.cos(ra)*math.cos(rc)*math.sin((rd-rb)/2)**2
    return 2*EARTH_KM*math.asin(min(1,math.sqrt(x)))

def _ymd(raw):
    if len(raw)!=10: raise ValueError('La fecha debe ser YYYY-MM-DD')
    return date.fromisoformat(raw)

def _real_range(d,opts,index_provider):
    year=d['year']; start=_ymd(opts.get('desde', f'{year}-01-01')); end=_ymd(opts.get('hasta',f'{year}-12-31'))
    if start>end:raise ValueError('La fecha inicial no puede superar a la final')
    if start.year!=year or end.year!=year:raise ValueError('El período debe estar dentro del año del conjunto seleccionado')
    if (end-start).days>366:raise ValueError('Selecciona un intervalo de hasta un año')
    sources=[x for x in opts.get('fuentes','modis,viirs-snpp,viirs-jpss1').split(',') if x in ALLOWED]
    method=opts.get('metodo','square')
    if method not in ('square','h3'):raise ValueError('Método espacial inválido')
    mode=opts.get('modo','points')
    if mode not in ('points','cells'):raise ValueError('Modo de mapa inválido')
    dn=opts.get('dia_noche','ambos')
    if dn not in ('ambos','D','N'):raise ValueError('Período del día inválido')
    type0=opts.get('solo_vegetacion','1')!='0'
    km=2.
    import json
    diag=d['folder']/'diagnostico_v2.json'
    if diag.exists():
        params=json.loads(diag.read_text(encoding='utf-8-sig')).get('parameters',{})
        if params.get('grid_km'):km=float(params['grid_km'])
    try:limit=max(50,min(3200,int(opts.get('limite','1500'))))
    except ValueError:limit=1500
    center=None
    if opts.get('lat') and opts.get('lon'):
        try:
            a,b=float(opts['lat']),float(opts['lon'])
            if not(-90<=a<=90 and -180<=b<=180):raise ValueError()
            radius=max(1,min(500,float(opts.get('radio','80'))))
            center=(a,b,radius)
        except ValueError:raise ValueError('Coordenadas o radio inválidos')
    db=index_provider(d)
    days={}
    cur=start
    while cur<=end:
        key=cur.isoformat()
        days[key]={'date':key,'total':0,'modis':0,'viirs':0,'snpp':0,'noaa20':0,
                   'cell_days':0,'both_cell_days':0}
        cur+=timedelta(days=1)
    memberships={}
    spatial_totals={}
    sample=[]; points_count=0
    rng=random.Random(47918)
    sources_clause=','.join('?' for _ in sources)
    # Sin fuentes, el mapa y las metricas deben ser cero, no mostrar fuentes ocultas.
    if sources:
        where='date BETWEEN ? AND ? AND source IN ('+sources_clause+')'
        args=[start.isoformat(),end.isoformat(),*sources]
        if type0:where+=" AND typ='0'"
        if dn!='ambos':where+=' AND daynight=?';args.append(dn)
        if center:
            lat,lon,radius=center
            dlat=radius/111.2; dlon=radius/max(15.,111.2*math.cos(math.radians(lat)))
            where+=' AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?'
            args.extend([lat-dlat,lat+dlat,lon-dlon,lon+dlon])
        q='SELECT date,lat,lon,source,platform,time,frp,confidence,daynight,scan,track FROM points WHERE '+where+' ORDER BY date'
        if method=='h3':
            try:import h3
            except ImportError:raise RuntimeError('H3 no está instalado. Ejecuta pip install -r requirements.txt')
        with closing(sqlite3.connect(db)) as con:
            for dt,lat,lon,src,platform,tm,frp,confidence,daynight,scan,track in con.execute(q,args):
                if center and _haversine(lat,lon,center[0],center[1])>center[2]:continue
                points_count+=1
                family=1 if src=='modis' else 2
                if src=='modis':field='modis'
                elif src=='viirs-snpp':field='snpp'
                else:field='noaa20'
                daily=days[dt];daily['total']+=1;daily[field]+=1
                if family==2:daily['viirs']+=1
                cell=h3.latlng_to_cell(lat,lon,7) if method=='h3' else _grid(lat,lon,km)
                key=(dt,cell)
                memberships[key]=memberships.get(key,0)|family
                old=spatial_totals.get(cell)
                if old is None:spatial_totals[cell]=[1,family,frp or 0.0,lat,lon]
                else:old[0]+=1;old[1]|=family;old[2]+=frp or 0.0
                # Uniform reservoir sampling to avoid biasing maps toward early days.
                if mode=='points':
                    pt={'lat':round(lat,6),'lon':round(lon,6),'source':src,'platform':platform,
                        'date':dt,'time':tm,'frp':frp,'confidence':confidence,'daynight':daynight,
                        'scan':scan,'track':track}
                    if len(sample)<limit:sample.append(pt)
                    else:
                        j=rng.randrange(points_count)
                        if j<limit:sample[j]=pt
    both_cell_days=0
    for (dt,cell),mask in memberships.items():
        days[dt]['cell_days']+=1
        if mask==3:
            days[dt]['both_cell_days']+=1
            both_cell_days+=1
    multisource_cells=sum(1 for cell,v in spatial_totals.items() if v[1]==3)
    all_cell_days=len(memberships)
    active_days=sum(1 for item in days.values() if item['total']>0)
    if mode=='cells':
        # Prefer strongest observed cells across the interval; no polygon is fire perimeter.
        ranked=sorted(spatial_totals.items(),key=lambda kv:kv[1][0],reverse=True)[:limit]
        for cell,(count,mask,frp,lat,lon) in ranked:
            if method=='h3':
                coords=[list(p) for p in h3.cell_to_boundary(cell)]
            else:
                x,y=cell;coords=[_inverse(x,y,km),_inverse(x+1,y,km),_inverse(x+1,y+1,km),_inverse(x,y+1,km)]
            sample.append({'lat':lat,'lon':lon,'polygon':coords,'total':count,'frp':round(frp,2),
                           'category':'ambos' if mask==3 else ('solo_modis' if mask==1 else 'solo_viirs')})
        sample_count=len(sample)
        total_features=len(spatial_totals)
    else:
        sample_count=len(sample)
        total_features=points_count
    # 'multi-source' es celda espacial unica durante el rango; no numero de incendios.
    return {'dataset':{'id':d['id'],'region':d['region'],'year':year},
            'range':{'from':start.isoformat(),'to':end.isoformat(),'days':len(days)},
            'method':method,'mode':mode,'filters':{'sources':sources,'daynight':dn,'type0':type0,'center':center},
            'summary':{'detections':points_count,'multisource_cells':multisource_cells,
                       'cell_days':all_cell_days,'both_cell_days':both_cell_days,
                       'cooccurrence_pct':round(100*both_cell_days/all_cell_days,2) if all_cell_days else 0,
                       'active_days':active_days,'spatial_cells':len(spatial_totals)},
            'daily':list(days.values()),'features':sample,
            'limited':sample_count<total_features,'total_features':total_features,
            'notice':'La actividad se cuantifica por registros y celdas; no representa incendios individuales ni superficie quemada. La coocurrencia es una fraccion descriptiva, no confianza estadistica.'}

def build_range(d,opts,index_provider):
    return _real_range(d,opts,index_provider)
