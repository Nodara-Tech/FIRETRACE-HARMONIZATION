"""Pruebas P3 de integridad algorítmica, con H3 controlado SINTÉTICO.

NO reemplazan una comprobación con la librería oficial H3 ni crean
resultados científicos: los datos y celdas ficticios viven en TemporaryDirectory.
Ejecutar: py aplicacion\\pruebas_problema3.py
"""
from __future__ import annotations
import csv
import json
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import emparejamiento_h3_v3_4 as engine
import espacial_h3_v3 as spatial


class FakeH3:
    """API mínima SOLO para pruebas; NO es una implementación de H3."""
    __version__='synthetic-test-not-h3'
    def latlng_to_cell(self,lat,lon,res):
        if lat>9.5:return 'C'
        return 'A' if lon<-84 else 'B'
    def grid_disk(self,cell,k):
        return {'A':{'A','B'},'B':{'A','B'},'C':{'C'}}[cell]
    def cell_to_latlng(self,cell):
        return {'A':(9,-84.001),'B':(9,-83.999),'C':(9.6,-84.001)}[cell]
    def cell_to_boundary(self,cell):
        la,lo=self.cell_to_latlng(cell)
        return ((la,lo-.002),(la+.002,lo),(la,lo+.002),(la-.002,lo))
    def cell_area(self,cell,unit='km^2'):return 5.1
    def average_hexagon_area(self,res,unit='km^2'):return 5.1


def record(t,lat,lon,family,platform='Terra',scan=.5,track=.5):
    dt=datetime.fromisoformat(t)
    return {'dt':dt,'date':dt.date(),'lat':lat,'lon':lon,'family':family,
            'platform':platform,'source':'modis' if family=='MODIS' else 'viirs-snpp',
            'daynight':'D','scan':scan,'track':track,'frp':5.0,
            'temp11':300.0,'temp4':310.0,'confidence':'n'}


def test_candidates():
    h3=FakeH3()
    recs=[
        record('2024-03-31T10:00',9,-84.001,'MODIS','Terra'),
        record('2024-03-31T10:08',9,-83.999,'VIIRS','SNPP'),
        record('2024-03-31T11:00',9.6,-84.001,'MODIS','Terra'),
        record('2024-03-31T11:07',9.6005,-84.0008,'VIIRS','SNPP'),
        # Celda vecina pero lejana: H3 solo NO basta.
        record('2024-03-31T12:00',9,-84.04,'MODIS','Aqua'),
        record('2024-03-31T12:05',9,-83.999,'VIIRS','NOAA20'),
        # Tiempo >30 minutos, NO se permite aunque esté al lado.
        record('2024-03-31T14:00',9,-84.001,'MODIS','Aqua'),
        record('2024-03-31T14:40',9,-83.999,'VIIRS','SNPP'),
    ]
    passes=engine.build_passes_h3(recs,h3,7)
    candidates=engine.candidate_pairs_h3(passes,h3,120)
    p15=engine.assign_pairs(candidates,15)
    p30=engine.assign_pairs(candidates,30)
    p60=engine.assign_pairs(candidates,60)
    assert len(p15)==2 and len(p30)==2 and len(p60)==3, (len(p15),len(p30),len(p60))
    assert {p['relacion_h3'] for p in p15}=={'misma_celda','vecinas'}
    assert all(p['distancia_centroides_km']<=p['umbral_huella_aprox_km'] for p in p60)
    assert all(p['diferencia_min']<=60 for p in p60)
    assert not [p for p in p60 if p['plataforma_modis']=='Aqua' and p['plataforma_viirs']=='NOAA20']
    # Un MODIS y dos VIIRS cercanos: no se reutiliza MODIS con la misma plataforma.
    two=[record('2024-03-31T10:00',9,-84.001,'MODIS','Terra'),
         record('2024-03-31T10:03',9,-83.999,'VIIRS','SNPP'),
         record('2024-03-31T10:18',9,-83.9989,'VIIRS','SNPP')]
    matched=engine.assign_pairs(engine.candidate_pairs_h3(engine.build_passes_h3(two,h3),h3,120),30)
    assert len(matched)==1,matched
    print('PASS P3: H3 misma celda/vecina, umbral huella, tiempo, deduplicación 1:1')


def test_classification():
    h3=FakeH3()
    obs=[record('2024-03-31T10:00',9,-84.001,'MODIS'),
         record('2024-03-31T10:08',9,-83.999,'VIIRS','SNPP'),
         record('2024-03-31T11:00',9.6,-84.001,'MODIS'),
         record('2024-03-31T11:07',9.6005,-84.0008,'VIIRS','SNPP')]
    matches=engine.assign_pairs(engine.candidate_pairs_h3(engine.build_passes_h3(obs,h3),h3),15)
    presence={('2024-03-31','A'):'solo_modis',('2024-03-31','B'):'solo_viirs',('2024-03-31','C'):'ambos'}
    rows,days=engine.classify_presence(presence,matches,15)
    assert days[0]['ambos_diarios']==1
    assert days[0]['ambos_paso_cercano']==1
    assert days[0]['solo_modis_con_pareja_vecina']==1
    assert days[0]['solo_viirs_con_pareja_vecina']==1
    assert sum(r['clasificacion']=='ambos' for r in rows)==1
    print('PASS P3: no se confunden celdas vecinas con celdas compartidas')


