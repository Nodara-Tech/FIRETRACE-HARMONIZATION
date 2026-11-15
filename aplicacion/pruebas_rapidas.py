"""Comprobaciones locales de lectura y agrupación; ejecutar: py pruebas_rapidas.py"""
from visor_incendios import list_datasets,dataset_profile,day_records

xs=list_datasets()
assert any(d['id']=='Costa_Rica__2024' for d in xs)
assert any(d['id']=='Afghanistan__2024' for d in xs)
costa=next(d for d in xs if d['id']=='Costa_Rica__2024')
p=dataset_profile(costa)
assert p['diagnostic']['valid_total']==13941
assert p['diagnostic']['cell_day']['union']==6023
assert p['default_date']=='2024-03-31'
assert len(day_records(costa,'2024-03-31','points',False,['modis','viirs-snpp','viirs-jpss1'],'ambos')['features'])==628
assert len(day_records(costa,'2024-03-31','cells',False,[], 'ambos')['features'])==184
assert len(day_records(costa,'2024-03-31','pairs',False,[], 'ambos')['features'])==65
assert len(day_records(costa,'2024-03-31','points',False,[], 'ambos')['features'])==0
print('PRUEBAS CORRECTAS: 2 regiones, indicadores, puntos, celdas, parejas y filtro de fuentes.\nINDICE EN CACHE:', __import__('visor_incendios').sqlite_file(costa))
