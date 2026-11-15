"""Pruebas unitarias P4; H3 SIMULADO solo en TemporaryDirectory.

Para validar la API oficial y los datos NASA ejecutar pruebas_problema4_reales.py.
"""
import csv
import json
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from datetime import datetime
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from pruebas_problema3 import FakeH3, record
from comparacion_espacial_v3_5 import SquareAdapter, build, count_matches
from sensibilidad_temporal_v3_3 import records_from_normalized


def tests_geometry():
    # La posición del punto no cambia cuando se desplaza la cuadrícula.
    base=SquareAdapter(2.,0.,0.)
    shift=SquareAdapter(2.,.5,.25)
    for lat,lon in [(9.0,-84.0),(33.5,65.7),(-15.1,-70.2)]:
        x,y=base.latlng_to_cell(lat,lon,7)
        assert len(base.grid_disk((x,y),1))==9
        assert base.latlng_to_cell(lat,lon,7)==(x,y)
        assert isinstance(shift.latlng_to_cell(lat,lon,7),tuple)
    # Mismas funciones de P3 aplicadas a cuadrados: pareja cercana entre vecinos.
    recs=[record('2024-03-31T10:00',9,-84.001,'MODIS','Terra'),
          record('2024-03-31T10:08',9,-83.999,'VIIRS','SNPP')]
    outcome=count_matches(recs,base,window=15,kind='cuadrado_2km',side_km=2.,nominal_area=4.)
    assert outcome['pares_con_vecinos']==1,outcome
    assert outcome['pares_estrictos_misma_celda']<=1
    assert outcome['celdas_dia_ambos']<=outcome['celdas_dia_activas']
    print('PASS P4: cuadrados, desplazamientos y emparejador compartido')


def tests_pipeline():
    fake=FakeH3()
    with tempfile.TemporaryDirectory(prefix='nodara_p4_synthetic_') as tmp:
        folder=Path(tmp)
        (folder/'diagnostico_v2.json').write_text(json.dumps({'anio':2024,'pais':'Ejemplo Ficticio',
                     'parameters':{'grid_km':2,'quality':'todas'}}),encoding='utf-8')
        columns=['latitude','longitude','date_utc','time_utc','family','platform','source','daynight',
                 'scan_km','track_km','frp_mw','brightness_4um_k','brightness_11um_k',
                 'confidence_original','type']
        recs=[record('2024-03-31T10:00',9,-84.001,'MODIS','Terra'),
              record('2024-03-31T10:08',9,-83.999,'VIIRS','SNPP'),
              record('2024-03-31T11:00',9.6,-84.001,'MODIS','Terra'),
              record('2024-03-31T11:07',9.6005,-84.0008,'VIIRS','SNPP')]
        with (folder/'registros_normalizados_v2.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
            for rec in recs:
                w.writerow({'latitude':rec['lat'],'longitude':rec['lon'],
                'date_utc':rec['dt'].date().isoformat(),'time_utc':rec['dt'].strftime('%H:%M:%S'),
                'family':rec['family'],'platform':rec['platform'],'source':rec['source'],
                'daynight':'D','scan_km':rec['scan'],'track_km':rec['track'],
                'frp_mw':rec['frp'],'brightness_4um_k':rec['temp4'],
                'brightness_11um_k':rec['temp11'],'confidence_original':'n','type':'0'})
        out,meta=build(folder,window=15,force=True,h3_lib=fake)
        assert meta['scenarios']==33
        assert abs(meta['matched_square_side_km']**2-5.1)<1e-5
        assert len(meta['shift_summary'])==2
        assert meta['h3']['pares_con_vecinos']==2,meta['h3']
        assert (out/'escenarios.csv').is_file()
        assert len(list(csv.DictReader((out/'escenarios.csv').open(encoding='utf-8-sig'))))==33
        # API GET con H3 sintético: en memoria y carpeta temporal, NO modifica datos reales.
        import visor_incendios as viewer
        ds={'id':'Ficticia__2024','folder':folder,'year':2024,'region':'Ficticia','demo':True}
        with patch.object(viewer,'dataset_by_id',return_value=ds),patch.dict(sys.modules,{'h3':fake}):
            # backend usa h3_api(), que consulta sys.modules['h3'].
            server=ThreadingHTTPServer(('127.0.0.1',0),viewer.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            try:
                thread.start()
                url=f'http://127.0.0.1:{server.server_address[1]}/api/auditoria-espacial?id=Ficticia__2024&ventana=15'
                with urllib.request.urlopen(url,timeout=20) as resp:
                    answer=json.loads(resp.read())
                assert answer['metodo']=='auditoria_espacial_controlada_P4'
                assert answer['h3']['pares_con_vecinos']==2
                assert len(answer['resumen_desplazamientos'])==2
            finally:
                server.shutdown();server.server_close();thread.join(timeout=5)
    print('PASS P4: 33 escenarios, CSV, caché y endpoint HTTP sintéticos')


def test_real_square_baselines():
    root=Path(__file__).resolve().parent.parent/'resultados'/'resultados_armonizacion_v2'
    for region,expected in [('Costa_Rica',370),('Afghanistan',18)]:
        folder=root/region/'2024'
        if not (folder/'registros_normalizados_v2.csv').is_file():continue
        recs=records_from_normalized(folder,'todas')
        got=count_matches(recs,SquareAdapter(2),kind='cuadrado_2km',side_km=2,nominal_area=4)
        assert got['pares_estrictos_misma_celda']==expected,(region,got)
        print(f'PASS P4: {region} estrictas={expected} reproduce v2/P2; vecinos={got["pares_con_vecinos"]}')

if __name__=='__main__':
    tests_geometry();tests_pipeline();test_real_square_baselines()
    print('P4: PRUEBAS COMPLETAS. Los hexágonos reales requieren h3-py 4.x en Windows.')
