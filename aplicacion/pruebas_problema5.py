"""Pruebas P5 sin biblioteca h3 oficial (H3 SINTÉTICO). No validar exactitud."""
from __future__ import annotations
import csv
import json
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from pruebas_problema3 import FakeH3,record
from comparacion_espacial_v3_5 import SquareAdapter
from calidad_detecciones_v3_6 import accept,build,read_rows,status,SCENARIOS


def test_quality_flags():
    r=record('2024-03-31T10:00',9,-84,'MODIS')
    r['confidence']='50'; assert status(r)==50 and accept(r,'modis50')
    r['confidence']='49'; assert not accept(r,'modis50') and accept(r,'viirs_nh')
    r['confidence']=''; assert not accept(r,'modis50') and accept(r,'todas')
    r['confidence']='101'; assert status(r) is None and not accept(r,'modis80')
    r['family']='VIIRS';r['confidence']='l';assert not accept(r,'viirs_nh') and accept(r,'modis50')
    r['confidence']='h';assert accept(r,'viirs_nh')
    r['confidence']='n';assert accept(r,'ambos50')
    r['confidence']='desconocido';assert not accept(r,'viirs_nh')
    assert len(SCENARIOS)==6
    print('PASS P5: reglas independientes, fronteras 50/80, valores desconocidos')


def fixture(temp):
    f=Path(temp)
    (f/'diagnostico_v2.json').write_text(json.dumps({'pais':'Ficticia','anio':2024,
        'parameters':{'grid_km':2,'quality':'todas','pass_window_minutes':30}}),encoding='utf-8')
    fields=['latitude','longitude','date_utc','time_utc','family','platform','source','daynight',
      'scan_km','track_km','frp_mw','brightness_4um_k','brightness_11um_k','confidence_original','type']
    events=[
      (record('2024-03-31T10:00',9,-84.001,'MODIS','Terra'),'85','0'),
      (record('2024-03-31T10:08',9,-83.999,'VIIRS','SNPP'),'l','0'),
      (record('2024-03-31T11:00',9.6,-84.001,'MODIS','Terra'),'45','0'),
      (record('2024-03-31T11:07',9.6005,-84.0008,'VIIRS','SNPP'),'n','0'),
      (record('2024-03-31T12:00',9.6,-84.001,'MODIS','Aqua'),'60','1'),
    ]
    with (f/'registros_normalizados_v2.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        w=csv.DictWriter(handle,fieldnames=fields);w.writeheader()
        for r,quality,typ in events:
            w.writerow({'latitude':r['lat'],'longitude':r['lon'],'date_utc':r['dt'].date().isoformat(),
               'time_utc':r['dt'].strftime('%H:%M:%S'),'family':r['family'],
               'platform':r['platform'],'source':r['source'],'daynight':r['daynight'],
               'scan_km':r['scan'],'track_km':r['track'],'frp_mw':r['frp'],
               'brightness_4um_k':r['temp4'],'brightness_11um_k':r['temp11'],
               'confidence_original':quality,'type':typ})
    return f


def test_pipeline_and_api():
    fake=FakeH3()
    with tempfile.TemporaryDirectory(prefix='nodara_p5_synthetic_') as tmp:
        folder=fixture(tmp)
        out,d=build(folder,window=30,force=True,h3_lib=fake)
        assert len(d['escenarios'])==6 and d['registros_type0']==4
        data={r['escenario']:r for r in d['escenarios']}
        assert data['todas']['registros_type0']==4
        assert data['viirs_nh']['registros_type0']==3
        assert data['modis50']['registros_type0']==3
        assert data['ambos50']['registros_type0']==2
        assert data['modis80']['registros_type0']==3
        assert data['ambos80']['registros_type0']==2
        assert data['todas']['h3']['parejas']==2
        assert data['viirs_nh']['h3']['parejas']==1
        assert data['modis50']['h3']['parejas']==1
        assert data['ambos50']['h3']['parejas']==0
        assert data['todas']['cuadricula']['parejas']<=2
        assert data['todas']['h3']['ambos_con_pareja']<=data['todas']['h3']['ambos']
        assert (out/'escenarios_calidad.csv').is_file()
        assert len(list(read_rows(out/'escenarios_calidad.csv')))==12
        assert len(list(read_rows(out/'calendario_calidad.csv')))==6*2*366
        # Endpoint HTTP con FakeH3: calidad se consulta independientemente de la geometría del mapa.
        import visor_incendios as viewer
        import calidad_detecciones_v3_6 as engine
        dataset={'id':'Ficticia__2024','folder':folder,'year':2024,'region':'Ficticia','demo':True}
        with patch.object(viewer,'dataset_by_id',return_value=dataset), patch.object(engine,'h3_api',return_value=fake):
            server=ThreadingHTTPServer(('127.0.0.1',0),viewer.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            try:
                thread.start()
                url=f'http://127.0.0.1:{server.server_address[1]}/api/auditoria-calidad?id=Ficticia__2024&fecha=2024-03-31&ventana=30'
                with urllib.request.urlopen(url,timeout=20) as req:
                    result=json.loads(req.read())
                assert len(result['escenarios'])==6
                assert result['diarios']['todas']['h3']['parejas']==2
                assert result['distribucion']['viirs-snpp']['l']==1
                assert result['registros_type0']==4
                assert result['fecha_utc']=='2024-03-31'
            finally:
                server.shutdown();server.server_close();thread.join(timeout=5)
    print('PASS P5: filtros antes de pasadas; 6 escenarios, CSV, caché y HTTP sintéticos')


def test_real_square_baselines():
    root=Path(__file__).resolve().parent.parent/'resultados'/'resultados_armonizacion_v2'
    for region,expect,nrec,near in [('Costa_Rica',370,13836,313),('Afghanistan',18,1169,17)]:
        folder=root/region/'2024'
        if not (folder/'registros_normalizados_v2.csv').exists():continue
        out,d=build(folder,window=30,force=True,h3_lib=SquareAdapter(2))
        base=d['escenarios'][0]
        assert d['registros_type0']==nrec
        assert base['cuadricula']['parejas']==expect
        assert base['cuadricula']['ambos_con_pareja']==near
        assert d['escenarios'][1]['registros_type0']<=nrec
        print('PASS P5:',region,'cuadrados=',expect,'celdas próximas=',near,'VIIRS sin l=',d['escenarios'][1]['cuadricula']['parejas'])
    print('NOTA: Las cifras H3 de esta prueba usan un ADAPTADOR SIMULADO de cuadrados, NO H3 real.')

if __name__=='__main__':
    test_quality_flags();test_pipeline_and_api();test_real_square_baselines()
    print('P5: PRUEBAS DE SOFTWARE COMPLETAS. Ejecuta pruebas_problema5_reales.py en Windows.')
