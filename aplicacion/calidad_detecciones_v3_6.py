"""Nodara Tech v3.6 · Auditoría de sensibilidad a calidad MODIS/VIIRS.

NO equipara MODIS 0–100 con VIIRS l/n/h; NO calcula probabilidad,
exactitud, sensibilidad ni especificidad científica. Compara seis escenarios
predefinidos, filtrando los registros ANTES de reconstruir pasadas y parejas.
Los mismos registros type=0 y métodos originales se aplican a todos.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from threading import RLock

from armonizar_firms_v2 import grid_id, make_passes, paired_passes, presence
from sensibilidad_temporal_v3_3 import records_from_normalized, WINDOWS
from emparejamiento_h3_v3_4 import build_passes_h3, candidate_pairs_h3, assign_pairs
from espacial_h3_v3 import h3_api

VERSION='3.6-P5-QUALITY-2'
OUT_FOLDER='calidad_detecciones_v3_6'
H3_LEVEL=7
LOCK=RLock()
SCENARIOS={
 'todas':('Sin filtro de confianza', None,False),
 'viirs_nh':('VIIRS nominal/alta',None,True),
 'modis50':('MODIS >=50',50,False),
 'ambos50':('MODIS >=50 + VIIRS n/h',50,True),
 'modis80':('MODIS >=80',80,False),
 'ambos80':('MODIS >=80 + VIIRS n/h',80,True),
}


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        yield from csv.DictReader(f)


def write_rows(path,rows,columns):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore')
        w.writeheader();w.writerows(rows)


def status(rec):
    """Clasificación original sin traducir VIIRS a probabilidades MODIS."""
    s=str(rec['confidence']).strip().lower()
    if rec['family']=='VIIRS':
        return s if s in ('l','n','h') else 'desconocida'
    try:
        n=float(s)
        return n if math.isfinite(n) and 0<=n<=100 else None
    except (ValueError,TypeError):
        return None


def accept(rec,scenario):
    if scenario not in SCENARIOS:
        raise ValueError('Escenario de calidad no permitido')
    threshold,exclude_low=SCENARIOS[scenario][1:]
    if rec['family']=='VIIRS' and exclude_low:
        return status(rec) in ('n','h')
    if rec['family']=='MODIS' and threshold is not None:
        v=status(rec)
        return isinstance(v,(float,int)) and v>=threshold
    return True


def quality_distribution(records):
    quality=defaultdict(Counter)
    for r in records:
        q=status(r)
        if r['family']=='MODIS':
            cat=('sin_valor_valido' if q is None else '<30' if q<30 else '30-49' if q<50 else '50-79' if q<80 else '80-100')
        else:
            cat=q
        quality[r['source']][str(cat)]+=1
    return dict(quality)


def quality_distribution_by_period(records):
    counts=defaultdict(Counter)
    for r in records:
        q=status(r)
        counts[f"{r['source']}:{r['daynight']}"][str(q)]+=1
    return dict(counts)


def presence_h3(records,h3):
    groups=defaultdict(lambda: {'modis':0,'viirs-snpp':0,'viirs-jpss1':0})
    for r in records:
        c=h3.latlng_to_cell(r['lat'],r['lon'],H3_LEVEL)
        groups[(r['dt'].date().isoformat(),c)][r['source']]+=1
    return groups


def counts_and_daily(groups,pairs,method,window,year):
    cat={}; byday=defaultdict(Counter)
    for (day,cell), counts in groups.items():
        m=counts['modis']>0;v=counts['viirs-snpp']+counts['viirs-jpss1']>0
        c='ambos' if m and v else 'solo_modis' if m else 'solo_viirs'
        cellkey=f'{cell[0]}_{cell[1]}' if method=='square' else cell
        cat[day,cellkey]=c
        byday[day]['celdas']+=1;byday[day][c]+=1
    close=set(); day_pairs=Counter(); intra=inter=0
    for p in pairs:
        day=p['fecha_utc'] if method=='h3' else str(p['fecha_modis_utc'])[:10]
        day_pairs[day]+=1
        if method=='h3':
            cm,cv=p['celda_h3_modis'],p['celda_h3_viirs']
            if cm==cv:intra+=1
            else:inter+=1
            for c in (cm,cv):
                if cat.get((day,c))=='ambos': close.add((day,c))
        else:
            if str(p['fecha_viirs_utc'])[:10]!=day:continue
            c=p['celda']
            if cat.get((day,c))=='ambos': close.add((day,c))
    for d,_ in close:byday[d]['con_pareja']+=1
    total=Counter(cat.values())
    start=date(year,1,1);end=date(year+1,1,1)
    daily=[]
    while start<end:
        day=start.isoformat();v=byday[day]
        daily.append({'fecha_utc':day,'metodo':method,'ventana_min':window,
          'celdas_activas':v['celdas'],'ambos':v['ambos'],'solo_modis':v['solo_modis'],
          'solo_viirs':v['solo_viirs'],'ambos_con_pareja':v['con_pareja'],
          'ambos_solo_fecha':v['ambos']-v['con_pareja'],'parejas':day_pairs[day]})
        start+=timedelta(days=1)
    return {'celdas_activas':len(cat),'ambos':total['ambos'],
        'solo_modis':total['solo_modis'],'solo_viirs':total['solo_viirs'],
        'ambos_con_pareja':len(close),'ambos_solo_fecha':total['ambos']-len(close),
        'parejas':len(pairs),'pares_misma_celda':intra if method=='h3' else len(pairs),
        'pares_vecinos':inter},daily


def scenario_run(records,scenario,grid,h3,window,year):
    filtered=[r for r in records if accept(r,scenario)]
    assert all(accept(r,scenario) for r in filtered)
    byfamily=Counter(r['family'] for r in filtered)
    bysource=Counter(r['source'] for r in filtered)
    groups_square=presence(filtered,grid)
    # presence() usa 'date' y no crea registros vacíos.
    square_passes=make_passes(filtered,grid)
    square_pairs=paired_passes(square_passes,window)
    square_summary,square_daily=counts_and_daily(groups_square,square_pairs,'square',window,year)
    groups_h3=presence_h3(filtered,h3)
    h3_passes=build_passes_h3(filtered,h3,H3_LEVEL)
    h3_pairs=assign_pairs(candidate_pairs_h3(h3_passes,h3,maximum_minutes=window),window)
    h3_summary,h3_daily=counts_and_daily(groups_h3,h3_pairs,'h3',window,year)
    assert square_summary['parejas']==len(square_pairs)
    assert h3_summary['parejas']==len(h3_pairs)
    assert all(item['ambos_con_pareja']<=item['ambos'] for item in (square_summary,h3_summary))
    return {'escenario':scenario,'etiqueta':SCENARIOS[scenario][0],
        'registros_type0':len(filtered),'registros_modis':byfamily['MODIS'],
        'registros_viirs':byfamily['VIIRS'],'por_fuente':dict(bysource),
        'cuadricula':square_summary,'h3':h3_summary}, [
             {**r,'escenario':scenario} for r in square_daily+h3_daily]


def fingerprint(src,diag,window,h3):
    return hashlib.sha256(repr((VERSION,window,str(getattr(h3,'__version__','H3-4.x')),
       tuple((p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in (src,diag)))).encode()).hexdigest()[:22]


def build(folder,*,window=30,force=False,h3_lib=None):
    folder=Path(folder).resolve();window=int(window)
    if window not in WINDOWS:raise ValueError('Ventana permitida: 15,30,60,120')
    src=folder/'registros_normalizados_v2.csv'; diagpath=folder/'diagnostico_v2.json'
    if not (src.is_file() and diagpath.is_file()):raise FileNotFoundError('Faltan CSV normalizado o diagnóstico v2')
    h3=h3_lib if h3_lib is not None else h3_api()
    sig=fingerprint(src,diagpath,window,h3)
    out=folder/OUT_FOLDER/f't_{window}min'
    manifest=out/'diagnostico_calidad.json'
    expected=(out/'escenarios_calidad.csv',out/'calendario_calidad.csv',manifest)
    with LOCK:
        if not force and all(f.is_file() for f in expected):
            try:
                data=json.loads(manifest.read_text(encoding='utf-8'))
                if data.get('signature')==sig:return out,data
            except (OSError,ValueError):pass
        v2diag=json.loads(diagpath.read_text(encoding='utf-8-sig'))
        grid=float(v2diag.get('parameters',{}).get('grid_km',2.0))
        year=int(v2diag.get('anio') or str(src.parent.name))
        # IMPORTANTE: los CSV normalizados incluyen todos los registros validados.
        # El universo fijo de auditoría es SOLO type=0; nunca mezclar tipos.
        records=records_from_normalized(folder,'todas')
        distribution=quality_distribution(records)
        distribution_dn=quality_distribution_by_period(records)
        results=[];all_daily=[]
        for scenario in SCENARIOS:
            result,daily=scenario_run(records,scenario,grid,h3,window,year)
            results.append(result);all_daily.extend(daily)
        base=results[0]
        for r in results:
            r['retencion_registros_pct']=round(100*r['registros_type0']/base['registros_type0'],2) if base['registros_type0'] else 0
            for method in ('cuadricula','h3'):
                bs=base[method];s=r[method]
                s['retencion_parejas_pct']=round(100*s['parejas']/bs['parejas'],2) if bs['parejas'] else None
                s['cambio_celdas_compartidas_pct']=round(100*(s['ambos']-bs['ambos'])/bs['ambos'],2) if bs['ambos'] else None
        # Comparar baseline con motores anteriores; si el v2 original ya tenía
        # filtro de confianza, el baseline analítico debe considerarse nuevo.
        previous=v2diag.get('parameters',{}).get('quality','todas')
        if previous=='todas' and window==int(v2diag.get('parameters',{}).get('pass_window_minutes',30)):
            original_pairs=int(v2diag.get('candidate_pairs',-1))
            if original_pairs!=-1 and base['cuadricula']['parejas']!=original_pairs:
                raise AssertionError(f'No reproduce parejas v2: {base["cuadricula"]["parejas"]} vs {original_pairs}')
        if previous=='todas':
            # H3 r7 baseline debe ser igual al P3 ya probado si biblioteca oficial.
            pass
        output={'version':VERSION,'signature':sig,'pais':v2diag.get('pais'),
          'anio':year,'ventana_min':window,'grid_km':grid,'h3_version':str(getattr(h3,'__version__','4.x')),
          'registros_validados_todos_los_tipos':int(v2diag.get('valid_total',0)),
          'registros_type0':len(records),'calidad_original_v2':previous,
          'calidad_por_fuente':distribution,'calidad_por_fuente_y_dia_noche':distribution_dn,'escenarios':results,
          'limitaciones':[
            'MODIS 0-100 no es probabilidad calibrada ni equivalente a VIIRS l/n/h.',
            'VIIRS alta h corresponde a saturación y no es necesariamente más exacta radiométricamente.',
            'Filtrar elimina observaciones y puede modificar pasadas/parejas; nunca inferir falsos positivos solo por descartar.',
            'Las variaciones de conteos NO estiman exactitud, sensibilidad ni especificidad.',
            'La selección type=0 es constante; diferencias de plataforma, horario y nubes persisten.',
            'La comparación es interna, no validación con verdad terreno; no asegura equivalencia histórica.',
            'Los porcentajes de retención son porcentajes de REGISTROS o PAREJAS, no confianza probabilística.',
            'Las parejas pueden reorganizarse al volver a agrupar las observaciones filtradas.'
          ]}
        out.mkdir(parents=True,exist_ok=True)
        flat=[]
        for r in results:
            for m,name in (('cuadricula','square'),('h3','h3')):
                s=r[m]
                flat.append({'escenario':r['escenario'],'etiqueta':r['etiqueta'],'metodo':name,
                    'ventana_min':window,'registros_type0':r['registros_type0'],
                    'registros_modis':r['registros_modis'],'registros_viirs':r['registros_viirs'],
                    'retencion_registros_pct':r['retencion_registros_pct'],**s})
        write_rows(expected[0],flat,list(flat[0]))
        write_rows(expected[1],all_daily,list(all_daily[0]))
        manifest.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        return out,output


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description='Nodara v3.6 sensibilidad a confianza MODIS-VIIRS')
    p.add_argument('--carpeta',type=Path,required=True)
    p.add_argument('--ventana',type=int,choices=WINDOWS,default=30)
    p.add_argument('--forzar',action='store_true')
    args=p.parse_args()
    folder,data=build(args.carpeta,window=args.ventana,force=args.forzar)
    print('P5 CORRECTO:',folder)
    for r in data['escenarios']:
        print(f"{r['escenario']:>10}  registros={r['registros_type0']:5}  "+
              f"cuadrados={r['cuadricula']['parejas']:4}  H3={r['h3']['parejas']:4}")
    print('ADVERTENCIA: calidad de sensor no equivale a probabilidad de incendio.')
