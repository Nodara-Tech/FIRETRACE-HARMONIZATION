"""Nodara v3.5 (P4) — comparación de sensibilidad espacial, no de exactitud.

La comparación anterior 370 (cuadrícula v2) vs 452 (H3 temporal v3.4)
NO está controlada: las áreas, las vecindades y algunas reglas de agrupación
son distintas. Este módulo usa EXACTAMENTE el mismo agrupador de pasadas,
la misma geometría aproximada de huellas, la misma ventana y la misma
asignación greedy 1:1 por par de plataformas para todos los escenarios.

Escenarios: H3 r7, cuadrados con 2 km y cuadrados de área nominal equivalente
al hexágono H3 promedio global. Se desplaza el origen de cada cuadrícula
16 veces (4x4), sin desplazar las coordenadas de los satélites.

Comparaciones separadas: solo MISMA CELDA y MISMA + VECINDAD (k1 H3 = 6;
cuadrados = 8). Se informa la geometría y las diferencias de topología;
NO se afirma equivalencia total de los algoritmos ni precisión.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from threading import RLock

from espacial_h3_v3 import h3_api
from armonizar_firms_v2 import projection
from sensibilidad_temporal_v3_3 import records_from_normalized, WINDOWS
from emparejamiento_h3_v3_4 import (build_passes_h3, candidate_pairs_h3,
                                     assign_pairs, write_csv)

VERSION='3.5-P4-FULL-SAME-ENGINE'
FOLDER='comparacion_espacial_v3_5'
OFFSETS=(0.0,0.25,0.5,0.75)
H3_RES=7
DEFAULT_WINDOW=30
LOCK=RLock()


class SquareAdapter:
    """Compatible con el motor de P3; proyección cilíndrica equivalente de v2.

    La cuadrícula es de AREA CONSTANTE en la esfera bajo la proyección de v2.
    La etiqueta del id tiene forma (ix,iy), sin asumir un desplazamiento real.
    """
    def __init__(self, side_km, offset_x=0., offset_y=0.):
        if side_km<=0 or not math.isfinite(side_km):
            raise ValueError('Lado de cuadrícula inválido')
        self.km=float(side_km)
        self.x=float(offset_x)
        self.y=float(offset_y)

    def latlng_to_cell(self,lat,lon,resolution):
        xx,yy=projection(lat,lon)
        return (math.floor(xx/self.km+self.x),math.floor(yy/self.km+self.y))

    @staticmethod
    def grid_disk(cell,k):
        if k!=1:raise ValueError('Solo vecindad k=1 en comparación')
        x,y=cell
        return [(x+i,y+j) for i in (-1,0,1) for j in (-1,0,1)]


def count_presence(records,indexer):
    seen=defaultdict(int)
    for r in records:
        cell=indexer.latlng_to_cell(r['lat'],r['lon'],H3_RES)
        key=(r['dt'].date().isoformat(),cell)
        seen[key] |= 1 if r['family']=='MODIS' else 2
    return seen


def count_matches(records,adapter,*,window=30,kind='',side_km=None,offset_x=None,offset_y=None,nominal_area=None):
    """Compone las MISMAS rutinas de P3 para ambos tipos de celdas.

    Matching interno y con vecinos SE RECALCULA por separado con asignación
    1:1. La diferencia de recuentos no es número de incendios adicionales.
    """
    pres=count_presence(records,adapter)
    active=len(pres)
    both=sum(v==3 for v in pres.values())
    modis=sum(bool(v&1) for v in pres.values())
    viirs=sum(bool(v&2) for v in pres.values())
    passes=build_passes_h3(records,adapter,H3_RES)
    candidates=candidate_pairs_h3(passes,adapter,maximum_minutes=window)
    only_inside={key:[v for v in vals if v[-1]=='misma_celda'] for key,vals in candidates.items()}
    same=assign_pairs(only_inside,window)
    all_neighbors=assign_pairs(candidates,window)
    same_cells={(p['fecha_utc'],p['celda_h3_modis']) for p in same}
    with_neighbors={(p['fecha_utc'],p['celda_h3_modis']) for p in all_neighbors}
    # Separar pares que cruzan celdas del conteo de celdas "ambos".
    cells_both_near={key for key in with_neighbors if pres.get(key)==3}
    n_neighbor=sum(p['relacion_h3']=='vecinas' for p in all_neighbors)
    return {'metodo':kind,'lado_km':round(side_km,6) if side_km else '',
       'area_nominal_km2':round(nominal_area,7) if nominal_area else '',
       'offset_x':offset_x if offset_x is not None else '',
       'offset_y':offset_y if offset_y is not None else '',
       'ventana_min':window,'registros':len(records),'pasadas':len(passes),
       'celdas_dia_activas':active,'celdas_dia_ambos':both,
       'celdas_dia_solo_modis':modis-both,'celdas_dia_solo_viirs':viirs-both,
       'pares_estrictos_misma_celda':len(same),
       'pares_con_vecinos':len(all_neighbors),
       'pares_misma_celda_con_vecinos':len(all_neighbors)-n_neighbor,
       'pares_entre_vecinos':n_neighbor,
       'celdas_ambos_con_pareja_estricta':sum(pres.get(p)==3 for p in same_cells),
       'celdas_ambos_con_pareja_vecinos':len(cells_both_near),
       'proporcion_ambos_con_pareja_vecinos':round(len(cells_both_near)/both,5) if both else 0,
       'advertencia':'conteos de detecciones no precision; vecinos k1=6 H3,8 cuadrados'}


COLUMNS=['metodo','lado_km','area_nominal_km2','offset_x','offset_y','ventana_min','registros','pasadas',
         'celdas_dia_activas','celdas_dia_ambos','celdas_dia_solo_modis','celdas_dia_solo_viirs',
         'pares_estrictos_misma_celda','pares_con_vecinos','pares_misma_celda_con_vecinos',
         'pares_entre_vecinos','celdas_ambos_con_pareja_estricta','celdas_ambos_con_pareja_vecinos',
         'proporcion_ambos_con_pareja_vecinos','advertencia']


def summarize_shifts(rows,method):
    entries=[r for r in rows if r['metodo']==method]
    output={'metodo':method,'n_desplazamientos':len(entries),'lado_km':entries[0]['lado_km']}
    for col in ('celdas_dia_activas','celdas_dia_ambos','pares_estrictos_misma_celda',
                'pares_con_vecinos','celdas_ambos_con_pareja_vecinos'):
        vals=[r[col] for r in entries]
        output[col]={'min':min(vals),'max':max(vals), 'media':round(statistics.mean(vals),3),
                     'mediana':statistics.median(vals),
                     'desv_estandar':round(statistics.pstdev(vals),3),
                     'rango':max(vals)-min(vals)}
    return output


def fingerprint(source,diag,window,offsets):
    return hashlib.sha256(repr((VERSION,window,offsets,
      [(p.name,p.stat().st_size,p.stat().st_mtime_ns) for p in (source,diag)])).encode()).hexdigest()[:20]


def build(folder,*,window=DEFAULT_WINDOW,force=False,h3_lib=None):
    folder=Path(folder).resolve();window=int(window)
    if window not in WINDOWS: raise ValueError('Ventana debe ser 15,30,60 o 120')
    src=folder/'registros_normalizados_v2.csv'; diagf=folder/'diagnostico_v2.json'
    if not (src.exists() and diagf.exists()):raise FileNotFoundError(f'Faltan fuente o diagnóstico en {folder}')
    h3=h3_lib if h3_lib is not None else h3_api()
    sig=fingerprint(src,diagf,window,OFFSETS) + '-' + str(getattr(h3,'__version__','4.x')).replace('.', '_')
    out=folder/FOLDER/f't_{window}min'
    manifest=out/'diagnostico_p4.json'
    required=(out/'escenarios.csv',out/'resumen_desplazamientos.csv',manifest)
    def read_cache():
        if not force and all(p.is_file() for p in required):
            try:
                res=json.loads(manifest.read_text(encoding='utf-8'))
                if res.get('signature')==sig:return res
            except (ValueError,OSError): pass
        return None
    cached=read_cache()
    if cached:return out,cached
    with LOCK:
        cached=read_cache()
        if cached:return out,cached
        diag=json.loads(diagf.read_text(encoding='utf-8-sig'))
        quality=diag.get('parameters',{}).get('quality','todas')
        records=records_from_normalized(folder,quality)
        area=float(h3.average_hexagon_area(H3_RES,unit='km^2'))
        square_match=math.sqrt(area)
        rows=[]
        # Una ejecución de H3 frente a 16 orígenes de cada cuadrícula.
        rows.append(count_matches(records,h3,window=window,kind='h3_r7',nominal_area=area))
        for method,side in [('cuadrado_2km',2.0),('cuadrado_area_H3',square_match)]:
            for ox in OFFSETS:
                for oy in OFFSETS:
                    adapter=SquareAdapter(side,ox,oy)
                    rows.append(count_matches(records,adapter,window=window,kind=method,
                           side_km=side,offset_x=ox,offset_y=oy,nominal_area=side*side))
        assert len(rows)==33
        assert all(r['registros']==len(records) for r in rows)
        assert all(r['pares_entre_vecinos']<=r['pares_con_vecinos'] for r in rows)
        assert all(r['celdas_ambos_con_pareja_vecinos']<=r['celdas_dia_ambos'] for r in rows)
        shift_summ=[summarize_shifts(rows,m) for m in ('cuadrado_2km','cuadrado_area_H3')]
        meta={'version':VERSION,'signature':sig,'pais':diag.get('pais'),'anio':diag.get('anio'),
          'h3_api':getattr(h3,'__version__','4.x'),'h3_resolution':H3_RES,
          'window':window,'records_used':len(records),
          'h3_average_cell_area_km2':round(area,7),
          'matched_square_side_km':round(square_match,7),
          'matched_square_area_km2':round(square_match*square_match,7),
          'baseline_square_side_km':2.0,'square_offsets':list(OFFSETS),
          'scenarios':len(rows),'h3':rows[0],
          'square_2km_origin':next(r for r in rows if r['metodo']=='cuadrado_2km' and r['offset_x']==0 and r['offset_y']==0),
          'square_matched_origin':next(r for r in rows if r['metodo']=='cuadrado_area_H3' and r['offset_x']==0 and r['offset_y']==0),
          'shift_summary':shift_summ,
          'scientific_limitations':[
             'El area de H3 reportada es media GLOBAL; las areas concretas varian por celda.',
             'Emparejador y tolerancia temporal/huella iguales; 6 vecinos hexagonales y 8 cuadrados no tienen misma topologia.',
             'Las pasadas se agregan dentro de cada celda: los objetos agrupados pueden variar con la particion.',
             'El matching es greedy 1:1, no maximo exacto ni verdad terreno.',
             'No se suman areas de celdas ocupadas como area quemada.',
             'Los rangos por desplazamiento describen sensibilidad al origen, NO intervalos de confianza ni precision.',
             'No se prueba superioridad de H3 ni equivalencia radiometrica; faltan mascaras y datos de referencia.'
          ]}
        out.mkdir(parents=True,exist_ok=True)
        write_csv(out/'escenarios.csv',rows,COLUMNS)
        summary_rows=[]
        for s in shift_summ:
            for metric,values in s.items():
                if not isinstance(values,dict):continue
                summary_rows.append({'metodo':s['metodo'],'n_desplazamientos':s['n_desplazamientos'],
                     'lado_km':s['lado_km'],'indicador':metric,**values})
        write_csv(out/'resumen_desplazamientos.csv',summary_rows,
                  ['metodo','n_desplazamientos','lado_km','indicador','min','max','media','mediana','desv_estandar','rango'])
        manifest.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        return out,meta


def main():
    parser=argparse.ArgumentParser(description='Comparación espacial v3.5 H3 vs cuadrados (P4)')
    parser.add_argument('--carpeta',type=Path,required=True)
    parser.add_argument('--ventana',type=int,default=30,choices=WINDOWS)
    parser.add_argument('--forzar',action='store_true')
    args=parser.parse_args()
    out,meta=build(args.carpeta,window=args.ventana,force=args.forzar)
    print('P4 OK',out,'| biblioteca H3',meta['h3_api'])
    print('H3 (misma celda / con vecinos):',meta['h3']['pares_estrictos_misma_celda'], '/', meta['h3']['pares_con_vecinos'])
    for s in meta['shift_summary']:
        print(s['metodo'],'lado=',s['lado_km'], 'km, 16 desplazamientos')
        for name in ('celdas_dia_ambos','pares_estrictos_misma_celda','pares_con_vecinos'):
            print('  ',name,':',s[name]['min'],'–',s[name]['max'],'; media',s[name]['media'])
    print('No mide exactitud, sensibilidad/especificidad ni probabilidad de incendio.')

if __name__=='__main__':main()