def test_pipeline():
    h3=FakeH3()
    with tempfile.TemporaryDirectory(prefix='nodara_p3_synthetic_') as tmp:
        folder=Path(tmp)
        (folder/'diagnostico_v2.json').write_text(json.dumps({'anio':2024,'pais':'Costa Rica',
                    'parameters':{'grid_km':2,'quality':'todas'}}),encoding='utf-8')
        names=['latitude','longitude','date_utc','time_utc','family','platform','source','daynight',
               'scan_km','track_km','frp_mw','brightness_4um_k','brightness_11um_k',
               'confidence_original','type']
        recs=[record('2024-03-31T10:00',9,-84.001,'MODIS','Terra'),
              record('2024-03-31T10:08',9,-83.999,'VIIRS','SNPP'),
              record('2024-03-31T11:00',9.6,-84.001,'MODIS','Terra'),
              record('2024-03-31T11:07',9.6005,-84.0008,'VIIRS','SNPP')]
        with (folder/'registros_normalizados_v2.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=names);writer.writeheader()
            for r in recs:
                writer.writerow({'latitude':r['lat'],'longitude':r['lon'],'date_utc':r['dt'].date().isoformat(),
                    'time_utc':r['dt'].strftime('%H:%M:%S'),'family':r['family'],
                    'platform':r['platform'],'source':r['source'],'daynight':r['daynight'],
                    'scan_km':r['scan'],'track_km':r['track'],'frp_mw':r['frp'],
                    'brightness_4um_k':r['temp4'],'brightness_11um_k':r['temp11'],
                    'confidence_original':r['confidence'],'type':'0'})
        # El motor real usa espacial_h3_v3.h3_api() y este archivo de prueba
        # reemplaza H3 SOLO en el proceso del test y en directorio temporal.
        with patch.object(spatial,'h3_api',return_value=h3),patch.object(engine,'h3_api',return_value=h3):
            out,diag=engine.build(folder,7,force=True)
            assert diag['summary'][0]['parejas_candidatas']==2,diag['summary'][0]
            assert diag['summary'][0]['parejas_vecinas']==1
            assert diag['summary'][0]['parejas_misma_celda']==1
            assert diag['summary'][0]['celdas_dia_ambos']==1
            assert (out/'h3_concordancia_diaria.csv').is_file()
            import visor_incendios as viewer
            from unittest.mock import patch as mp
            # Los endpoints reales del visor reciben datos FICTICIOS H3
            # solo en esta prueba; jamás se guardan al proyecto.
            fake_ds={'id':'Ficticia__2024','folder':folder,'year':2024,
                     'region':'Costa Rica','demo':True}
            with mp.dict(sys.modules,{'h3':h3}),mp.object(viewer,'dataset_by_id',return_value=fake_ds):
                server=ThreadingHTTPServer(('127.0.0.1',0),viewer.Handler)
                t=threading.Thread(target=server.serve_forever,daemon=True)
                try:
                    t.start()
                    base=f'http://127.0.0.1:{server.server_address[1]}'
                    url='?id=Ficticia__2024&fecha=2024-03-31&metodo=h3&ventana=15'
                    def request(path):
                        with urllib.request.urlopen(base+path,timeout=15) as resp:
                            return json.loads(resp.read())
                    cells=request('/api/dia'+url+'&modo=cells')
                    pairs=request('/api/dia'+url+'&modo=pairs')
                    temporal=request('/api/temporal'+url)
                    con=request('/api/concordancia'+url)
                    assert len(cells['features'])==3,len(cells['features'])
                    assert len(pairs['features'])==2,len(pairs['features'])
                    assert con['metodo_concordancia']=='H3_r7_temporal'
                    assert con['ambos_diarios']==1
                    assert con['celdas']['solo_modis_con_pareja_vecina']==1
                    assert con['celdas']['solo_viirs_con_pareja_vecina']==1
                    assert temporal['escenarios'][0]['global']['parejas_candidatas']==2
                    assert {p['relation_h3'] for p in pairs['features']}=={'misma_celda','vecinas'}
                finally:
                    server.shutdown();server.server_close();t.join(timeout=5)
    print('PASS P3: pipeline + endpoints HTTP H3 sintéticos; sin alterar datos reales')


if __name__=='__main__':
    test_candidates();test_classification();test_pipeline()
    print('P3: PRUEBAS UNITARIAS COMPLETAS. PENDIENTE ejecución con h3-py 4.x oficial en Windows.')
