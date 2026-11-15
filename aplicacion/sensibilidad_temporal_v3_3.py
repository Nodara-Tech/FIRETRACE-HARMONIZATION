"""Nodara Tech v3.3: estudio de sensibilidad de la ventana temporal (P2).

Reutiliza sin modificar make_passes/paired_passes de armonizar_firms_v2.
Cuadrícula y filtros espaciales permanecen idénticos a la corrida base.
El valor 30 min NO queda validado como óptimo ni este análisis estima precisión.

Archivos adicionales por conjunto: sensibilidad_temporal_v3_3/*.
No altera los resultados originales v2, concordancia_v3_2 o H3.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from threading import Lock

from armonizar_firms_v2 import make_passes, paired_passes, csv_write

VERSION = '3.3-P2'
WINDOWS = (15, 30, 60, 120)
OUT_DIR = 'sensibilidad_temporal_v3_3'
BUILD_LOCK = Lock()


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def float_or_none(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def records_from_normalized(folder, quality):
    records=[]
    for r in read_rows(folder / 'registros_normalizados_v2.csv'):
        if r['type'] != '0':
            continue
        if quality == 'sin_l_viirs' and r['family'] == 'VIIRS' and r['confidence_original'] == 'l':
            continue
        dt=datetime.fromisoformat(r['date_utc'] + 'T' + r['time_utc'])
        rec={'lat':float(r['latitude']), 'lon':float(r['longitude']),
             'scan':float(r['scan_km']), 'track':float(r['track_km']),
             'date':dt.date(), 'dt':dt,
             'family':r['family'], 'platform':r['platform'], 'source':r['source'],
             'daynight':r['daynight'], 'confidence':r['confidence_original'],
             'frp':float_or_none(r.get('frp_mw')),
             'temp4':float_or_none(r.get('brightness_4um_k')),
             'temp11':float_or_none(r.get('brightness_11um_k'))}
        records.append(rec)
    return records


def bootstrap_day_fraction(daily_rows, *, n=500, seed=20261114):
    """Intervalo de estabilidad por remuestreo de días (no IC de exactitud)."""
    rng=random.Random(seed)
    vals=[(r['ambos_diarios'],r['ambos_paso_cercano']) for r in daily_rows if r['ambos_diarios']]
    if not vals:
        return None
    n_days=len(vals)
    estimates=[]
    for _ in range(n):
        selected=[vals[rng.randrange(n_days)] for _ in range(n_days)]
        denom=sum(x[0] for x in selected)
        if denom:
            estimates.append(sum(x[1] for x in selected)/denom)
    if not estimates:
        return None
    estimates.sort()
    return [round(estimates[int(.025*(len(estimates)-1))],4),
            round(estimates[int(.975*(len(estimates)-1))],4)]


def fingerprint(sources, *, params):
    return hashlib.sha256(repr((VERSION, params,
           [(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in sources])).encode('utf-8')).hexdigest()[:16]


def build(folder, force=False):
    folder=Path(folder).resolve()
    inputs=[folder/n for n in ('registros_normalizados_v2.csv','armonizacion_celdas_dia_v2.csv','diagnostico_v2.json','coincidencias_pasadas_frp.csv')]
    for f in inputs:
        if not f.is_file():
            raise FileNotFoundError(f'Falta fuente de resultados: {f}')
    diag=json.loads((folder/'diagnostico_v2.json').read_text(encoding='utf-8-sig'))
    params=diag.get('parameters',{})
    km=float(params.get('grid_km',2))
    quality=params.get('quality','todas')
    if quality not in ('todas','sin_l_viirs'):
        raise ValueError(f'Calidad no soportada: {quality}')
    sig=fingerprint(inputs,params=params)
    out=folder/OUT_DIR
    manifest_path=out/'diagnostico_sensibilidad.json'
    expected=[out/x for x in ('resumen_ventanas.csv','concordancia_ventanas_celdas.csv','concordancia_ventanas_diaria.csv','parejas_ventanas.csv','plataformas_ventanas.csv')]
    if not force and manifest_path.is_file() and all(p.is_file() for p in expected):
        try:
            d=json.loads(manifest_path.read_text(encoding='utf-8'))
            if d.get('signature')==sig:
                return out,d
        except (ValueError,OSError):pass
    with BUILD_LOCK:
        if not force and manifest_path.is_file() and all(p.is_file() for p in expected):
            try:
                d=json.loads(manifest_path.read_text(encoding='utf-8'))
                if d.get('signature')==sig: return out,d
            except (ValueError,OSError):pass
        cells={(r['fecha_utc'],r['celda']):r for r in read_rows(inputs[1])}
        cells_both={k for k,v in cells.items() if v['clasificacion']=='ambos'}
        days=sorted({k[0] for k in cells})
        date_both=Counter(day for day,_ in cells_both)
        obs=records_from_normalized(folder,quality)
        passes=make_passes(obs,km)
        summary=[];daily_rows=[];cell_rows=[];pair_rows=[];platform_rows=[]
        near_by_window={}
        pair_count_by_window={}
        for window in WINDOWS:
            pairs=paired_passes(passes,window)
            near=Counter()
            pair_by_day=Counter()
            platform_stats=defaultdict(list)
            outside=Counter()
            for p in pairs:
                m=datetime.fromisoformat(p['fecha_modis_utc'].removesuffix('Z'))
                v=datetime.fromisoformat(p['fecha_viirs_utc'].removesuffix('Z'))
                delta=abs((m-v).total_seconds())/60
                if delta>window+1e-8:
                    raise AssertionError('Pareja que excede la ventana solicitada')
                same_day=m.date()==v.date()
                key=(m.date().isoformat(),p['celda'])
                if not same_day:
                    outside['cruza_medianoche']+=1
                elif key not in cells_both:
                    outside['no_corresponde_a_ambos']+=1
                else:
                    near[key]+=1
                    pair_by_day[m.date().isoformat()]+=1
                platform_stats[(p['plataforma_modis'],p['plataforma_viirs'],p['dia_noche'])].append(delta)
                pair_rows.append({**p,'ventana_min':window, 'vinculado_a_celda_dia':int(same_day and key in cells_both)})
            near_by_window[window]=near
            pair_count_by_window[window]=len(pairs)
            for (mp,vp,dn),deltas in sorted(platform_stats.items()):
                platform_rows.append({'ventana_min':window,'modis':mp,'viirs':vp,'dia_noche':dn,
                     'n_pares':len(deltas),'mediana_delta_min':round(statistics.median(deltas),2),
                     'min_delta_min':round(min(deltas),2),'max_delta_min':round(max(deltas),2)})
            day_counts=[]
            for day in days:
                both=date_both[day]
                near_n=sum(bool(n) for (d,c),n in near.items() if d==day)
                # Este criterio conserva el significado de P1: celda-día, no parejas.
                day_counts.append({'fecha_utc':day,'ambos_diarios':both,
                     'ambos_paso_cercano':near_n,'ambos_solo_dia':both-near_n})
                daily_rows.append({'ventana_min':window,'fecha_utc':day,
                     'ambos_diarios':both,'ambos_paso_cercano':near_n,
                     'ambos_solo_dia':both-near_n,'parejas_candidatas_dia':pair_by_day[day]})
            for key in sorted(cells_both):
                count=near[key]
                cell_rows.append({'ventana_min':window,'fecha_utc':key[0],'celda':key[1],
                     'nivel_concordancia':'ambos_paso_cercano' if count else 'ambos_solo_dia',
                     'parejas_pasada_cercana':count})
            n_near=sum(1 for k in cells_both if near[k])
            if n_near>len(cells_both):raise AssertionError('Más celdas próximas que diarias')
            ci=bootstrap_day_fraction(day_counts,seed=20261114+window)
            summary.append({'ventana_min':window,
                 'parejas_candidatas':len(pairs), 'parejas_vinculadas_celda_dia':sum(near.values()),
                 'celdas_dia_ambos':len(cells_both),'celdas_con_pareja':n_near,
                 'celdas_solo_dia':len(cells_both)-n_near,
                 'proporcion_con_pareja':round(n_near/len(cells_both),4) if cells_both else 0,
                 'ic_bootstrap_dias_inf':ci[0] if ci else '',
                 'ic_bootstrap_dias_sup':ci[1] if ci else '',
                 'parejas_cruzan_medianoche':outside['cruza_medianoche'],
                 'advertencia':'No representa precisión ni probabilidad de incendio'})
        # Validación fuerte: ventana original debe reproducir exactamente la v2 y P1.
        v2_pairs=list(read_rows(inputs[3]))
        original=int(params.get('pass_window_minutes',30))
        if original in pair_count_by_window and len(v2_pairs)!=pair_count_by_window[original]:
            raise AssertionError('Regeneración temporal NO reproduce el número de parejas v2')
        from concordancia_v3_2 import build as p1_build,read_rows as p1_read
        p1folder,p1diag=p1_build(folder)
        base_window=int(params.get('pass_window_minutes',30))
        if base_window in near_by_window:
            p1_near=Counter({(r['fecha_utc'],r['celda']):int(r['parejas_pasada_cercana'])
                     for r in p1_read(p1folder/'concordancia_celdas_dia.csv') if r['clasificacion']=='ambos'})
            observed=near_by_window[base_window]
            if p1_near != observed:
                raise AssertionError(f'Conflicto P1 vs P2 en ventana original {base_window} min')
        for window1,window2 in zip(WINDOWS, WINDOWS[1:]):
            if not set(near_by_window[window1])<=set(near_by_window[window2]):
                raise AssertionError('Las celdas con pareja dejan de ser monótonas con la ventana')
        out.mkdir(parents=True,exist_ok=True)
        csv_write(out/'resumen_ventanas.csv',summary,list(summary[0]))
        csv_write(out/'concordancia_ventanas_celdas.csv',cell_rows,list(cell_rows[0]) if cell_rows else ['ventana_min','fecha_utc','celda','nivel_concordancia','parejas_pasada_cercana'])
        csv_write(out/'concordancia_ventanas_diaria.csv',daily_rows,list(daily_rows[0]) if daily_rows else ['ventana_min','fecha_utc','ambos_diarios','ambos_paso_cercano','ambos_solo_dia','parejas_candidatas_dia'])
        csv_write(out/'parejas_ventanas.csv',pair_rows,list(pair_rows[0]) if pair_rows else ['ventana_min']+list(v2_pairs[0]) if v2_pairs else ['ventana_min'])
        csv_write(out/'plataformas_ventanas.csv',platform_rows,list(platform_rows[0]) if platform_rows else ['ventana_min','modis','viirs','dia_noche','n_pares','mediana_delta_min','min_delta_min','max_delta_min'])
        manifest={'version':VERSION,'signature':sig,'parameters':{'grid_km':km,'quality':quality,'pass_span_min':params.get('pass_span_minutes',12)},
            'windows':list(WINDOWS),'summary':summary,'records_processed':len(obs),
            'nearby_source':'motor v2 / make_passes / paired_passes',
            'notes':['Mantiene filtros geométricos y reglas 1 a 1 por par de plataformas; solamente cambia el tope temporal.',
                '30 min es la referencia existente, NO un óptimo validado.',
                'Los intervalos bootstrap re-muestrean días; solo indican estabilidad interna, NO sensibilidad/especificidad.',
                'Solo analiza la cuadrícula v2; H3 temporal queda pendiente (P3).',
                'El tamaño de las ventanas altera la posibilidad de emparejar pasadas y NO la presencia diaria.',
                'Cruces entre medianoches UTC no clasifican como celdas-día con pareja cercana según P1.']}
        manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
        return out,manifest


def main():
    import argparse
    ap=argparse.ArgumentParser(description='Nodara v3.3 — problema 2: sensibilidad temporal MODIS–VIIRS')
    ap.add_argument('carpeta',type=Path)
    ap.add_argument('--recalcular',action='store_true')
    args=ap.parse_args()
    out,diag=build(args.carpeta,force=args.recalcular)
    print('Resultado:',out)
    for row in diag['summary']:
        print('{ventana_min:>3} min | pares {parejas_candidatas:>4} | celdas próximas {celdas_con_pareja:>4} | solo día {celdas_solo_dia:>4}'.format(**row))
    print('No se determina cuál ventana tiene mayor exactitud sin referencia independiente.')

if __name__=='__main__':main()
