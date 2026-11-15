"""Nodara Tech v3: SEGUNDO sistema espacial, H3, en paralelo con la cuadrícula v2.

Entradas: registros_normalizados_v2.csv y los productos cuadriculados v2.
Salida: células H3 por día, calendario, comprobaciones de vecindad y comparación
         entre métodos. NO estima hectáreas quemadas ni incendios únicos.

h3-py API 4.x (https://uber.github.io/h3-py/api_quick.html).
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

H3_RES_DEFAULT = 7
SOURCES = ('modis', 'viirs-snpp', 'viirs-jpss1')
OUTPUT = 'espacial_h3_v3'


def h3_api():
    try:
        import h3
    except ImportError as exc:
        raise RuntimeError('Falta H3. Instala: py -m pip install "h3>=4.2,<5"') from exc
    if not hasattr(h3, 'latlng_to_cell') or not hasattr(h3, 'cell_to_boundary'):
        raise RuntimeError('Se requiere h3-py 4.x, NO la API antigua 3.x.')
    return h3


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def is_type0(row, quality='todas'):
    if str(row.get('type', '')).strip() != '0':
        return False
    if (quality == 'sin_l_viirs' and row.get('source') != 'modis'
            and str(row.get('confidence_original', '')).lower() == 'l'):
        return False
    return True


def load_counter(folder: Path, resolution: int, quality='todas'):
    h3 = h3_api()
    file = folder / 'registros_normalizados_v2.csv'
    if not file.is_file():
        raise FileNotFoundError(f'No existe {file}; primero ejecuta el motor v2.')
    cells = defaultdict(Counter)
    seen = Counter()
    with file.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            seen['total'] += 1
            if not is_type0(row, quality):
                continue
            source = row.get('source', '')
            lat, lon = number(row.get('latitude')), number(row.get('longitude'))
            dt = row.get('date_utc', '')
            if source not in SOURCES or lat is None or lon is None or not (-90<=lat<=90 and -180<=lon<=180):
                seen['invalid_included'] += 1
                continue
            try:
                date.fromisoformat(dt)
                cell = h3.latlng_to_cell(lat, lon, resolution)
            except (ValueError, TypeError):
                seen['invalid_included'] += 1
                continue
            cells[(dt, cell)][source] += 1
            seen['included'] += 1
    return cells, seen


def classify(c):
    m = c['modis'] > 0
    v = (c['viirs-snpp'] + c['viirs-jpss1']) > 0
    return 'ambos' if m and v else 'solo_modis' if m else 'solo_viirs'


def stats_for(cells):
    result = Counter(classify(counter) for counter in cells.values())
    result['union'] = len(cells)
    result['modis'] = result['ambos'] + result['solo_modis']
    result['viirs'] = result['ambos'] + result['solo_viirs']
    return dict(result)


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore')
        w.writeheader();w.writerows(rows)


def generate(folder: Path, resolution=H3_RES_DEFAULT, force=False):
    """Produce análisis H3. Caching por firma archivo+resolución+calidad.

    Se ejecuta tras la v2. La v2 no se altera; el archivo normalizado es la fuente.
    """
    folder = Path(folder).resolve()
    resolution = int(resolution)
    if not 0 <= resolution <= 15:
        raise ValueError('Resolución H3 debe estar entre 0 y 15.')
    h3=h3_api()
    diagfile=folder/'diagnostico_v2.json'
    diag=json.loads(diagfile.read_text(encoding='utf-8-sig')) if diagfile.exists() else {}
    quality=diag.get('parameters',{}).get('quality','todas')
    square_km=diag.get('parameters',{}).get('grid_km',2)
    source=folder/'registros_normalizados_v2.csv'
    st=source.stat()
    dst=folder/OUTPUT/f'h3_r{resolution}'
    manifest=dst/'manifiesto_v3.json'
    signature={'bytes':st.st_size,'mtime_ns':st.st_mtime_ns,'resolution':resolution,'quality':quality,'motor':'3.0'}
    if not force and manifest.is_file():
        try:
            prev=json.loads(manifest.read_text(encoding='utf-8'))
            if prev.get('signature')==signature and (dst/'h3_celdas_dia.csv').is_file():
                return dst,prev
        except (OSError,ValueError):pass
    cells,seen=load_counter(folder,resolution,quality)
    by_day=defaultdict(list)
    for (dt,cell),c in sorted(cells.items()):
        by_day[dt].append((cell,c))
    # Vecindad: NO considera tiempo exacto ni delimita el fuego.
    adjacent=Counter()
    near_rows=[]
    for dt,items in sorted(by_day.items()):
        categories={cell:classify(c) for cell,c in items}
        mset={cell for cell,cat in categories.items() if cat in ('ambos','solo_modis')}
        vset={cell for cell,cat in categories.items() if cat in ('ambos','solo_viirs')}
        for cell,c in items:
            cat=categories[cell]
            if cat not in ('solo_modis','solo_viirs'):
                continue
            other=vset if cat=='solo_modis' else mset
            # Checar solo 6 vecinos inmediatos (más la propia celda, ya excluida).
            peers=sorted(set(h3.grid_disk(cell,1)).intersection(other)-{cell})
            if peers:
                adjacent[cat]+=1
                near_rows.append({'fecha_utc':dt,'h3_id':cell,'clasificacion':cat,
                                  'vecinos_otra_familia':';'.join(peers),
                                  'cantidad_vecinos':len(peers),
                                  'aviso':'solo vecindad espacial diaria; no confirma mismo fuego'})
    dst.mkdir(parents=True,exist_ok=True)
    rows=[]
    for (dt,cell),c in sorted(cells.items()):
        lat,lon=h3.cell_to_latlng(cell)
        rows.append({'fecha_utc':dt,'h3_id':cell,'h3_resolucion':resolution,
                     'area_hexagono_km2':round(h3.cell_area(cell,unit='km^2'),7),
                     'centro_lat':round(lat,7),'centro_lon':round(lon,7),
                     'clasificacion':classify(c),
                     'n_modis':c['modis'],'n_viirs_snpp':c['viirs-snpp'],
                     'n_viirs_noaa20':c['viirs-jpss1'],
                     'total_detecciones':sum(c.values()),
                     'presencia_proxy':1})
    write_csv(dst/'h3_celdas_dia.csv',
              ['fecha_utc','h3_id','h3_resolucion','area_hexagono_km2','centro_lat','centro_lon',
               'clasificacion','n_modis','n_viirs_snpp','n_viirs_noaa20','total_detecciones','presencia_proxy'],rows)
    write_csv(dst/'h3_vecindad_exploratoria.csv',
              ['fecha_utc','h3_id','clasificacion','vecinos_otra_familia','cantidad_vecinos','aviso'],near_rows)
    year = int(diag.get('anio',0)) if diag.get('anio') else (int(next(iter(by_day))[:4]) if by_day else None)
    daily=[];monthly=[]
    if year:
        d,end=date(year,1,1),date(year+1,1,1)
        while d<end:
            dt=d.isoformat();counts=Counter(classify(c) for _,c in by_day.get(dt,[]))
            daily.append({'fecha_utc':dt,'celdas_activas_proxy':sum(counts.values()),
                          'ambos':counts['ambos'],'solo_modis':counts['solo_modis'],
                          'solo_viirs':counts['solo_viirs'],
                          'nota':'sin_detecciones_no_equivale_sin_incendios' if not counts else ''})
            d+=timedelta(days=1)
        for m in range(1,13):
            dates=[r for r in daily if r['fecha_utc'][5:7]==f'{m:02d}']
            monthly.append({'mes_utc':f'{year}-{m:02d}',
                'celdas_dia_activas_proxy':sum(r['celdas_activas_proxy'] for r in dates),
                'ambos':sum(r['ambos'] for r in dates),
                'solo_modis':sum(r['solo_modis'] for r in dates),
                'solo_viirs':sum(r['solo_viirs'] for r in dates),
                'dias_con_detecciones':sum(r['celdas_activas_proxy']>0 for r in dates)})
    write_csv(dst/'h3_calendario_diario.csv',
        ['fecha_utc','celdas_activas_proxy','ambos','solo_modis','solo_viirs','nota'],daily)
    write_csv(dst/'h3_calendario_mensual.csv',
        ['mes_utc','celdas_dia_activas_proxy','ambos','solo_modis','solo_viirs','dias_con_detecciones'],monthly)
    sq_file=folder/'armonizacion_celdas_dia_v2.csv'
    squares=defaultdict(Counter)
    if sq_file.exists():
        with sq_file.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f): squares[row['fecha_utc']][row['clasificacion']]+=1
    comparison=[]
    for dt in sorted(set(by_day)|set(squares)):
        hs=Counter(classify(c) for _,c in by_day.get(dt,[]));ss=squares[dt]
        hsum=sum(hs.values()); ssum=sum(ss.values())
        comparison.append({'fecha_utc':dt,'cuadriculas_v2':ssum,'hexagonos_h3':hsum,
            'ambos_cuadricula':ss['ambos'],'ambos_h3':hs['ambos'],
            'solo_modis_cuadricula':ss['solo_modis'],'solo_modis_h3':hs['solo_modis'],
            'solo_viirs_cuadricula':ss['solo_viirs'],'solo_viirs_h3':hs['solo_viirs'],
            'diferencia_unidades_h3_menos_cuadricula':hsum-ssum,
            'nota':'area_y_geometria_diferentes;no_comparar_como_precision'})
    write_csv(dst/'comparacion_metodos_por_dia.csv',
        ['fecha_utc','cuadriculas_v2','hexagonos_h3','ambos_cuadricula','ambos_h3',
         'solo_modis_cuadricula','solo_modis_h3','solo_viirs_cuadricula','solo_viirs_h3',
         'diferencia_unidades_h3_menos_cuadricula','nota'],comparison)
    res=stats_for(cells)
    sq=Counter()
    for counts in squares.values():sq.update(counts)
    meta={'signature':signature,'pais':diag.get('pais'),'anio':year,
          'resolucion_h3':resolution,'area_media_hexagono_km2':h3.average_hexagon_area(resolution,unit='km^2'),
          'cuadricula_v2_km':square_km,'area_nominal_cuadricula_km2':square_km*square_km,
          'calidad':quality,'leidos':dict(seen),'h3_celdas_dia':res,
          'cuadricula_celdas_dia':dict(sq),
          'vecindad_h3':{'solo_modis_con_vecino_viirs':adjacent['solo_modis'],
                        'solo_viirs_con_vecino_modis':adjacent['solo_viirs']},
          'pares_frp_v2':diag.get('candidate_pairs'),
          'advertencia':('Los valores son conteos de celdas CON detección, no de incendios, área quemada, '
                         'ni exactitud de sensores. H3 y cuadrícula tienen distinta área y geometría. '
                         'Las coincidencias vecinas no están verificadas temporalmente. '
                         'No hay máscaras de nubosidad/cobertura ni calibración histórica.')}
    tmp=manifest.with_suffix('.tmp')
    tmp.write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    os.replace(tmp,manifest)
    return dst,meta


def main():
    parser=argparse.ArgumentParser(description='Nodara Tech: comparación espacial H3 + cuadrícula v2')
    parser.add_argument('--carpeta',type=Path,required=True,help='Carpeta con registros_normalizados_v2.csv')
    parser.add_argument('--resolucion',type=int,default=7,help='H3 resolución, por defecto 7')
    parser.add_argument('--forzar',action='store_true')
    args=parser.parse_args()
    dst,report=generate(args.carpeta,args.resolucion,args.forzar)
    print('H3 v3 terminado:',dst)
    print('H3:',report['h3_celdas_dia'],'| Cuadrícula:',report['cuadricula_celdas_dia'])
    print('Vecindad:',report['vecindad_h3'])
    print('ATENCIÓN: son agrupaciones de detecciones, NO incendios confirmados.')

if __name__=='__main__':main()
