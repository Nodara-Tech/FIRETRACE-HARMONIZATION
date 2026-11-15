"""Prueba de P4 con h3-py REAL + datos NASA; no sustituye validación externa."""
from pathlib import Path
from comparacion_espacial_v3_5 import build
from emparejamiento_h3_v3_4 import build as p3_build
from espacial_h3_v3 import h3_api

root=Path(__file__).resolve().parent.parent/'resultados'/'resultados_armonizacion_v2'
h3=h3_api()
print('H3 oficial',getattr(h3,'__version__','4.x'))
for region in ('Costa_Rica','Afghanistan'):
    folder=root/region/'2024'
    if not (folder/'registros_normalizados_v2.csv').is_file():
        print('No se encontró el conjunto:',region,'(se omite)');continue
    _,p3=p3_build(folder,7)
    expected=next(r for r in p3['summary'] if r['ventana_min']==30)['parejas_candidatas']
    path,p4=build(folder,window=30,force=True)
    actual=p4['h3']['pares_con_vecinos']
    assert actual==expected,(region,actual,expected)
    assert p4['scenarios']==33
    print('PASS:',region,'H3 real',actual,'parejas; coincide v3.4 original:',expected)
    print('  Cuadrado equivalente:',p4['matched_square_side_km'],'km, 16 desplazamientos')
    for group in p4['shift_summary']:
        p=group['pares_con_vecinos']
        print(' ',group['metodo'],p['min'],'a',p['max'],'(media',p['media'],')')
    print('  Exportación:',path/'escenarios.csv')
print('La prueba valida consistencia numérica y software; NO sensibilidad ni exactitud científica.')
