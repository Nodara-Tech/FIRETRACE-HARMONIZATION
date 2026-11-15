"""Nodara Tech — visor web histórico MODIS + VIIRS.

Inicio: py visor_incendios.py
Opcional: py visor_incendios.py --auto --estado California --anios 2024

No afirma incendios individuales, hectáreas quemadas ni equivalencia radiométrica.
Servidor local sin frameworks; NASA GIBS/OSM se consumen en el navegador.
"""
from __future__ import annotations

import argparse
import hashlib
import time
from contextlib import closing
from functools import lru_cache
import csv
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parent
STATIC = APP_DIR / "web"
PORT_DEFAULT = 8765
BASES = (ROOT / "resultados" / "resultados_estados_unidos", ROOT / "resultados" / "resultados_armonizacion_v2")
SERVER_LOCK = threading.Lock()
INDEX_LOCK = threading.Lock()
H3_LOCK = threading.Lock()
CONCORDANCE_LOCK = threading.Lock()
TEMPORAL_LOCK = threading.Lock()
H3_PAIR_LOCK = threading.Lock()
JOB = {"proc": None, "log": "", "status": "inactivo", "estado": "", "anios": ""}
EARTH_KM = 6371.0088
COS_STD = math.cos(math.radians(30.0))


def list_datasets():
    """Encuentra resultados normales y resultados anidados en escenarios/.

    El orquestador de EE. UU. guarda cada año en:
      resultados_estados_unidos/California/2024/escenarios/celda_5km_t_30min_todas/
    mientras los ejemplos históricos están en:
      resultados_armonizacion_v2/Costa_Rica/2024/
    """
    found = {}
    for base in BASES:
        if not base.exists():
            continue
        direct = sorted(base.glob('*/[12][0-9][0-9][0-9]/registros_normalizados_v2.csv'))
        nested = sorted(base.glob('*/[12][0-9][0-9][0-9]/escenarios/*/registros_normalizados_v2.csv'))
        for path in direct + nested:
            folder = path.parent
            year_dir = folder if folder.name.isdigit() else folder.parent.parent
            try:
                year = int(year_dir.name)
            except ValueError:
                continue
            region = year_dir.parent.name
            key = region + '__' + str(year)
            # Un dataset directo tiene prioridad frente a escenarios alternativos.
            if key in found:
                continue
            found[key] = {
                'id': key, 'region': region.replace('_', ' '),
                'year': year, 'folder': folder,
                'demo': base.name == 'resultados_armonizacion_v2'
            }
    return sorted(found.values(), key=lambda x: (x['region'].lower(), -x['year']))


def dataset_by_id(dataset_id):
    for d in list_datasets():
        if d['id'] == dataset_id:
            return d
    return None


