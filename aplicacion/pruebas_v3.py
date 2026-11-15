"""Prueba real de v3 H3 + cuadrícula; ejecutable sin conectar a NASA.
No utiliza datos ficticios ni modifica los originales.
"""
from pathlib import Path
import csv
import json
import sys

import espacial_h3_v3 as spatial
import visor_incendios as visor


def run():
    h3 = spatial.h3_api()
    print('H3 instalado:', getattr(h3, '__version__', 'versión no indicada'))
    # Caso de referencia publicado en documentación oficial h3-py.
    known = h3.latlng_to_cell(37.769377,-122.388903,9)
    assert known == '89283082e73ffff', f'Índice H3 inesperado: {known}'
    assert len(h3.cell_to_boundary(known)) in (5,6), 'Geometría H3 inválida'
    print('PASS: índice H3 del ejemplo oficial y límite de hexágono')
    d=visor.dataset_by_id('Costa_Rica__2024')
    if d is None:
        raise RuntimeError('Faltan datos de ejemplo Costa Rica 2024.')
    sq = visor.dataset_profile(d,'square')
    he = visor.dataset_profile(d,'h3')
    assert len(sq['daily']) == len(he['daily']) == 366
    out=spatial.generate(d['folder'],7)[1]
    assert out['leidos']['total'] == 13941
    assert out['leidos']['included'] == 13836
    assert out['h3_celdas_dia']['union'] == sum(
        x['active'] for x in he['daily'])
    assert out['cuadricula_celdas_dia']['solo_modis'] == 413
    assert out['cuadricula_celdas_dia']['ambos'] == 527
    assert out['cuadricula_celdas_dia']['solo_viirs'] == 5083
    print('PASS: 13.941 registros; 13.836 type=0; cuadrícula v2 sin cambios')
    dt='2024-03-31'
    point=visor.day_records(d,dt,'points',False,list(spatial.SOURCES),'ambos',method='h3')
    square=visor.day_records(d,dt,'cells',False,[],'ambos',method='square')
    h3day=visor.day_records(d,dt,'cells',False,[],'ambos',method='h3')
    paired=visor.day_records(d,dt,'pairs',False,[],'ambos',method='h3')
    assert len(point['features']) == 628
    assert len(square['features']) == 184
    assert len(paired['features']) == 65
    assert h3day['features'] and len(h3day['features']) > 0
    assert len(h3day['features'][0]['polygon']) in (5,6)
    assert visor.spatial_comparison(d,dt)['square']['cells'] == 184
    print('PASS: mapa con detecciones, cuadrados, hexágonos y cruces')
    print('H3 r7 Costa Rica 2024:',out['h3_celdas_dia'])
    print('H3 r7 para 2024-03-31:',len(h3day['features']))
    print('PASS: v3 H3 y v2 pueden funcionar en paralelo')

if __name__=='__main__':
    try:run()
    except Exception as exc:
        print('ERROR DE PRUEBA:', type(exc).__name__, exc)
        raise SystemExit(1)
