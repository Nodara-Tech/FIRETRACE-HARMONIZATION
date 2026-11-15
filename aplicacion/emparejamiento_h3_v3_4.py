"""Nodara Tech v3.4 (P3): emparejamiento temporal H3 REAL.

Un punto se indexa con h3-py 4.x. Pasadas se agregan por H3+plataforma+
D/N+fecha UTC (máximo 12 minutos desde la primera muestra). Las parejas
pueden pertenecer a la misma celda o a un vecino inmediato (k=1), pero deben
cumplir simultáneamente: mismo día UTC, D/N, |delta tiempo|<= ventana y
separación de centroides <= 1/2 diagonal scan/track de ambos + 250 m.
Emparejamiento ávido 1:1 por par concreto de plataformas, GLOBAL por día:
no permite reutilizar una misma pasada en distintos hexágonos vecinos dentro
 del mismo par de plataformas. Los resultados NO confirman incendios únicos.

NO calibra FRP ni reemplaza la cuadrícula v2/v3.3. Usa la API oficial H3 4.x.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from threading import Lock

from espacial_h3_v3 import h3_api
from sensibilidad_temporal_v3_3 import WINDOWS, records_from_normalized
from armonizar_firms_v2 import PASS_SPAN_MIN, haversine

VERSION = '3.4-P3-H3'
OUT = 'emparejamiento_h3_v3_4'
BUILD_LOCK = Lock()


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def write_csv(path, rows, cols):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer=csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)


def build_passes_h3(records, h3, resolution=7):
    """Pasadas por centro de píxel; una detección pertenece a una celda."""
    groups=defaultdict(list)
    for rec in records:
        lat,lon=rec['lat'],rec['lon']
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        cell=h3.latlng_to_cell(lat,lon,resolution)
        groups[(rec['dt'].date().isoformat(),cell,rec['platform'],rec['daynight'])].append(rec)
    passes=[]
    for (day,cell,platform,dn), items in sorted(groups.items()):
        items.sort(key=lambda p:p['dt'])
        slices=[]
        for rec in items:
            if not slices or (rec['dt']-slices[-1][0]['dt']).total_seconds()>PASS_SPAN_MIN*60:
                slices.append([rec])
            else:
                slices[-1].append(rec)
        for chunk in slices:
            first,last=chunk[0]['dt'],chunk[-1]['dt']
            frps=[r['frp'] for r in chunk if r['frp'] is not None]
            t11=[r['temp11'] for r in chunk if r['temp11'] is not None]
            n=len(passes)+1
            passes.append({
                'id':f'H3P{n:07d}', 'day':day,'cell':cell,
                'platform':platform,'family':chunk[0]['family'],'daynight':dn,
                't':first+(last-first)/2,'n':len(chunk),
                'lat':sum(r['lat'] for r in chunk)/len(chunk),
                'lon':sum(r['lon'] for r in chunk)/len(chunk),
                'scan':max(r['scan'] for r in chunk),'track':max(r['track'] for r in chunk),
                'frp':sum(frps) if frps else None,
                'frp_missing':len(chunk)-len(frps),
                't11':sum(t11)/len(t11) if t11 else None,
            })
    return passes


def candidate_pairs_h3(passes, h3, maximum_minutes=120):
    """Genera candidatos únicos antes de la selección 1:1.

    No se aplica solo distancia de H3: la geometría/huella es obligatoria.
    El índice de búsqueda es (día, celda, plataforma, D/N).
    """
    by_cell=defaultdict(list)
    for p in passes:
        if p['family']=='VIIRS':
            by_cell[(p['day'],p['cell'],p['daynight'])].append(p)
    candidates=defaultdict(list)
    for m in passes:
        if m['family']!='MODIS':continue
        neighbors=set(h3.grid_disk(m['cell'],1))
        for target in neighbors:
            for v in by_cell.get((m['day'],target,m['daynight']),()):
                delta=abs((m['t']-v['t']).total_seconds())/60
                if delta>maximum_minutes:continue
                dist=haversine(m,v)
                # Centroides agregados: regla geométrica APROXIMADA, no solapamiento exacto.
                radius=.5*math.hypot(m['scan'],m['track'])+.5*math.hypot(v['scan'],v['track'])+.25
                if dist>radius:continue
                relation='misma_celda' if m['cell']==v['cell'] else 'vecinas'
                # Parejas por fecha + plataformas. Un mismo pase no se usa dos
                # veces dentro del par de plataformas aunque aparezca en vecinos.
                key=(m['day'],m['platform'],v['platform'])
                candidates[key].append((delta,dist,0 if relation=='misma_celda' else 1,m,v,radius,relation))
    for key, vals in candidates.items():
        vals.sort(key=lambda x:(x[0],x[1],x[2],x[3]['id'],x[4]['id']))
    return candidates


def assign_pairs(candidates, window):
    matches=[]
    for (day,mp,vp), values in sorted(candidates.items()):
        used_m,used_v=set(),set()
        for delta,dist,_,m,v,radius,relation in values:
            if delta>window: continue
            if m['id'] in used_m or v['id'] in used_v:continue
            used_m.add(m['id']);used_v.add(v['id'])
            ratio=(v['frp']/m['frp']) if m['frp'] and v['frp'] else None
            matches.append({
                'fecha_utc':day,'celda_h3_modis':m['cell'],'celda_h3_viirs':v['cell'],
                'relacion_h3':relation,'plataforma_modis':mp,'plataforma_viirs':vp,
                'id_paso_modis':m['id'],'id_paso_viirs':v['id'],
                'fecha_modis_utc':m['t'].isoformat()+'Z','fecha_viirs_utc':v['t'].isoformat()+'Z',
                'dia_noche':m['daynight'],'diferencia_min':round(delta,3),
                'distancia_centroides_km':round(dist,5),'umbral_huella_aprox_km':round(radius,5),
                'lat':round((m['lat']+v['lat'])/2,7),'lon':round((m['lon']+v['lon'])/2,7),
                'lat_modis':round(m['lat'],7),'lon_modis':round(m['lon'],7),
                'lat_viirs':round(v['lat'],7),'lon_viirs':round(v['lon'],7),
                'n_pix_modis':m['n'],'n_pix_viirs':v['n'],
                'frp_modis_mw':m['frp'],'frp_viirs_mw':v['frp'],
                'frp_ratio_viirs_modis':round(ratio,5) if ratio is not None else '',
                't11_modis_media_k':m['t11'],'t11_viirs_media_k':v['t11'],
                'frp_faltante_pix_modis':m['frp_missing'], 'frp_faltante_pix_viirs':v['frp_missing'],
                'advertencia':'candidato_espacio_tiempo_no_confirma_incendio',
            })
    return matches


PAIR_FIELDS=['ventana_min','fecha_utc','celda_h3_modis','celda_h3_viirs','relacion_h3',
 'plataforma_modis','plataforma_viirs','id_paso_modis','id_paso_viirs',
 'fecha_modis_utc','fecha_viirs_utc','dia_noche','diferencia_min','distancia_centroides_km',
 'umbral_huella_aprox_km','lat','lon','lat_modis','lon_modis','lat_viirs','lon_viirs',
 'n_pix_modis','n_pix_viirs','frp_modis_mw','frp_viirs_mw','frp_ratio_viirs_modis',
 't11_modis_media_k','t11_viirs_media_k','frp_faltante_pix_modis','frp_faltante_pix_viirs','advertencia']
CELL_FIELDS=['ventana_min','fecha_utc','h3_id','clasificacion','nivel_concordancia',
             'parejas_misma_celda','parejas_vecinas','parejas_pasada_cercana']
DAILY_FIELDS=['ventana_min','fecha_utc','ambos_diarios','ambos_paso_cercano','ambos_misma_celda',
              'ambos_con_pareja_vecina','ambos_solo_dia','solo_modis_con_pareja_vecina',
              'solo_viirs_con_pareja_vecina','parejas_candidatas_dia','parejas_misma_celda',
              'parejas_vecinas']
SUMMARY_FIELDS=['ventana_min','parejas_candidatas','parejas_misma_celda','parejas_vecinas',
                'celdas_dia_ambos','celdas_con_pareja','celdas_solo_dia',
                'solo_modis_con_pareja_vecina','solo_viirs_con_pareja_vecina',
                'proporcion_con_pareja','aviso']


def classify_presence(presence, matches, window):
    """Clasifica cada celda H3, SIN fusionar vecinos como «ambos»."""
    within=Counter(); nearby=Counter()
    for pair in matches:
        day=pair['fecha_utc']; cm=pair['celda_h3_modis']; cv=pair['celda_h3_viirs']
        if cm==cv:within[day,cm]+=1
        else:
            nearby[day,cm]+=1;nearby[day,cv]+=1
    cell_rows=[];daily=defaultdict(Counter)
    for (day,cell),cat in sorted(presence.items()):
        same=within[day,cell];adj=nearby[day,cell]
        if cat=='ambos':
            level=('ambos_paso_cercano' if same or adj else 'ambos_solo_dia')
            exact=('ambos_misma_celda' if same else 'ambos_con_pareja_vecina' if adj else 'ambos_solo_dia')
            daily[day]['ambos_diarios']+=1;daily[day][exact]+=1
            if same or adj:daily[day]['ambos_paso_cercano']+=1
        elif cat=='solo_modis':
            level='solo_modis_vecino_cercano' if adj else 'solo_modis'
            if adj:daily[day]['solo_modis_con_pareja_vecina']+=1
        else:
            level='solo_viirs_vecino_cercano' if adj else 'solo_viirs'
            if adj:daily[day]['solo_viirs_con_pareja_vecina']+=1
        cell_rows.append({'ventana_min':window,'fecha_utc':day,'h3_id':cell,
                          'clasificacion':cat,'nivel_concordancia':level,
                          'parejas_misma_celda':same,'parejas_vecinas':adj,
                          'parejas_pasada_cercana':same+adj})
    for p in matches:
        c=daily[p['fecha_utc']]
        c['parejas_candidatas_dia']+=1
        c['parejas_misma_celda' if p['relacion_h3']=='misma_celda' else 'parejas_vecinas']+=1
    # Los pares dentro de un mismo H3 siempre deben corresponder a presencia «ambos».
    for pair in matches:
        a=(pair['fecha_utc'],pair['celda_h3_modis']);b=(pair['fecha_utc'],pair['celda_h3_viirs'])
        assert a in presence and b in presence
        if a==b:assert presence[a]=='ambos'
    daily_rows=[]
    for day, c in sorted(daily.items()):
        assert c['ambos_diarios']==c['ambos_misma_celda']+c['ambos_con_pareja_vecina']+c['ambos_solo_dia']
        daily_rows.append({'ventana_min':window,'fecha_utc':day,**{k:c[k] for k in DAILY_FIELDS[2:]}})
    return cell_rows,daily_rows


def source_signature(folder,resolution):
    files=[folder/'registros_normalizados_v2.csv',folder/'diagnostico_v2.json',
           folder/'espacial_h3_v3'/f'h3_r{resolution}'/'h3_celdas_dia.csv']
    for f in files:
        if not f.is_file(): raise FileNotFoundError(f'Falta archivo: {f}')
    return hashlib.sha256(repr((VERSION,resolution,PASS_SPAN_MIN,list(WINDOWS),
      [(f.name,f.stat().st_size,f.stat().st_mtime_ns) for f in files])).encode()).hexdigest()[:20]


def build(folder, resolution=7, force=False):
    folder=Path(folder).resolve();resolution=int(resolution)
    # H3 válido obligatorio: no ejecutar fallback o aproximación hexagonal.
    h3=h3_api()
    from espacial_h3_v3 import generate
    # generate cachea la agrupación diaria, respeta calidad del análisis v2.
    h3_folder,_=generate(folder,resolution=resolution)
    sig=source_signature(folder,resolution)
    dest=folder/OUT/f'h3_r{resolution}'
    manifest_file=dest/'diagnostico_emparejamiento_h3.json'
    required=['h3_parejas_ventanas.csv','h3_concordancia_celdas.csv',
              'h3_concordancia_diaria.csv','h3_resumen_ventanas.csv']
    def cached():
        if not force and manifest_file.exists() and all((dest/n).exists() for n in required):
            try:
                d=json.loads(manifest_file.read_text(encoding='utf-8'))
                if d.get('signature')==sig:return d
            except (OSError, ValueError):pass
        return None
    old=cached()
    if old:return dest,old
    with BUILD_LOCK:
        old=cached()
        if old:return dest,old
        meta=json.loads((folder/'diagnostico_v2.json').read_text(encoding='utf-8-sig'))
        quality=meta.get('parameters',{}).get('quality','todas')
        # No agregar registros de distinta calidad que los contados en H3 diario.
        records=records_from_normalized(folder,quality)
        presence={(r['fecha_utc'],r['h3_id']):r['clasificacion']
                  for r in read_csv(h3_folder/'h3_celdas_dia.csv')}
        passes=build_passes_h3(records,h3,resolution)
        candidates=candidate_pairs_h3(passes,h3,max(WINDOWS))
        all_pairs=[]; all_cells=[];all_days=[];summary=[]
        last_pair_count=0;last_cells=set()
        for window in WINDOWS:
            matches=assign_pairs(candidates,window)
            cell_rows,day_rows=classify_presence(presence,matches,window)
            all_pairs.extend({'ventana_min':window,**p} for p in matches)
            all_cells.extend(cell_rows);all_days.extend(day_rows)
            counts=Counter(p['relacion_h3'] for p in matches)
            both=sum(1 for cls in presence.values() if cls=='ambos')
            with_match=sum(r['clasificacion']=='ambos' and r['parejas_pasada_cercana']>0 for r in cell_rows)
            solo_modis_near=sum(r['nivel_concordancia']=='solo_modis_vecino_cercano' for r in cell_rows)
            solo_viirs_near=sum(r['nivel_concordancia']=='solo_viirs_vecino_cercano' for r in cell_rows)
            near_set={(r['fecha_utc'],r['h3_id']) for r in cell_rows
                      if r['clasificacion']=='ambos' and r['parejas_pasada_cercana']}
            assert len(matches)>=last_pair_count, 'Parejas H3 no monótonas al ampliar ventana'
            assert last_cells<=near_set, 'Celdas con parejas H3 no monótonas'
            assert with_match<=both
            last_pair_count=len(matches);last_cells=near_set
            summary.append({'ventana_min':window,'parejas_candidatas':len(matches),
                'parejas_misma_celda':counts['misma_celda'],'parejas_vecinas':counts['vecinas'],
                'celdas_dia_ambos':both,'celdas_con_pareja':with_match,
                'celdas_solo_dia':both-with_match,
                'solo_modis_con_pareja_vecina':solo_modis_near,
                'solo_viirs_con_pareja_vecina':solo_viirs_near,
                'proporcion_con_pareja':round(with_match/both,4) if both else 0,
                'aviso':'Candidatos exploratorios: cobertura y area distinta a cuadricula v2; NO equivalencia fisica'})
        dest.mkdir(parents=True,exist_ok=True)
        write_csv(dest/required[0],all_pairs,PAIR_FIELDS)
        write_csv(dest/required[1],all_cells,CELL_FIELDS)
        write_csv(dest/required[2],all_days,DAILY_FIELDS)
        write_csv(dest/required[3],summary,SUMMARY_FIELDS)
        manifest={'version':VERSION,'signature':sig,'h3_api':getattr(h3,'__version__','4.x'),
             'resolucion':resolution,'quality':quality,'records_used':len(records),
             'passes':len(passes),'celdas_dia':len(presence), 'windows':list(WINDOWS),
             'summary':summary,'criterios':{'vecindad_h3':1,'pases_agrupacion_min':PASS_SPAN_MIN,
                'mismo_dia_utc':True,'mismo_daynight':True,
                'distancia_aprox':'media diagonal scan/track ambos + 0.25km',
                'matching':'greedy 1:1 por dia y par concreto de plataformas; no optimizacion global'},
             'limitaciones':['Aproximaciones de huella, FRP y tiempo; no identifica incendios ni valida calibracion.',
                'H3 centro de pixel no representa area afectada ni huella real.',
                'Vecindad k=1 no garantiza cercania, se exige distancia de huellas.',
                'No se emparejan pases que crucen medianoche UTC; conserva interpretacion celda-dia.',
                'Una pasada puede pertenecer a varios pares distintos de plataformas.',
                'No equivale a la superficie de cuadrados 2x2 km ni a comparacion de sensibilidad/especificidad.']}
        manifest_file.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        return dest,manifest


def main():
    import argparse
    a=argparse.ArgumentParser(description='Nodara v3.4 H3 temporal real (P3)')
    a.add_argument('carpeta',type=Path)
    a.add_argument('--resolucion',type=int,default=7)
    a.add_argument('--recalcular',action='store_true')
    args=a.parse_args()
    p,d=build(args.carpeta,resolution=args.resolucion,force=args.recalcular)
    print('Archivos:',p)
    for r in d['summary']:
        print(f"{r['ventana_min']:>3} min: {r['parejas_candidatas']:>5} pares H3 "
              f"({r['parejas_misma_celda']} misma celda, {r['parejas_vecinas']} vecinas); "
              f"{r['celdas_con_pareja']} de {r['celdas_dia_ambos']} compartidas con pareja")
    print('Candidatos exploratorios: NO incendios confirmados.')


if __name__=='__main__':main()
