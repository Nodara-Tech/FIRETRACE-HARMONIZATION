"""Nodara Tech — herramienta unificada de NASA FIRMS para Estados Unidos.

Integración automática de los módulos existentes:
* descargar_firms_interactivo.py: descargas oficiales por país o ZIP anual.
* armonizar_firms_v2.py: análisis aproximado por celda/día y pasadas.
* nodara_usa.py: asignación de detecciones al estado con límites del US Census.

Ejecución:
  py -m pip install pyshp
  py nodara_usa.py
  py nodara_usa.py ejecutar --estado California --anios 2024
  py nodara_usa.py ejecutar --estado Texas --anios 2015,2020,2024
  py nodara_usa.py analizar --estado California --anios 2000,2005,2024
  py nodara_usa.py analizar --estado Texas --anios 2024 --cuadricula 5
  py nodara_usa.py analizar --estado TODOS --anios 2024

IMPORTANTE: indicadores de detecciones, NO incendios confirmados ni hectáreas quemadas.
No hay calibración histórica ni corrección de nubosidad/cobertura.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.request
import zipfile
from contextlib import ExitStack
from pathlib import Path

import armonizar_firms_v2 as motor
import descargar_firms_interactivo as nasa

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'datos' / 'datos_firms'
STATE_DATA = ROOT / 'datos' / 'datos_firms_estados'
RESULTS = ROOT / 'resultados' / 'resultados_estados_unidos'
GEOGRAPHY = ROOT / 'datos' / 'limites_geograficos'
BOUNDARY_FILENAME = 'cb_2024_us_state_500k.zip'
BOUNDARY_URL = 'https://www2.census.gov/geo/tiger/GENZ2024/shp/' + BOUNDARY_FILENAME
SENSORS = ('modis', 'viirs-snpp', 'viirs-jpss1')

# 50 estados y el Distrito de Columbia (no territorios).
US_STATES = {
 'AL':'Alabama', 'AK':'Alaska', 'AZ':'Arizona', 'AR':'Arkansas', 'CA':'California',
 'CO':'Colorado', 'CT':'Connecticut', 'DE':'Delaware', 'FL':'Florida', 'GA':'Georgia',
 'HI':'Hawaii', 'ID':'Idaho', 'IL':'Illinois', 'IN':'Indiana', 'IA':'Iowa', 'KS':'Kansas',
 'KY':'Kentucky', 'LA':'Louisiana', 'ME':'Maine', 'MD':'Maryland', 'MA':'Massachusetts',
 'MI':'Michigan', 'MN':'Minnesota', 'MS':'Mississippi', 'MO':'Missouri', 'MT':'Montana',
 'NE':'Nebraska', 'NV':'Nevada', 'NH':'New Hampshire', 'NJ':'New Jersey',
 'NM':'New Mexico', 'NY':'New York', 'NC':'North Carolina', 'ND':'North Dakota',
 'OH':'Ohio', 'OK':'Oklahoma', 'OR':'Oregon', 'PA':'Pennsylvania', 'RI':'Rhode Island',
 'SC':'South Carolina', 'SD':'South Dakota', 'TN':'Tennessee', 'TX':'Texas',
 'UT':'Utah', 'VT':'Vermont', 'VA':'Virginia', 'WA':'Washington',
 'WV':'West Virginia', 'WI':'Wisconsin', 'WY':'Wyoming',
 'DC':'District of Columbia'
}


def parse_years(text: str) -> list[int]:
    years = set()
    for part in text.replace(' ', '').split(','):
        if not part:
            raise ValueError('Formato de años incorrecto: usa 2000,2005,2020-2024')
        if '-' in part:
            a, b = part.split('-', 1)
            a, b = int(a), int(b)
            if not 2000 <= a <= b <= 2100:
                raise ValueError('Rango de años inválido')
            years.update(range(a, b + 1))
        else:
            y = int(part)
            if not 2000 <= y <= 2100:
                raise ValueError('Año fuera de rango')
            years.add(y)
    if not years:
        raise ValueError('Se necesita un año')
    return sorted(years)


def slug(name: str) -> str:
    return re.sub(r'[^A-Za-z0-9_]', '', name.replace(' ', '_'))


def resolve_state(value: str) -> str:
    if value.upper() == 'TODOS':
        return 'TODOS'
    if value.upper() in US_STATES:
        return US_STATES[value.upper()]
    for name in US_STATES.values():
        if motor.keytext(value) == motor.keytext(name):
            return name
    raise ValueError(f"Estado no reconocido: {value}. Usa 'estados' para ver los nombres.")


def download_boundaries() -> Path:
    GEOGRAPHY.mkdir(parents=True, exist_ok=True)
    local = GEOGRAPHY / BOUNDARY_FILENAME
    if local.exists() and zipfile.is_zipfile(local):
        return local
    print('Descargando límites de los estados desde US Census Bureau...')
    print('  Fuente:', BOUNDARY_URL)
    tmp = local.with_suffix('.part')
    try:
        request = urllib.request.Request(BOUNDARY_URL, headers={'User-Agent':'NodaraTech-Prototipo/1.0'})
        with urllib.request.urlopen(request, timeout=90) as response, tmp.open('wb') as w:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                w.write(block)
        if not zipfile.is_zipfile(tmp):
            raise ValueError('La respuesta no contiene un ZIP válido')
        tmp.replace(local)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError('No se pudieron descargar los límites geográficos. Descarga manualmente '
            + BOUNDARY_URL + f' y guarda el ZIP en: {local} | Error: {exc}') from exc
    return local


def read_boundaries(path: Path | None = None) -> dict:
    try:
        import shapefile
    except ImportError as exc:
        raise RuntimeError('Falta pyshp. Ejecuta: py -m pip install pyshp') from exc
    path = path or download_boundaries()
    if not path.exists():
        raise RuntimeError(f'No existe el archivo de límites: {path}')
    with zipfile.ZipFile(path) as z:
        members = {Path(name).suffix.lower(): name for name in z.namelist() if Path(name).suffix.lower() in ('.shp','.shx','.dbf')}
        if not all(s in members for s in ('.shp','.shx','.dbf')):
            raise ValueError('ZIP de límites incompleto: faltan SHP/SHX/DBF')
        with shapefile.Reader(shp=io.BytesIO(z.read(members['.shp'])),
                              shx=io.BytesIO(z.read(members['.shx'])),
                              dbf=io.BytesIO(z.read(members['.dbf']))) as sf:
            fields = [f[0] for f in sf.fields[1:]]
            states = {}
            for item in sf.iterShapeRecords():
                attrs = dict(zip(fields, item.record))
                code = str(attrs.get('STUSPS', '')).strip()
                if code not in US_STATES:
                    continue
                shape = item.shape
                parts = list(shape.parts) + [len(shape.points)]
                rings = []
                for i, j in zip(parts[:-1],parts[1:]):
                    pts = shape.points[i:j]
                    if len(pts)<3: continue
                    lon0 = min(x for x,y in pts)
                    lon1 = max(x for x,y in pts)
                    lat0 = min(y for x,y in pts)
                    lat1 = max(y for x,y in pts)
                    rings.append((lon0, lat0, lon1, lat1, pts))
                states[US_STATES[code]] = {'code':code, 'bbox':tuple(shape.bbox), 'rings':rings}
    return states


def point_in_ring(x: float, y: float, pts: list) -> bool:
    """Ray casting; anillo individual. Usa sólo coordenadas de centro de píxel."""
    inside = False
    j = len(pts) - 1
    for i, (xi, yi) in enumerate(pts):
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            cross_x = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < cross_x:
                inside = not inside
        j = i
    return inside


def inside_state(lon: float, lat: float, geom: dict) -> bool:
    a, b, c, d = geom['bbox']
    if not (a <= lon <= c and b <= lat <= d):
        return False
    inside = False
    for x0, y0, x1, y1, pts in geom['rings']:
        if x0 <= lon <= x1 and y0 <= lat <= y1 and point_in_ring(lon, lat, pts):
            inside = not inside  # regla par-impar, incluyendo huecos
    return inside


def source_index():
    motor.DATA = RAW
    return motor.sources()


def available_sources(years, sensors):
    idx = source_index()
    out = {}
    for year in years:
        for sensor in sensors:
            item = idx.get((sensor, year, motor.keytext('United States')))
            if item is not None:
                out[sensor,year] = item
    return out


def contiene_usa_en_zip(ruta: Path, sensor: str, anio: int) -> bool:
    """Comprueba que un ZIP incluya el CSV estadounidense solicitado."""
    if not ruta.is_file() or not zipfile.is_zipfile(ruta):
        return False
    nombre = f"{sensor}_{anio}_United_States.csv"
    try:
        with zipfile.ZipFile(ruta) as z:
            coinciden = [m for m in z.namelist() if Path(m).name == nombre]
            if len(coinciden) != 1:
                return False
            with z.open(coinciden[0]) as datos:
                cabecera = datos.readline().decode("utf-8-sig", errors="replace").lower()
                return "latitude" in cabecera and "longitude" in cabecera
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        return False


def buscar_zip_existente(sensor: str, anio: int) -> Path | None:
    """Reutiliza ZIPs de este proyecto, incluso si se guardaron en otra carpeta."""
    nombre = f"{sensor}_{anio}_all_countries.zip"
    for ruta in [ROOT/nombre, RAW/sensor/"zips"/nombre, RAW/nombre]:
        if contiene_usa_en_zip(ruta, sensor, anio):
            return ruta
    return None


def descargar_y_verificar_zip(years: list[int], sensors: tuple[str, ...]):
    """Descarga los ZIP anuales faltantes y valida que contengan Estados Unidos.

    Lanza error si falló un ZIP que NASA afirmó tener disponible; no permite
    continuar con una descarga incompleta como si hubiera terminado bien.
    """
    faltantes = [(sensor, year) for year in years for sensor in sensors
                 if buscar_zip_existente(sensor, year) is None]
    existentes = len(years)*len(sensors)-len(faltantes)
    print(f"\nArchivos ZIP en caché: {existentes}. Por consultar: {len(faltantes)}.")
    if not faltantes:
        print("Todos los ZIP necesarios ya están disponibles localmente.")
        return

    print("Consultando catálogo anual público de NASA FIRMS...")
    try:
        catalogo = nasa.obtener_catalogo()
    except Exception as exc:
        raise RuntimeError(f"No se pudo consultar NASA FIRMS: {exc}") from exc

    plan = []
    sin_publicar = []
    for sensor, year in faltantes:
        nombre = f"{sensor}_{year}_all_countries.zip"
        if nombre not in catalogo:
            sin_publicar.append((sensor,year))
            continue
        ruta = RAW / sensor / "zips" / nombre
        plan.append((nombre,f"{nasa.BASE}/zips/{nombre}",ruta,catalogo[nombre],sensor,year))

    if sin_publicar:
        for sensor,year in sin_publicar:
            print(f"  NO PUBLICADO en catálogo anual: {sensor} / {year} (no equivale a cero incendios)")
    if not plan and existentes == 0:
        raise RuntimeError("Ninguno de los archivos solicitados está publicado en el catálogo anual de NASA.")

    bytes_total = sum(x[3] for x in plan)
    print(f"Por descargar: {len(plan)} ZIP(s), aproximadamente {bytes_total/1048576:.1f} MB.")
    fallidos = []
    for n,(nombre,url,ruta,esperado,sensor,year) in enumerate(plan,1):
        print(f"\n[{n}/{len(plan)}] {nombre}")
        # Si existe un ZIP con tamaño correcto pero sin el CSV requerido,
        # descartarlo antes de reintentar: el descargador básico revisa
        # tamaño y firma ZIP, no todos sus miembros.
        if ruta.exists() and not contiene_usa_en_zip(ruta,sensor,year):
            print("  ZIP local incompleto/inválido; se volverá a descargar:", ruta.name)
            ruta.unlink()
        # La función existente descarga por bloques, comprueba tamaño y evita duplicados.
        if not nasa.descargar_archivo(nombre,url,ruta,esperado):
            fallidos.append(nombre)
        elif not contiene_usa_en_zip(ruta,sensor,year):
            fallidos.append(nombre + " (sin CSV de United States válido)")
    if fallidos:
        raise RuntimeError("Descarga/verificación incompleta: " + ", ".join(fallidos))
    print("\nZIPs descargados y verificados correctamente.")


def download_us(years, sensors, full_zip=False, assume_yes=False):
    """Comando avanzado para descargar sin analizar."""
    if full_zip:
        descargar_y_verificar_zip(years,tuple(sensors))
        return
    print('Consultando catálogo público anual de NASA FIRMS...')
    catalog = nasa.obtener_catalogo()
    solicitudes = [{'sensores':list(sensors), 'modo':'pais',
                    'pais':'United States', 'anios':years}]
    plan = nasa.construir_plan(solicitudes, catalog)
    missing = [p for p in plan if not nasa.validar_archivo(p[2],p[3])]
    print(f'Encontrados {len(plan)}, pendientes {len(missing)}; tamaño aproximado '
          f'{sum(p[3] for p in missing)/1048576:.1f} MB.')
    if missing and not assume_yes:
        if input('¿Descargar? (s/n): ').strip().lower() not in {'s','si','sí'}:
            print('Descarga cancelada')
            return
    failures = []
    for i,p in enumerate(missing,1):
        print(f'[{i}/{len(missing)}] {p[0]}')
        if not nasa.descargar_archivo(*p):
            failures.append(p[0])
    if failures:
        raise RuntimeError('Descargas fallidas: '+', '.join(failures))

def is_candidate(lon, lat, selected):
    for state, geom in selected.items():
        a,b,c,d = geom['bbox']
        if a <= lon <= c and b <= lat <= d and inside_state(lon,lat,geom):
            return state
    return None


def partition_state_files(sources:dict, year:int, wanted_states:list[str], geoms:dict, force:bool=False):
    """Lee UNA vez cada archivo USA anual por sensor, sin descomprimir ZIPs gigantes.

    Escribe CSV estatal para reutilizar íntegramente el motor v2 existente.
    Los estados se determinan por centro de píxel: no por huella completa.
    """
    selected={s:geoms[s] for s in wanted_states}
    totals = {}
    for sensor in SENSORS:
        item = sources.get((sensor,year))
        if item is None:
            print(f'  {year} {sensor}: SIN FUENTE; no se interpreta como cero incendios.')
            continue
        targets = {state:STATE_DATA/sensor/str(year)/f'{sensor}_{year}_{slug(state)}.csv'
                   for state in wanted_states}
        pending = {st:p for st,p in targets.items() if force or not p.exists()}
        if not pending:
            print(f'  {year} {sensor}: archivos por estado existentes; se reutilizan.')
            continue
        selected2 = {s:selected[s] for s in pending}
        print(f'  Filtrando {year} {sensor} ({len(pending)} estado(s)) desde {item[2].name}...')
        with ExitStack() as stack:
            writers={}
            counts={state:0 for state in pending}
            it=iter(motor.read_csv(item))
            try:
                first=next(it)
            except StopIteration:
                print('    CSV sin registros')
                continue
            cols=list(first.keys())
            for state, path in pending.items():
                path.parent.mkdir(parents=True,exist_ok=True)
                f=stack.enter_context(path.open('w',encoding='utf-8-sig',newline=''))
                w=csv.DictWriter(f,fieldnames=cols)
                w.writeheader()
                writers[state]=w
            count_valid=0
            import itertools
            for row in itertools.chain([first],it):
                try:
                    lat, lon = float(row['latitude']),float(row['longitude'])
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        continue
                except (ValueError,KeyError,TypeError):
                    continue
                count_valid+=1
                st=is_candidate(lon,lat,selected2)
                if st is not None:
                    writers[st].writerow(row)
                    counts[st]+=1
            totals[sensor] = counts
            print('    Registros evaluados:', count_valid, '| por estado:',
                  ', '.join(f'{st}={n}' for st,n in counts.items()))
    return totals


def summarize_one_state(state: str, years: list[int], folders: dict[int,Path]):
    folder = RESULTS / slug(state)
    all_month=[]; all_year=[]
    for y in years:
        runfolder = folders.get(y)
        if runfolder is None:
            continue
        p=runfolder/'calendario_mensual_v2.csv'
        diagpath=runfolder/'diagnostico_v2.json'
        if not p.exists() or not diagpath.exists():
            continue
        diag=json.loads(diagpath.read_text(encoding='utf-8'))
        with p.open(encoding='utf-8-sig',newline='') as f:
            xs=list(csv.DictReader(f))
        sensors=sorted(diag['input_counts'])
        for row in xs:
            all_month.append({'estado':state,'mes_utc':row['mes_utc'],
               'celdas_dia_activas_proxy':row['celdas_dia_activas_proxy'],
               'ambos':row['ambos'],'solo_modis':row['solo_modis'],
               'solo_viirs':row['solo_viirs'],
               'sensores_disponibles':'+'.join(sensors),
               'nota':'NO_comparable_entre_anios_sin_corregir_cobertura_y_sensibilidad'})
        stats=diag['cell_day_proxy']
        all_year.append({'estado':state,'anio':y,'detecciones_validas':diag['valid_total'],
            'celdas_dia_activas_proxy':stats['union'],
            'ambos':stats.get('ambos',0),'solo_modis':stats.get('solo_modis',0),
            'solo_viirs':stats.get('solo_viirs',0),'parejas_candidatas':diag['candidate_pairs'],
            'sensores_disponibles':'+'.join(sensors),
            'nota':'indicador_exploratorio_NO_calibracion_historica'})
    if all_month:
        with (folder/'historico_mensual_exploratorio.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(all_month[0]));w.writeheader();w.writerows(all_month)
        with (folder/'resumen_anual_exploratorio.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(all_year[0]));w.writeheader();w.writerows(all_year)
        print('  Historial de',state,'en',folder)


def analyze(states: list[str], years: list[int], grid:float,window:int,quality:str,force:bool,
            boundary:Path|None, only_partition:bool=False):
    available=available_sources(years, SENSORS)
    if not available:
        raise RuntimeError('No encuentro CSV o ZIP de United States para los años seleccionados. '
                           'Usa primero el comando descargar, o coloca ZIP anuales junto al programa.')
    print('Fuentes de Estados Unidos disponibles:',
          ', '.join(f'{sensor}/{year}' for sensor,year in sorted(available)))
    geo=read_boundaries(boundary)
    for st in states:
        if st not in geo:
            raise RuntimeError(f'No se encontró geometría para {st} en el ZIP del Census')
    summary_folders = {state:{} for state in states}
    for year in years:
        if not any(k[1] == year for k in available):
            print(f'{year}: no existen fuentes; se omite, NO es cero actividad.')
            continue
        print('\n=== AÑO',year,'===')
        partition_state_files(available,year,states,geo,force)
        if only_partition:
            continue
        for st in states:
            print('\nAnalizando:',st,year)
            olddata,oldout = motor.DATA,motor.OUT
            motor.DATA = STATE_DATA
            motor.OUT = RESULTS
            args=argparse.Namespace(pais=st,anio=year,cuadricula=grid,ventana=window,calidad=quality)
            try:
                try:
                    runfolder,diag = motor.run(args)
                    summary_folders[st][year] = runfolder
                    # v3: segundo análisis ESPACIAL; los originales y v2 quedan intactos.
                    from espacial_h3_v3 import generate
                    h3_out, h3_report = generate(runfolder, resolution=7)
                    print('  H3 r7:', h3_report['h3_celdas_dia'].get('union',0),
                          'hexágonos-día; cuadrícula v2:',
                          sum(h3_report['cuadricula_celdas_dia'].values()))
                except RuntimeError as exc:
                    if 'No hay observaciones validas' in str(exc):
                        print('  Sin registros válidos para el estado/año; se omite.')
                    else: raise
            finally:
                motor.DATA, motor.OUT = olddata,oldout
    if not only_partition:
        for st in states:
            summarize_one_state(st, years, summary_folders[st])
    print('\nIMPORTANTE: las salidas son presencias de detecciones por celda-día, '
          'no número de incendios. NO son una serie histórica calibrada.')


def main(argv=None):
    p=argparse.ArgumentParser(description='Nodara Tech — NASA FIRMS de ZIP a resultados por estado, automáticamente')
    commands=p.add_subparsers(dest='cmd')
    commands.add_parser('estados',help='Mostrar estados disponibles')

    auto=commands.add_parser('ejecutar',help='TODO automático: descargar ZIPs NASA, filtrar por estado y armonizar')
    auto.add_argument('--estado',required=True,help='California, Texas, CA, TX o TODOS')
    auto.add_argument('--anios',required=True,help='2024 o 2015,2020,2024 o 2018-2024')
    auto.add_argument('--cuadricula',type=float,choices=[2.,5.,10.],default=5.)
    auto.add_argument('--ventana',type=int,choices=[15,30,60,120],default=30)
    auto.add_argument('--calidad',choices=['todas','sin_l_viirs'],default='todas')
    auto.add_argument('--limites',type=Path,default=None,help='Ruta opcional a límites US Census')
    auto.add_argument('--recalcular',action='store_true')

    d=commands.add_parser('descargar',help='Solo descargar, sin analizar (modo avanzado)')
    d.add_argument('--anios',required=True)
    d.add_argument('--sensores',choices=['todos']+list(SENSORS),default='todos')
    d.add_argument('--zip',action='store_true',help='Bajar ZIP completo de todos los países')
    d.add_argument('--si',action='store_true',help='Confirmar si se descarga un CSV por país')

    a=commands.add_parser('analizar',help='Solo analizar archivos ya descargados (modo avanzado)')
    a.add_argument('--estado',required=True)
    a.add_argument('--anios',required=True)
    a.add_argument('--cuadricula',type=float,choices=[2.,5.,10.],default=5.)
    a.add_argument('--ventana',type=int,choices=[15,30,60,120],default=30)
    a.add_argument('--calidad',choices=['todas','sin_l_viirs'],default='todas')
    a.add_argument('--limites',type=Path,default=None)
    a.add_argument('--recalcular',action='store_true')
    a.add_argument('--solo-filtrar',action='store_true')

    if argv is None and len(sys.argv)==1:
        print('NODARA TECH | DESCARGA + ARMONIZACIÓN AUTOMÁTICA')
        print('1. Descargar ZIPs NASA y analizar estado (RECOMENDADO)')
        print('2. Solo descargar ZIPs')
        print('3. Solo analizar datos locales')
        print('4. Ver lista de estados')
        op=input('Elige 1-4: ').strip()
        if op=='4':
            argv=['estados']
        elif op in ('1','2','3'):
            state = ''
            if op != '2':
                state = input('Estado (ej.: California, Texas, CA o TODOS) [California]: ').strip() or 'California'
            years=input('Años (ej.: 2024 o 2015,2020,2024) [2024]: ').strip() or '2024'
            if op=='1': argv=['ejecutar','--estado',state,'--anios',years]
            elif op=='2': argv=['descargar','--anios',years,'--sensores','todos','--zip']
            else: argv=['analizar','--estado',state,'--anios',years]
        else:
            print('Opción no válida')
            return 1
    args=p.parse_args(argv)
    if args.cmd is None:
        p.print_help();return 1
    if args.cmd=='estados':
        for code,name in sorted(US_STATES.items(),key=lambda x:x[1]):
            print(f'{name:25s} {code}')
        return 0
    years=parse_years(args.anios)
    if args.cmd=='descargar':
        sensors=SENSORS if args.sensores=='todos' else (args.sensores,)
        download_us(years,sensors,args.zip,args.si)
        return 0
    if args.cmd in ('analizar','ejecutar'):
        state=resolve_state(args.estado)
        states=sorted(US_STATES.values()) if state=='TODOS' else [state]
        if len(states)>1:
            print('AVISO: todos los estados y muchos años puede consumir bastante tiempo y disco.')
        if args.cmd=='ejecutar':
            print('\nPASO 1 / 3: Descarga automática de los ZIP anuales de NASA FIRMS')
            descargar_y_verificar_zip(years,SENSORS)
            print('\nPASO 2 / 3: Límites oficiales y separación por estado')
        else:
            print('\nModo avanzado: usando únicamente archivos locales')
        print('\nPASO 3 / 3: Motor de armonización MODIS–VIIRS v2')
        analyze(states,years,args.cuadricula,args.ventana,args.calidad,args.recalcular,
                args.limites,getattr(args,'solo_filtrar',False))
        print('\nPROCESO COMPLETO. Resultados en:',RESULTS)
        return 0
    return 1


if __name__=='__main__':
    try: sys.exit(main())
    except (RuntimeError, ValueError, OSError, zipfile.BadZipFile) as exc:
        print('\nERROR:',exc)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nProceso interrumpido. Los ZIP completados se reutilizarán.')
        sys.exit(130)
