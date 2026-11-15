"""Validación con H3 OFICIAL + datos FIRMS del proyecto, sin simulaciones.

Ejecutar en Windows desde raíz del proyecto:
  py aplicacion\\pruebas_problema3_reales.py
Falla si h3-py 4.x no está instalado; no sustituye un estudio de exactitud.
"""
from pathlib import Path
from collections import Counter,defaultdict
import math
from datetime import datetime

from espacial_h3_v3 import h3_api
from emparejamiento_h3_v3_4 import build,read_csv
from sensibilidad_temporal_v3_3 import WINDOWS

ROOT=Path(__file__).resolve().parent.parent
BASE=ROOT/'resultados'/'resultados_armonizacion_v2'


def validate(folder):
    h3=h3_api()
    dest,diag=build(folder,resolution=7)
    cells_file=folder/'espacial_h3_v3'/'h3_r7'/'h3_celdas_dia.csv'
    h3_daily=list(read_csv(cells_file))
    presence={(r['fecha_utc'],r['h3_id']):r['clasificacion'] for r in h3_daily}
    with_pairs={}
    prev_count=0
    for w in WINDOWS:
        pairs=[p for p in read_csv(dest/'h3_parejas_ventanas.csv') if int(p['ventana_min'])==w]
        summary=next(x for x in diag['summary'] if x['ventana_min']==w)
        assert len(pairs)==summary['parejas_candidatas']
        assert len(pairs)>=prev_count
        prev_count=len(pairs)
        seen=defaultdict(lambda:[set(),set()])
        for p in pairs:
            m=datetime.fromisoformat(p['fecha_modis_utc'].removesuffix('Z'))
            v=datetime.fromisoformat(p['fecha_viirs_utc'].removesuffix('Z'))
            assert m.date()==v.date()
            assert m.date().isoformat()==p['fecha_utc']
            assert abs((m-v).total_seconds())/60<=w+1e-8
            assert float(p['distancia_centroides_km'])<=float(p['umbral_huella_aprox_km'])+1e-6
            a=p['celda_h3_modis'];b=p['celda_h3_viirs']
            assert a==b if p['relacion_h3']=='misma_celda' else (a!=b and b in h3.grid_disk(a,1))
            assert (p['fecha_utc'],a) in presence and (p['fecha_utc'],b) in presence
            key=(p['fecha_utc'],p['plataforma_modis'],p['plataforma_viirs'])
            assert p['id_paso_modis'] not in seen[key][0]
            assert p['id_paso_viirs'] not in seen[key][1]
            seen[key][0].add(p['id_paso_modis']);seen[key][1].add(p['id_paso_viirs'])
        day_cells=[r for r in read_csv(dest/'h3_concordancia_celdas.csv') if int(r['ventana_min'])==w]
        assert len(day_cells)==len(presence)
        assert sum(r['clasificacion']=='ambos' for r in day_cells)==summary['celdas_dia_ambos']
        assert summary['celdas_dia_ambos']==summary['celdas_con_pareja']+summary['celdas_solo_dia']
        print(f'  {w:3d} min: {len(pairs):5d} pares H3 ({summary["parejas_misma_celda"]} internos, '
              f'{summary["parejas_vecinas"]} vecinas); {summary["celdas_con_pareja"]} '
              f'de {summary["celdas_dia_ambos"]} compartidas con al menos una pareja')
    print('  PASA: API H3 real; tiempo, distancia, vecindad, 1:1 y conservación de conteos.')


def main():
    h3=h3_api()
    print('H3 oficial:',getattr(h3,'__version__','4.x'))
    for region in ('Costa_Rica','Afghanistan'):
        folder=BASE/region/'2024'
        if folder.exists():
            print('Datos:',region,2024)
            validate(folder)
        else:
            print('Sin datos opcionales:',folder)
    print('Validación de software completada. NO calcula sensibilidad, especificidad ni exactitud científica.')

if __name__=='__main__':main()
