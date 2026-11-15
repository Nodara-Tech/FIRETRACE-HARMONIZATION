"""Pruebas de integración FIRETRACE sin datos simulados ni servicio externo.
No reemplaza las cinco auditorías estadísticas originales v3.6.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'aplicacion'))
import visor_incendios as v
from firetrace_api import build_range

def run():
    datasets=v.list_datasets()
    assert datasets,'No se encontraron resultados procesados'
    for d in datasets:
        year=d['year'];start=f'{year}-01-01';end=f'{year}-12-31'
        r=build_range(d,{'desde':start,'hasta':end,'metodo':'square','limite':'100'},v.ensure_index)
        s=r['summary'];assert r['range']['days'] in (365,366)
        assert sum(x['total'] for x in r['daily'])==s['detections']
        assert sum(x['cell_days'] for x in r['daily'])==s['cell_days']
        assert sum(x['both_cell_days'] for x in r['daily'])==s['both_cell_days']
        assert 0<=s['cooccurrence_pct']<=100
        assert all(x['total']==x['modis']+x['viirs'] for x in r['daily'])
        no_sources=build_range(d,{'desde':start,'hasta':end,'fuentes':''},v.ensure_index)
        assert no_sources['summary']['detections']==0 and no_sources['features']==[]
        print('PASS',d['id'],s['detections'],'detecciones;',s['cell_days'],'celdas-día;',s['multisource_cells'],'celdas multisensor')
    cr=next((x for x in datasets if x['id']=='Costa_Rica__2024'),None)
    if cr:
        x=build_range(cr,{'desde':'2024-03-31','hasta':'2024-03-31','modo':'cells'},v.ensure_index)
        assert x['summary']['detections']==628,(x['summary']['detections'],628)
        assert x['summary']['cell_days']==184
        assert x['summary']['both_cell_days']==51
        print('PASS 2024-03-31: 628 detecciones, 184 celdas, 51 celdas compartidas')
    static=Path(__file__).resolve().parent/'aplicacion'/'web'
    for name in ('firetrace.html','firetrace.css','firetrace.js','firetrace-logo.png','index.html','styles.css','app.js'):
        assert (static/name).stat().st_size>100,name
    print('PASS HOME + HARMONIZATION nuevos y observatorio técnico v3.6 intacto')
    # Smoke test real del servidor, incluyendo el filtro vacío (ningún satélite).
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.request import urlopen
    from urllib.parse import urlencode
    import json
    server=ThreadingHTTPServer(('127.0.0.1',0),v.Handler)
    worker=Thread(target=server.serve_forever,daemon=True);worker.start()
    base=f'http://127.0.0.1:{server.server_address[1]}'
    try:
        for route in ('/','/observatorio','/firetrace.css','/firetrace.js','/firetrace-logo.png'):
            with urlopen(base+route,timeout=10) as resp:
                assert resp.status==200 and len(resp.read())>100
        if cr:
            p=urlencode({'id':cr['id'],'desde':'2024-03-31','hasta':'2024-03-31',
                         'metodo':'square','fuentes':''})
            with urlopen(base+'/api/firetrace/rango?'+p,timeout=12) as resp:
                empty=json.load(resp)
            assert empty['summary']['detections']==0, 'No deben aparecer puntos con los satélites desactivados'
            p=urlencode({'id':cr['id'],'desde':'2024-03-31','hasta':'2024-03-31','metodo':'square'})
            with urlopen(base+'/api/firetrace/rango?'+p,timeout=12) as resp:
                day=json.load(resp)
            assert day['summary']['detections']==628
        print('PASS HTTP: HOME, HARMONIZATION, archivos estáticos, filtros vacíos y registros reales')
    finally:
        server.shutdown();server.server_close();worker.join(timeout=3)
    print('PRUEBAS FIRETRACE COMPLETAS. H3 oficial se comprueba con pruebas_problema5_reales.py')
if __name__=='__main__':run()