def read_csv_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def to_float(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def to_int(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def data_center(lat, lon):
    return [lat, lon]


def bounds_for_region(region):
    lookup = {
        "Costa Rica": ([9.73, -84.2], 8),
        "Afghanistan": ([33.85, 66.1], 6),
        "California": ([36.5, -119.5], 6),
        "Texas": ([31.0, -99.0], 6),
        "Florida": ([27.8, -82.0], 7),
        "Alaska": ([63.0, -152.0], 4),
        "Hawaii": ([20.8, -157.1], 7),
        "Colorado": ([39.0, -105.6], 7),
        "Arizona": ([34.3, -111.9], 7),
        "Oregon": ([44.0, -120.6], 7),
        "Washington": ([47.4, -120.4], 7),
        "Montana": ([46.8, -110.7], 6),
        "New Mexico": ([34.4, -106.1], 7),
    }
    return lookup.get(region, ([39.0, -98.0], 5))


def h3_folder(d):
    """Genera resultados H3 después de leer la salida v2; cachea por firma."""
    from espacial_h3_v3 import generate
    with H3_LOCK:
        out, _ = generate(d['folder'], resolution=7)
    return out


def h3_daily_profile(d):
    folder = h3_folder(d)
    return (read_csv_rows(folder / 'h3_calendario_diario.csv'),
            read_csv_rows(folder / 'h3_calendario_mensual.csv'),
            json.loads((folder / 'manifiesto_v3.json').read_text(encoding='utf-8')))


def dataset_profile(d, method='square'):
    folder = d["folder"]
    if method == 'h3':
        days, months, hdiag = h3_daily_profile(d)
    else:
        days = read_csv_rows(folder / "calendario_diario_v2.csv")
        months = read_csv_rows(folder / "calendario_mensual_v2.csv")
        hdiag = None
    diag_path = folder / "diagnostico_v2.json"
    diagnostic = json.loads(diag_path.read_text(encoding="utf-8-sig")) if diag_path.exists() else {}
    filled = sorted(days, key=lambda x: to_int(x.get("celdas_activas_proxy")), reverse=True)
    selected = filled[0]['fecha_utc'] if filled else f'{d["year"]}-01-01'
    center, zoom = bounds_for_region(d['region'])
    return {
        "id": d["id"], "region": d["region"], "year": d["year"],
        "center": center, "zoom": zoom, "default_date": selected,
        "daily": [{"date": row.get("fecha_utc", ""),
                   "active": to_int(row.get("celdas_activas_proxy")),
                   "both": to_int(row.get("ambos")),
                   "only_modis": to_int(row.get("solo_modis")),
                   "only_viirs": to_int(row.get("solo_viirs"))} for row in days],
        "monthly": [{"month": row.get("mes_utc", ""),
                      "active": to_int(row.get("celdas_dia_activas_proxy")),
                      "both": to_int(row.get("ambos")),
                      "only_modis": to_int(row.get("solo_modis")),
                      "only_viirs": to_int(row.get("solo_viirs"))} for row in months],
        "diagnostic": {
            "valid_total": diagnostic.get("valid_total", 0),
            "candidate_pairs": diagnostic.get("candidate_pairs", 0),
            "grid_km": diagnostic.get("parameters", {}).get("grid_km", None),
            "h3_resolution": (hdiag.get('resolucion_h3') if hdiag else None),
            "h3_avg_area_km2": (hdiag.get('area_media_hexagono_km2') if hdiag else None),
            "input_counts": diagnostic.get("input_counts", {}),
            "cell_day": diagnostic.get("cell_day_proxy", {})
        },
        "demo": d["demo"], "spatial_method":method,
        "spatial_description": ("H3 resolución 7 (~5,16 km² por hexágono en promedio)" if method == "h3" else
                                f"Cuadrícula v2 ({diagnostic.get('parameters',{}).get('grid_km',2)} km por lado)"),
        "warning": "Detecciones y celdas-día exploratorias, no incendios ni área quemada. Sin corrección completa de cobertura/nubosidad."
    }


def concordance_file(d):
    """Genera solo la partición P1 sin tocar los resultados científicos v2/H3."""
    from concordancia_v3_2 import build
    with CONCORDANCE_LOCK:
        folder, manifest = build(d['folder'])
    return folder / 'concordancia_celdas_dia.csv'


def concordance_meta(d):
    concordance_file(d)
    f = d['folder'] / 'concordancia_v3_2' / 'diagnostico_concordancia.json'
    return json.loads(f.read_text(encoding='utf-8'))


def temporal_index(d):
    """Índice de solo lectura para las 4 ventanas; no modifica el SQLite v2/P1."""
    from sensibilidad_temporal_v3_3 import build
    with TEMPORAL_LOCK:
        out, manifest = build(d['folder'])
    return _temporal_index_cached(str(out), manifest['signature'])


@lru_cache(maxsize=6)
def _temporal_index_cached(out, signature):
    path = Path(out)
    cells = {}
    days = {}
    pairs = {}
    summary = {}
    for r in read_csv_rows(path / 'concordancia_ventanas_celdas.csv'):
        key=(to_int(r['ventana_min']),r['fecha_utc'])
        cells.setdefault(key,{})[r['celda']] = {
            'nivel':r['nivel_concordancia'], 'parejas':to_int(r['parejas_pasada_cercana'])}
    for r in read_csv_rows(path / 'concordancia_ventanas_diaria.csv'):
        key=(to_int(r['ventana_min']),r['fecha_utc'])
        days[key]={k:to_int(r[k]) for k in ('ambos_diarios','ambos_paso_cercano',
            'ambos_solo_dia','parejas_candidatas_dia')}
    for r in read_csv_rows(path / 'parejas_ventanas.csv'):
        key=(to_int(r['ventana_min']),str(r['fecha_modis_utc'])[:10])
        pairs.setdefault(key,[]).append(r)
    for r in read_csv_rows(path / 'resumen_ventanas.csv'):
        summary[to_int(r['ventana_min'])]={
            'ventana_min':to_int(r['ventana_min']),
            'parejas_candidatas':to_int(r['parejas_candidatas']),
            'celdas_dia_ambos':to_int(r['celdas_dia_ambos']),
            'celdas_con_pareja':to_int(r['celdas_con_pareja']),
            'celdas_solo_dia':to_int(r['celdas_solo_dia']),
            'proporcion_con_pareja':to_float(r['proporcion_con_pareja']),
            'ic_bootstrap_dias_inf':to_float(r['ic_bootstrap_dias_inf']),
            'ic_bootstrap_dias_sup':to_float(r['ic_bootstrap_dias_sup'])}
    return {'cells':cells,'days':days,'pairs':pairs,'summary':summary}




def h3_temporal_index(d):
    """Aisla el motor H3 P3: no reutiliza cruces de cuadrícula v2."""
    from emparejamiento_h3_v3_4 import build
    with H3_PAIR_LOCK:
        out, manifest = build(d['folder'], resolution=7)
    return _h3_temporal_index_cached(str(out), manifest['signature'])


@lru_cache(maxsize=4)
def _h3_temporal_index_cached(folder, signature):
    p=Path(folder)
    cells={}; days={}; pairs={}; summary={}
    for r in read_csv_rows(p/'h3_concordancia_celdas.csv'):
        k=(to_int(r['ventana_min']),r['fecha_utc'])
        cells.setdefault(k,{})[r['h3_id']] = {
            'nivel':r['nivel_concordancia'],
            'parejas':to_int(r['parejas_pasada_cercana']),
            'misma':to_int(r['parejas_misma_celda']),
            'vecinas':to_int(r['parejas_vecinas'])}
    for r in read_csv_rows(p/'h3_concordancia_diaria.csv'):
        k=(to_int(r['ventana_min']),r['fecha_utc'])
        days[k]={name:to_int(value) for name,value in r.items() if name not in ('fecha_utc','ventana_min')}
    for r in read_csv_rows(p/'h3_parejas_ventanas.csv'):
        k=(to_int(r['ventana_min']),r['fecha_utc'])
        pairs.setdefault(k,[]).append(r)
    for r in read_csv_rows(p/'h3_resumen_ventanas.csv'):
        w=to_int(r['ventana_min'])
        summary[w]={key:(to_float(val) if key=='proporcion_con_pareja' else to_int(val))
                    for key,val in r.items() if key!='aviso'}
        summary[w]['ic_bootstrap_dias_inf']=None
        summary[w]['ic_bootstrap_dias_sup']=None
    return {'cells':cells,'days':days,'pairs':pairs,'summary':summary}


def valid_window(q):
    text=q.get('ventana',['30'])[0]
    if text not in ('15','30','60','120'):
        raise ValueError('Ventana temporal inválida: elige 15, 30, 60 o 120 minutos')
    return int(text)


def sqlite_file(d):
    """Ruta inmutable del índice. Nunca se reemplaza una base abierta en Windows.

    El nombre cambia al cambiar tamaño/fecha de los CSV de entrada, por lo que
    podemos crear un índice nuevo sin sobrescribir uno que atiende consultas.
    """
    folder = d['folder']
    source_names = ('registros_normalizados_v2.csv',
                    'armonizacion_celdas_dia_v2.csv', 'coincidencias_pasadas_frp.csv')
    concordance_source = concordance_file(d)
    signature = [str(folder.resolve())]
    signature.append((str(concordance_source), concordance_source.stat().st_size, concordance_source.stat().st_mtime_ns))
    for name in source_names:
        path = folder / name
        if path.exists():
            s = path.stat()
            signature.append((name, s.st_size, s.st_mtime_ns))
        else:
            signature.append((name, None, None))
    fingerprint = hashlib.sha256(repr(signature).encode('utf-8')).hexdigest()[:16]
    cache = ROOT / 'cache' / 'indices'
    return cache / f"{d['id']}_{fingerprint}.sqlite3"


def ensure_index(d):
    """Crea caché SQLite indexada por fecha para que años grandes no deban leerse por completo en cada cambio de día."""
    folder = d['folder']
    dbfile = sqlite_file(d)
    dbfile.parent.mkdir(parents=True, exist_ok=True)
    sources = [folder / n for n in ('registros_normalizados_v2.csv',
                                    'armonizacion_celdas_dia_v2.csv', 'coincidencias_pasadas_frp.csv')]
    concordance_source = concordance_file(d)
    if dbfile.is_file():
        return dbfile
    with INDEX_LOCK:
        if dbfile.is_file():
            return dbfile
        tmp = dbfile.parent / ('.construccion_' + uuid4().hex + '.sqlite3')
        try:
            # IMPORTANTE: 'with sqlite3.connect(...)' NO cierra la conexión.
            # closing garantiza cerrarla antes de renombrar en Windows.
            with closing(sqlite3.connect(tmp)) as con, con:
                con.execute("PRAGMA journal_mode=DELETE")
                con.execute("CREATE TABLE points (date TEXT, id TEXT, lat REAL, lon REAL, source TEXT, platform TEXT, time TEXT, frp REAL, t4 REAL, t11 REAL, confidence TEXT, daynight TEXT, scan REAL, track REAL, typ TEXT)")
                con.execute("CREATE TABLE cells (date TEXT, x INTEGER, y INTEGER, km REAL, category TEXT, n_modis INTEGER, n_snpp INTEGER, n_noaa20 INTEGER)")
                con.execute("CREATE TABLE pairs (date TEXT, x INTEGER, y INTEGER, mp TEXT, vp TEXT, distance REAL, minutes REAL, nm INTEGER, nv INTEGER, frpm REAL, frpv REAL, t11m REAL, t11v REAL)")
                con.execute("CREATE TABLE concordance (date TEXT, x INTEGER, y INTEGER, level TEXT, npairs INTEGER, PRIMARY KEY(date,x,y))")
                p = sources[0]
                if p.exists():
                    with p.open(encoding="utf-8-sig", newline="") as f:
                        rd = csv.DictReader(f)
                        batch = []
                        for row in rd:
                            lat, lon = to_float(row.get('latitude')), to_float(row.get('longitude'))
                            if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                                continue
                            batch.append((row.get('date_utc'),row.get('id'),lat,lon,row.get('source'),
                                          row.get('platform'),row.get('time_utc'),to_float(row.get('frp_mw')),
                                          to_float(row.get('brightness_4um_k')),to_float(row.get('brightness_11um_k')),
                                          row.get('confidence_original'),row.get('daynight'),
                                          to_float(row.get('scan_km')),to_float(row.get('track_km')),row.get('type')))
                            if len(batch) >= 5000:
                                con.executemany("INSERT INTO points VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch); batch = []
                        if batch: con.executemany("INSERT INTO points VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                p = sources[1]
                if p.exists():
                    with p.open(encoding="utf-8-sig", newline="") as f:
                        rd = csv.DictReader(f)
                        batch = []
                        for row in rd:
                            try:
                                x, y = (int(z) for z in row.get('celda', '').split('_', 1))
                            except (ValueError, TypeError):
                                continue
                            batch.append((row.get('fecha_utc'),x,y,to_float(row.get('tamano_celda_km')),
                                          row.get('clasificacion'),to_int(row.get('n_modis')),
                                          to_int(row.get('n_viirs_snpp')),to_int(row.get('n_viirs_noaa20'))))
                            if len(batch) >= 5000:
                                con.executemany("INSERT INTO cells VALUES (?,?,?,?,?,?,?,?)",batch); batch=[]
                        if batch: con.executemany("INSERT INTO cells VALUES (?,?,?,?,?,?,?,?)",batch)
                p = sources[2]
                if p.exists():
                    with p.open(encoding="utf-8-sig", newline="") as f:
                        rd = csv.DictReader(f)
                        batch = []
                        for row in rd:
                            try:
                                x, y = (int(z) for z in row.get('celda', '').split('_',1))
                            except (ValueError, TypeError):
                                continue
                            batch.append((str(row.get('fecha_modis_utc',''))[:10],x,y,
                                          row.get('plataforma_modis'),row.get('plataforma_viirs'),
                                          to_float(row.get('distancia_centroides_km')),
                                          to_float(row.get('diferencia_min')),to_int(row.get('n_pix_modis')),
                                          to_int(row.get('n_pix_viirs')),to_float(row.get('frp_modis_mw')),
                                          to_float(row.get('frp_viirs_mw')),to_float(row.get('t11_modis_media_k')),
                                          to_float(row.get('t11_viirs_media_k'))))
                            if len(batch) >= 5000:
                                con.executemany("INSERT INTO pairs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",batch);batch=[]
                        if batch: con.executemany("INSERT INTO pairs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",batch)
                # P1: clasificar concordancia estricta por pasada, por celda y fecha UTC.
                with concordance_source.open(encoding='utf-8-sig', newline='') as f:
                    batch=[]
                    for row in csv.DictReader(f):
                        try:
                            x, y = (int(z) for z in row['celda'].split('_', 1))
                        except (ValueError, KeyError, TypeError):
                            continue
                        batch.append((row['fecha_utc'], x, y, row['nivel_concordancia'],
                                      to_int(row.get('parejas_pasada_cercana'))))
                        if len(batch) >= 5000:
                            con.executemany('INSERT INTO concordance VALUES (?,?,?,?,?)', batch)
                            batch=[]
                    if batch:
                        con.executemany('INSERT INTO concordance VALUES (?,?,?,?,?)',batch)
                con.execute("CREATE INDEX idx_points_date ON points(date)")
                con.execute("CREATE INDEX idx_cells_date ON cells(date)")
                con.execute("CREATE INDEX idx_pairs_date ON pairs(date)")
                con.commit()
            # Archivo nuevo: no sobrescribe ningún índice abierto por otro lector.
            # Retries ayudan frente a antivirus / sincronizadores de Windows.
            for intento in range(5):
                try:
                    if not dbfile.exists():
                        os.replace(tmp, dbfile)
                    break
                except PermissionError:
                    if intento == 4:
                        raise
                    time.sleep(0.2 * (intento + 1))
        finally:
            if tmp.exists():
                try: tmp.unlink()
                except PermissionError: pass
    return dbfile


def invert_grid(x, y, km):
    """Inversa de la proyección simplificada utilizada POR EL MOTOR v2; no equivale a huella instrumental."""
    lat = math.degrees(math.asin(max(-1, min(1, y * km * COS_STD / EARTH_KM))))
    lon = math.degrees((x * km) / (EARTH_KM * COS_STD))
    return [round(lat, 6), round(lon, 6)]


def spatial_comparison(d, ymd):
    """Separación explícita de H3 y cuadrícula (superficies no iguales)."""
    folder = h3_folder(d)
    comp = folder / 'comparacion_metodos_por_dia.csv'
    with comp.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if row['fecha_utc'] == ymd:
                return {
                    'date':ymd,
                    'square':{'cells':to_int(row['cuadriculas_v2']),'both':to_int(row['ambos_cuadricula']),'km':to_float(json.loads((d['folder']/'diagnostico_v2.json').read_text(encoding='utf-8-sig')).get('parameters',{}).get('grid_km',2))},
                    'h3':{'cells':to_int(row['hexagonos_h3']),'both':to_int(row['ambos_h3'])},
                    'disclaimer':'No son métricas de precisión: área, contornos y posiciones de bordes diferentes.'}
    return {'date':ymd,'square':{'cells':0,'both':0},'h3':{'cells':0,'both':0}}


def day_records(d, ymd, layer, include_nonveg, sources, daynight, max_features=6000, method='square', window=30):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', ymd or '') or int(ymd[:4]) != d['year']:
        raise ValueError('Fecha fuera del año seleccionado')
    if layer == 'cells' and method == 'h3':
        # P3: coincidencia temporal H3 independiente de la cuadrícula v2.
        temporal_cells = h3_temporal_index(d)['cells'].get((window,ymd), {})
        import h3
        file = h3_folder(d) / 'h3_celdas_dia.csv'
        features = []
        seen = 0
        with file.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                if row['fecha_utc'] != ymd:
                    continue
                seen += 1
                if seen > max_features:
                    break
                cell = row['h3_id']
                t = temporal_cells.get(cell, {})
                vertices = [list(p) for p in h3.cell_to_boundary(cell)]
                features.append({'id':cell,'lat':to_float(row['centro_lat']),
                      'lon':to_float(row['centro_lon']), 'polygon':vertices,
                      'area_km2':to_float(row['area_hexagono_km2']),
                      'h3_resolucion':to_int(row['h3_resolucion']),
                      'category':row['clasificacion'],
                      'concordancia':t.get('nivel'),
                      'parejas_pasada_cercana':t.get('parejas',0),
                      'parejas_misma_celda':t.get('misma',0),
                      'parejas_vecinas':t.get('vecinas',0),
                      'n_modis':to_int(row['n_modis']),
                      'n_snpp':to_int(row['n_viirs_snpp']),
                      'n_noaa20':to_int(row['n_viirs_noaa20']),
                      'total':to_int(row['total_detecciones'])})
        return {'mode':'cells','spatial_method':'h3','date':ymd,'features':features,
                'limited':seen>max_features,
                'notice':f'H3 r7: coincidencias temporales hasta {window} min en la misma celda o vecinos (k=1), también se exige distancia de huellas; no son incendios confirmados.'}
    if layer == 'pairs' and method == 'h3':
        matches=h3_temporal_index(d)['pairs'].get((window,ymd),[])
        features=[]
        for r in matches[:max_features]:
            features.append({'lat':to_float(r['lat']),'lon':to_float(r['lon']),
                'modis':r['plataforma_modis'],'viirs':r['plataforma_viirs'],
                'relation_h3':r['relacion_h3'],
                'h3_modis':r['celda_h3_modis'],'h3_viirs':r['celda_h3_viirs'],
                'distance_km':to_float(r['distancia_centroides_km']),
                'delta_minutes':to_float(r['diferencia_min']),
                'n_modis':to_int(r['n_pix_modis']),'n_viirs':to_int(r['n_pix_viirs']),
                'frp_modis':to_float(r['frp_modis_mw']),
                'frp_viirs':to_float(r['frp_viirs_mw']),
                't11_modis':to_float(r['t11_modis_media_k']),
                't11_viirs':to_float(r['t11_viirs_media_k'])})
        return {'mode':'pairs','date':ymd,'spatial_method':'h3','features':features,
                'limited':len(matches)>max_features,
                'notice':f'Pares temporales H3 r7 ({window} min) en misma celda o vecinas k=1 y con distancia compatible. Candidatos, NO incendios confirmados.'}
    db = ensure_index(d)
    with closing(sqlite3.connect(db)) as con:
        if layer == 'points':
            query = 'SELECT id,lat,lon,source,platform,time,frp,t4,t11,confidence,daynight,scan,track,typ FROM points WHERE date=?'
            args = [ymd]
            if not include_nonveg:
                query += " AND typ='0'"
            if daynight in ('D', 'N'):
                query += ' AND daynight=?'; args.append(daynight)
            names = [s for s in sources if s in {'modis', 'viirs-snpp', 'viirs-jpss1'}]
            if names:
                query += ' AND source IN ('+','.join('?' for _ in names)+')'; args.extend(names)
            else:
                query += ' AND 1=0'
            rows = con.execute(query + ' LIMIT ?', args + [max_features + 1]).fetchall()
            clipped = len(rows) > max_features
            features = [{"id": v[0], "lat": v[1], "lon": v[2], "source": v[3], "platform": v[4],
                         "time":v[5], "frp":v[6], "t4":v[7], "t11":v[8], "confidence":v[9],
                         "daynight":v[10], "scan":v[11], "track":v[12], "type":v[13]} for v in rows[:max_features]]
            return {"mode": layer, "date": ymd, "features": features, "limited": clipped,
                    "notice": "Los puntos representan centros de píxeles, no la ubicación exacta del fuego."}
        if layer == 'cells':
            temporal_cells = temporal_index(d)['cells'].get((window,ymd), {}) if method == 'square' else {}
            rows = con.execute('SELECT c.x,c.y,c.km,c.category,c.n_modis,c.n_snpp,c.n_noaa20,a.level,a.npairs FROM cells c LEFT JOIN concordance a ON c.date=a.date AND c.x=a.x AND c.y=a.y WHERE c.date=? LIMIT ?', (ymd, max_features + 1)).fetchall()
            features = []
            for x,y,km,category,nm,ns,nn,level,npairs in rows[:max_features]:
                if not km: continue
                p0 = invert_grid(x,y,km)
                p1 = invert_grid(x+1,y+1,km)
                center = invert_grid(x+.5,y+.5,km)
                temporal = temporal_cells.get(f'{x}_{y}', {}) if category == 'ambos' else {}
                if temporal:
                    level,npairs = temporal['nivel'],temporal['parejas']
                features.append({"id": f'{x}_{y}',"lat": center[0], "lon":center[1],
                                 "bounds": [p0,p1], "category": category,
                                 "n_modis":nm,"n_snpp":ns,"n_noaa20":nn,
                                 "concordancia":level,"parejas_pasada_cercana":npairs,
                                 "total":nm+ns+nn})
            return {"mode":layer,"date":ymd,"features":features,"limited":len(rows)>max_features,
                    "notice":"Celdas geográficas del modelo, no perímetros de incendios ni huellas de los sensores."}
        if layer == 'pairs' and window != 30:
            raw = temporal_index(d)['pairs'].get((window,ymd), [])
            km = dataset_profile(d)['diagnostic']['grid_km'] or 2
            features=[]
            for r in raw[:max_features]:
                try:x,y=(int(x) for x in r['celda'].split('_',1))
                except (KeyError,ValueError):continue
                center=invert_grid(x+.5,y+.5,km)
                features.append({'lat':center[0],'lon':center[1],
                    'modis':r['plataforma_modis'],'viirs':r['plataforma_viirs'],
                    'distance_km':to_float(r['distancia_centroides_km']),
                    'delta_minutes':to_float(r['diferencia_min']),
                    'n_modis':to_int(r['n_pix_modis']),'n_viirs':to_int(r['n_pix_viirs']),
                    'frp_modis':to_float(r['frp_modis_mw']),
                    'frp_viirs':to_float(r['frp_viirs_mw']),
                    't11_modis':to_float(r['t11_modis_media_k']),
                    't11_viirs':to_float(r['t11_viirs_media_k'])})
            return {'mode':layer,'date':ymd,'features':features,'limited':len(raw)>max_features,
                    'notice':f'Parejas candidatas con ventana de {window} minutos. No son incendios confirmados; geometría cuadrada v2.'}
        if layer == 'pairs':
            rows = con.execute('SELECT x,y,mp,vp,distance,minutes,nm,nv,frpm,frpv,t11m,t11v FROM pairs WHERE date=? LIMIT ?', (ymd,max_features+1)).fetchall()
            grid_km = dataset_profile(d)['diagnostic']['grid_km'] or 2
            features=[]
            for x,y,mp,vp,dist,minute,nm,nv,frpm,frpv,t11m,t11v in rows[:max_features]:
                center = invert_grid(x+.5,y+.5,grid_km)
                features.append({"lat":center[0],"lon":center[1],"modis":mp,"viirs":vp,
                                 "distance_km":dist,"delta_minutes":minute,
                                 "n_modis":nm,"n_viirs":nv,"frp_modis":frpm,"frp_viirs":frpv,
                                 "t11_modis":t11m,"t11_viirs":t11v})
            return {"mode":layer,"date":ymd,"features":features,"limited":len(rows)>max_features,
                    "notice":"Candidatos por proximidad espacial-temporal; no confirman un mismo incendio."}
    raise ValueError('Modo no válido')


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, separators=(',',':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)

    def do_GET(self):
        parts = urlparse(self.path)
        q = parse_qs(parts.query, keep_blank_values=True)
        try:
            if parts.path == '/api/firetrace/rango':
                from firetrace_api import build_range
                d=dataset_by_id(q.get('id',[''])[0])
                if d is None:
                    self._send({'error':'Conjunto de datos no encontrado'},404);return
                self._send(build_range(d,{k:v[0] for k,v in q.items()},ensure_index));return
            if parts.path == '/api/salud':
                self._send({'ok': True, 'conjuntos': len(list_datasets()), 'version': 'Nodara v3.6 P5 · sensibilidad a calidad de detecciones'}); return
            if parts.path == '/api/catalogo':
                self._send([{"id":d['id'],"region":d['region'],"year":d['year'],"demo":d['demo']} for d in list_datasets()]);return
            if parts.path == '/api/estados':
                import nodara_usa
                self._send(sorted(set(nodara_usa.US_STATES.values())));return
            if parts.path == '/api/tarea':
                proc=JOB['proc']
                status=JOB['status']
                if proc and status=='ejecutando' and proc.poll() is not None:
                    status='completado' if proc.returncode == 0 else 'error';JOB['status']=status
                    try: JOB['log'].flush(); JOB['log'].close()
                    except Exception: pass
                logfile=ROOT/'cache'/'.procesamiento.log'
                tail=''
                if logfile.exists():
                    with logfile.open(encoding='utf-8',errors='replace') as f:
                        lines=f.readlines();tail=''.join(lines[-30:])[-3800:]
                self._send({'status':status,'estado':JOB['estado'],'anios':JOB['anios'],'log':tail});return
            if parts.path == '/api/temporal':
                d=dataset_by_id(q.get('id',[''])[0])
                if d is None:
                    self._send({'error':'Conjunto no encontrado'},404);return
                selected=q.get('fecha',[''])[0]
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',selected or '') or int(selected[:4]) != d['year']:
                    self._send({'error':'Fecha fuera del año seleccionado'},400);return
                method=q.get('metodo',['square'])[0]
                info=h3_temporal_index(d) if method=='h3' else temporal_index(d)
                self._send({'fecha_utc':selected,'seleccion':valid_window(q),'metodo':method,
                  'escenarios':[{'global':info['summary'][w],
                      'dia':info['days'].get((w,selected),{'ambos_diarios':0,'ambos_paso_cercano':0,
                              'ambos_solo_dia':0,'parejas_candidatas_dia':0,'parejas_misma_celda':0,'parejas_vecinas':0})}
                    for w in (15,30,60,120)],
                  'nota':'Ventanas exploratorias; H3 usa misma celda o vecinas k=1, tiempo, huella y pares 1:1. No prueban exactitud ni equivalencia de incendios.'});return
            if parts.path == '/api/concordancia':
                d=dataset_by_id(q.get('id',[''])[0])
                if d is None:
                    self._send({'error':'Conjunto no encontrado'},404);return
                selected=q.get('fecha',[''])[0]
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', selected or '') or int(selected[:4]) != d['year']:
                    self._send({'error':'Fecha fuera del año seleccionado'},400);return
                window=valid_window(q)
                method=q.get('metodo',['square'])[0]
                if method=='h3':
                    info=h3_temporal_index(d)
                    t=info['days'].get((window,selected),{})
                    breakdown={'ambos_paso_cercano':t.get('ambos_paso_cercano',0),
                        'ambos_solo_dia':t.get('ambos_solo_dia',0),
                        'ambos_misma_celda':t.get('ambos_misma_celda',0),
                        'ambos_con_pareja_vecina':t.get('ambos_con_pareja_vecina',0),
                        'solo_modis_con_pareja_vecina':t.get('solo_modis_con_pareja_vecina',0),
                        'solo_viirs_con_pareja_vecina':t.get('solo_viirs_con_pareja_vecina',0)}
                    self._send({'fecha_utc':selected,'metodo_concordancia':'H3_r7_temporal',
                        'pasadas_ventana_minutos':window,'celdas':breakdown,
                        'ambos_diarios':t.get('ambos_diarios',0),
                        'aviso':'H3 k=1 + tiempo y huellas. La vecindad no convierte una celda de un solo sensor en una celda ambos. Candidato NO confirma incendio.'});return
                info=temporal_index(d)
                temporal=info['days'].get((window,selected),{})
                breakdown={'ambos_paso_cercano':temporal.get('ambos_paso_cercano',0),
                           'ambos_solo_dia':temporal.get('ambos_solo_dia',0),
                           'solo_modis':0,'solo_viirs':0}
                db=ensure_index(d)
                with closing(sqlite3.connect(db)) as con:
                    rows=con.execute('SELECT category, COUNT(*) FROM cells WHERE date=? GROUP BY category',(selected,)).fetchall()
                for category,count in rows:
                    if category in ('solo_modis','solo_viirs'):breakdown[category]=count
                self._send({'fecha_utc':selected, 'metodo_concordancia':'cuadricula_v2',
                            'pasadas_ventana_minutos':window,
                            'celdas':breakdown,
                            'ambos_diarios':breakdown['ambos_paso_cercano']+breakdown['ambos_solo_dia'],
                            'aviso':'Candidato cercano NO confirma mismo incendio. No transferir categorías a H3 sin otro emparejamiento.'});return
            if parts.path == '/api/auditoria-calidad':
                d=dataset_by_id(q.get('id',[''])[0])
                if d is None:
                    self._send({'error':'Conjunto no encontrado'},404);return
                selected=q.get('fecha',[''])[0]
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',selected or '') or int(selected[:4])!=d['year']:
                    self._send({'error':'Fecha fuera del año seleccionado'},400);return
                from calidad_detecciones_v3_6 import build,read_rows
                window=valid_window(q)
                output,report=build(d['folder'],window=window)
                daily={}
                for r in read_rows(output/'calendario_calidad.csv'):
                    if r['fecha_utc']==selected:
                        daily.setdefault(r['escenario'],{})[r['metodo']]={
                            k:to_int(r[k]) for k in ('celdas_activas','ambos','solo_modis','solo_viirs',
                                     'ambos_con_pareja','ambos_solo_fecha','parejas')}
                self._send({'version':report['version'],'region':d['region'],'anio':d['year'],
                    'fecha_utc':selected,'ventana_min':window,'calidad_original_v2':report['calidad_original_v2'],
                    'registros_validados_todos_los_tipos':report['registros_validados_todos_los_tipos'],
                    'registros_type0':report['registros_type0'],
                    'distribucion':report['calidad_por_fuente'],'distribucion_periodo':report['calidad_por_fuente_y_dia_noche'],'escenarios':report['escenarios'],
                    'diarios':daily,'archivo_csv':str(output/'escenarios_calidad.csv'),
                    'advertencia':'Comparación de filtros: NO son probabilidades, no valida verdad terreno ni demuestra mayor exactitud.'});return
            if parts.path == '/api/auditoria-espacial':
                d=dataset_by_id(q.get('id',[''])[0])
                if d is None:
                    self._send({'error':'Conjunto no encontrado'},404);return
                from comparacion_espacial_v3_5 import build
                window=valid_window(q)
                folder,diagnostic=build(d['folder'],window=window)
                self._send({'metodo':'auditoria_espacial_controlada_P4',
                     'ventana':window,'region':d['region'],'anio':d['year'],
                     'h3':diagnostic['h3'],
                     'cuadrado_2km_origen':diagnostic['square_2km_origin'],
                     'cuadrado_area_equivalente_origen':diagnostic['square_matched_origin'],
                     'promedio_area_hexagono_km2':diagnostic['h3_average_cell_area_km2'],
                     'lado_cuadrado_equivalente_km':diagnostic['matched_square_side_km'],
                     'resumen_desplazamientos':diagnostic['shift_summary'],
                     'archivo_csv':str(folder/'escenarios.csv'),
                     'aviso':'33 escenarios reproducibles; no sensibilidad/especificidad ni validacion de sensores.'});return
            if parts.path == '/api/espacial':
                d=dataset_by_id(q.get('id',[''])[0])
                if d is None:
                    self._send({'error':'Conjunto no encontrado'},404);return
                self._send(spatial_comparison(d,q.get('fecha',[''])[0]));return
            if parts.path in ('/api/perfil','/api/dia'):
                dataset_id=q.get('id',[''])[0]
                d=dataset_by_id(dataset_id)
                if d is None:
                    self._send({'error':'Conjunto de datos no encontrado'},404);return
                if parts.path == '/api/perfil':
                    self._send(dataset_profile(d, q.get('metodo',['square'])[0] if q.get('metodo',['square'])[0] in ('square','h3') else 'square'));return
                selected_date=q.get('fecha',[f'{d["year"]}-01-01'])[0]
                layer=q.get('modo',['points'])[0]
                sources=[s for s in q.get('fuentes',['modis,viirs-snpp,viirs-jpss1'])[0].split(',') if s]
                onlyveg=q.get('solo_vegetacion',['1'])[0]!='0'
                dn=q.get('dia_noche',['ambos'])[0]
                self._send(day_records(d,selected_date,layer,not onlyveg,sources,dn,method=(q.get('metodo',['square'])[0] if q.get('metodo',['square'])[0] in ('square','h3') else 'square'),window=valid_window(q)));return
            # Archivos estáticos a partir de rutas conocidas; no permite recorrer el sistema.
            static = {'/':'firetrace.html','/firetrace.html':'firetrace.html',
                      '/firetrace.js':'firetrace.js','/firetrace.css':'firetrace.css',
                      '/firetrace-logo.png':'firetrace-logo.png',
                      '/observatorio':'index.html','/index.html':'index.html','/app.js':'app.js',
                      '/styles.css':'styles.css','/favicon.svg':'favicon.svg'}
            file = STATIC / static.get(parts.path,'') if parts.path in static else None
            if file and file.is_file():
                types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png'}
                data=file.read_bytes()
                self.send_response(200);self.send_header('Content-Type',types.get(file.suffix,'application/octet-stream')+'; charset=utf-8')
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
                return
            self._send({'error':'Recurso no encontrado'},404)
        except (OSError,ValueError,sqlite3.Error,RuntimeError,ImportError) as e:
            self._send({'error':str(e)},500)

    def do_POST(self):
        if urlparse(self.path).path != '/api/procesar':
            self._send({'error':'Ruta desconocida'},404);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 4096:
                raise ValueError('Solicitud inválida')
            obj=json.loads(self.rfile.read(length))
            estado=str(obj.get('estado','')).strip()
            anios=str(obj.get('anios','')).strip()
            import nodara_usa
            if estado not in set(nodara_usa.US_STATES.values()):
                raise ValueError('Selecciona un estado válido de Estados Unidos')
            years=nodara_usa.parse_years(anios)
            if len(years)>3 or min(years)<2000 or max(years)>date.today().year:
                raise ValueError('Selecciona de 1 a 3 años disponibles (2000-presente)')
            with SERVER_LOCK:
                if JOB['proc'] and JOB['proc'].poll() is None:
                    self._send({'error':'Ya hay una descarga/análisis ejecutándose'},409);return
                logfile=(ROOT/'cache'/'.procesamiento.log').open('w',encoding='utf-8')
                cmd=[sys.executable, '-u', str(APP_DIR/'nodara_usa.py'), 'ejecutar',
                     '--estado',estado,'--anios',','.join(str(y) for y in years)]
                try:
                    proc=subprocess.Popen(cmd,cwd=ROOT,stdout=logfile,stderr=subprocess.STDOUT)
                except Exception:
                    logfile.close();raise
                JOB.update({'proc':proc,'log':logfile,'status':'ejecutando','estado':estado,'anios':anios})
            self._send({'status':'ejecutando','estado':estado,'anios':anios});return
        except (ValueError,TypeError,OSError,ImportError) as e:
            self._send({'error':str(e)},400)

    def log_message(self,fmt,*args):
        if '/api/' not in str(args):
            print('[VISOR]',fmt%args)


def main():
    cli=argparse.ArgumentParser(description='Visor interactivo de detecciones y armonización NASA FIRMS')
    cli.add_argument('--puerto', type=int, default=PORT_DEFAULT)
    cli.add_argument('--no-abrir', action='store_true', help='No abrir navegador automáticamente')
    cli.add_argument('--auto', action='store_true', help='Descargar y analizar un estado antes de abrir visor')
    cli.add_argument('--estado', default='California')
    cli.add_argument('--anios', default='2024')
    args=cli.parse_args()
    if args.auto:
        import nodara_usa
        print('\nPreparando el estado solicitado con NASA FIRMS (puede descargar archivos grandes)...')
        nodara_usa.main(['ejecutar','--estado',args.estado,'--anios',args.anios])
    host='127.0.0.1'
    server=ThreadingHTTPServer((host,args.puerto),Handler)
    url=f'http://{host}:{args.puerto}'
    print('\nNODARA TECH — VISOR DE INCENDIOS')
    print('Abre en el navegador:',url)
    print('Para terminar presiona Ctrl+C.\n')
    if not args.no_abrir:
        threading.Timer(0.6,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServidor detenido.')
    finally:
        server.server_close()

if __name__=='__main__':
    main()
