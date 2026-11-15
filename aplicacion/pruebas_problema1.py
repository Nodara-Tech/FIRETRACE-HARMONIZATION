"""Pruebas automáticas de la corrección del problema 1, sin instalar paquetes extra."""
from __future__ import annotations
import csv
import json
import tempfile
from pathlib import Path
from concordancia_v3_2 import build,read_rows

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'resultados'/'resultados_armonizacion_v2'


def assert_result(folder, expected):
    dst,d=build(folder,force=True)
    got=(d['cell_days'],d['daily_both'],d['daily_both_with_nearby_pair'],d['daily_both_without_nearby_pair'])
    assert got==expected,(folder,got,expected)
    rows=list(read_rows(dst/'concordancia_celdas_dia.csv'))
    assert len(rows)==expected[0]
    assert sum(r['nivel_concordancia']=='ambos_paso_cercano' for r in rows)==expected[2]
    for day in read_rows(dst/'concordancia_diaria.csv'):
        assert int(day['celdas_activas']) == sum(int(day[x]) for x in ('ambos_paso_cercano','ambos_solo_dia','solo_modis','solo_viirs'))
    print('PASS:',folder.parent.name,got)
    return dst


def synthetic_midnight():
    """Una pareja que cruza medianoche NO acredita 'ambos el mismo día'."""
    with tempfile.TemporaryDirectory() as tmp:
        f=Path(tmp)
        (f/'diagnostico_v2.json').write_text(json.dumps({'parameters':{'pass_window_minutes':30}}))
        with (f/'armonizacion_celdas_dia_v2.csv').open('w',newline='') as h:
            w=csv.DictWriter(h,fieldnames=['fecha_utc','celda','clasificacion','n_modis','n_viirs_snpp','n_viirs_noaa20'])
            w.writeheader()
            w.writerow({'fecha_utc':'2024-03-31','celda':'3_4','clasificacion':'ambos','n_modis':1,'n_viirs_snpp':1,'n_viirs_noaa20':0})
        with (f/'coincidencias_pasadas_frp.csv').open('w',newline='') as h:
            w=csv.DictWriter(h,fieldnames=['fecha_modis_utc','fecha_viirs_utc','distancia_centroides_km','umbral_huella_aprox_km','celda'])
            w.writeheader()
            w.writerow({'fecha_modis_utc':'2024-03-31T23:55:00Z','fecha_viirs_utc':'2024-04-01T00:05:00Z','distancia_centroides_km':0.1,'umbral_huella_aprox_km':0.5,'celda':'3_4'})
        dst,d=build(f)
        assert d['daily_both_without_nearby_pair']==1
        assert d['daily_both_with_nearby_pair']==0
        assert d['unlinked_pair_reasons'].get('pares_cruzan_medianoche_utc')==1
        print('PASS: una pareja entre dos fechas UTC no se certifica como misma celda-día')


def main():
    cr=assert_result(OUT/'Costa_Rica'/'2024',(6023,527,313,214))
    af=assert_result(OUT/'Afghanistan'/'2024',(740,34,17,17))
    rows=[r for r in read_rows(cr/'concordancia_diaria.csv') if r['fecha_utc']=='2024-03-31']
    assert len(rows)==1
    r=rows[0]
    assert (int(r['celdas_activas']),int(r['ambos_paso_cercano']),int(r['ambos_solo_dia']))==(184,38,13)
    print('PASS: 31 de marzo: 184 activas, 38 de ambos con pareja cercana, 13 solo mismo día')
    synthetic_midnight()
    print('TODAS LAS PRUEBAS DEL PROBLEMA 1 PASARON')

if __name__=='__main__':main()
