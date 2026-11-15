"""Pruebas P2: cotejo fuerte con P1 y v2, monotonía y vistas del visor.

No requiere conexión a Internet ni paquetes adicionales para la cuadrícula.
H3 real se mantiene independiente (instalar 'h3' para probar su geometría).
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
from sensibilidad_temporal_v3_3 import build
from concordancia_v3_2 import build as build_p1
import visor_incendios as visor

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'resultados' / 'resultados_armonizacion_v2'


def test_region(country, pair_expected, near_expected, both):
    folder=BASE/country/'2024'
    out,manifest=build(folder,force=True)
    summary=manifest['summary']
    assert [s['ventana_min'] for s in summary]==[15,30,60,120]
    assert [s['parejas_candidatas'] for s in summary]==pair_expected
    assert [s['celdas_con_pareja'] for s in summary]==near_expected
    assert all(s['celdas_dia_ambos']==both for s in summary)
    assert all(s['celdas_con_pareja']+s['celdas_solo_dia']==both for s in summary)
    assert all(s['celdas_con_pareja']<=s['parejas_candidatas'] for s in summary)
    assert all(s['ic_bootstrap_dias_inf']<=s['proporcion_con_pareja']<=s['ic_bootstrap_dias_sup'] for s in summary)
    assert all(a<=b for a,b in zip(near_expected,near_expected[1:]))
    prev=build_p1(folder)[1]
    assert summary[1]['celdas_con_pareja']==prev['daily_both_with_nearby_pair']
    assert summary[1]['celdas_solo_dia']==prev['daily_both_without_nearby_pair']
    lookup={(d['id']):d for d in visor.list_datasets()}
    d=lookup[f'{country}__2024']
    cache=visor.temporal_index(d)
    assert [cache['summary'][x]['parejas_candidatas'] for x in (15,30,60,120)]==pair_expected
    for i,w in enumerate((15,30,60,120)):
        assert sum(r['parejas_candidatas_dia'] for (window,day),r in cache['days'].items() if window==w)==pair_expected[i]
    print('PASS:',country,'parejas',pair_expected,'celdas cercanas',near_expected)


def test_march_31():
    d=next(x for x in visor.list_datasets() if x['id']=='Costa_Rica__2024')
    info=visor.temporal_index(d)
    expected={15:(33,18,33),30:(38,13,65),60:(38,13,65),120:(38,13,65)}
    for window,(near,only_day,pairs) in expected.items():
        day=info['days'][(window,'2024-03-31')]
        assert (day['ambos_paso_cercano'],day['ambos_solo_dia'],day['parejas_candidatas_dia'])==(near,only_day,pairs)
        zones=visor.day_records(d,'2024-03-31','cells',False,['modis','viirs-snpp','viirs-jpss1'],'ambos',method='square',window=window)
        crosses=visor.day_records(d,'2024-03-31','pairs',False,[], 'ambos',method='square',window=window)
        assert len(zones['features'])==184
        assert len(crosses['features'])==pairs
        assert sum(f['concordancia']=='ambos_paso_cercano' for f in zones['features'])==near
        assert sum(f['concordancia']=='ambos_solo_dia' for f in zones['features'])==only_day
    print('PASS: Costa Rica 31/03 — 184 celdas intactas, ventanas y cruces sincronizados')


def main():
    test_region('Costa_Rica',[167,370,532,625],[167,313,374,399],527)
    test_region('Afghanistan',[9,18,25,34],[9,17,21,25],34)
    test_march_31()
    print('TODAS LAS PRUEBAS P2 PASARON. No implica que 30/60/120 min sean validados.')

if __name__=='__main__': main()
