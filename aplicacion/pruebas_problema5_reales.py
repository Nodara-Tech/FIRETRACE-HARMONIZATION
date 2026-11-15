"""Comprobación P5 con H3 OFICIAL en Windows y NASA FIRMS reales (no verdad terreno)."""
from pathlib import Path
from calidad_detecciones_v3_6 import build,read_rows
from emparejamiento_h3_v3_4 import build as p3_build
from espacial_h3_v3 import h3_api

h3=h3_api()
print('H3 oficial:',getattr(h3,'__version__','4.x'))
root=Path(__file__).resolve().parent.parent/'resultados'/'resultados_armonizacion_v2'
for region,square_expected,h3_expected,records_expected in [
    ('Costa_Rica',370,452,13836),('Afghanistan',18,19,1169)]:
    f=root/region/'2024'
    if not (f/'registros_normalizados_v2.csv').is_file():
        print('Conjunto no encontrado:',region,'(se omite)');continue
    # Compara con la versión P3 basada en exactamente las mismas observaciones.
    _,old=p3_build(f,7)
    p3=next(r for r in old['summary'] if int(r['ventana_min'])==30)['parejas_candidatas']
    assert int(p3)==h3_expected,(region,p3,h3_expected)
    out,info=build(f,window=30,force=True)
    rows={r['escenario']:r for r in info['escenarios']}
    base=rows['todas']
    assert info['registros_type0']==records_expected
    assert base['cuadricula']['parejas']==square_expected
    assert base['h3']['parejas']==h3_expected,(region,base['h3']['parejas'],h3_expected)
    assert len(rows)==6
    assert base['h3']['pares_misma_celda']+base['h3']['pares_vecinos']==h3_expected
    assert all(r['registros_type0']<=records_expected for r in rows.values())
    print(f'PASS {region}: {records_expected} type=0; cuadrados={square_expected}; H3={h3_expected}; seis escenarios')
    for name,r in rows.items():
        print(f"  {name:>10} | registros {r['registros_type0']:5} | cuadrados {r['cuadricula']['parejas']:4} | H3 {r['h3']['parejas']:4} | compartidas H3 {r['h3']['ambos']:4}")
    if region=='Costa_Rica':
        assert rows['viirs_nh']['registros_type0']==12182
        days=[r for r in read_rows(out/'calendario_calidad.csv') if r['fecha_utc']=='2024-03-31' and r['escenario']=='todas']
        bymethod={r['metodo']:r for r in days}
        assert int(bymethod['square']['parejas'])==65
        assert int(bymethod['h3']['parejas'])==80
        print('  PASS 31/03/2024: cuadrícula=65, H3=80, sin filtros')
    print('  CSV:',out/'escenarios_calidad.csv')
print('Verificación de software H3 real completa. NO demuestra mejora en exactitud ni equivale a probabilidades.')
