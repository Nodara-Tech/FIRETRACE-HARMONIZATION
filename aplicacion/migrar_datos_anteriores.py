"""Importa fuentes y resultados de un proyecto Nodara anterior sin borrar originales.
Uso: py aplicacion/migrar_datos_anteriores.py "RUTA_COMPLETA_A_LA_CARPETA_VIEJA"
"""
from pathlib import Path
import shutil
import sys

NEW_ROOT = Path(__file__).resolve().parent.parent
MAPPINGS = {
    "datos_firms": NEW_ROOT/"datos"/"datos_firms",
    "datos_firms_estados": NEW_ROOT/"datos"/"datos_firms_estados",
    "limites_geograficos": NEW_ROOT/"datos"/"limites_geograficos",
    "resultados_estados_unidos": NEW_ROOT/"resultados"/"resultados_estados_unidos",
    "resultados_armonizacion_v2": NEW_ROOT/"resultados"/"resultados_armonizacion_v2",
}


def migrar(origen: Path):
    origen = origen.expanduser().resolve()
    # Detecta estructura anterior: raíz doble dentro de Descargas.
    if not (origen/"visor_incendios.py").exists() and (origen/origen.name/"visor_incendios.py").exists():
        origen = origen/origen.name
    if not (origen/"visor_incendios.py").exists():
        raise FileNotFoundError("No encuentro visor_incendios.py en la carpeta indicada: " + str(origen))
    total, skip = 0, 0
    for name, target in MAPPINGS.items():
        source = origen/name
        if not source.is_dir():
            print("No existe carpeta anterior:",name)
            continue
        for f in source.rglob("*"):
            if not f.is_file() or f.suffix.lower() in {".sqlite3", ".part", ".sqlite3-shm", ".sqlite3-wal"}:
                continue
            dest = target/f.relative_to(source)
            if dest.exists():
                skip += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f,dest)
            total += 1
            print("Copiado:", name, f.relative_to(source))
    print(f"\nListo: {total} archivos importados, {skip} existentes sin reemplazar.")
    print("El proyecto anterior no se modificó.")

def detectar_anteriores():
    parent=NEW_ROOT.parent
    home=Path.home()
    bases=[parent,home/'Downloads',home/'OneDrive'/'Desktop',home/'Desktop',home/'Documents']
    posibles=[]
    for base in bases:
        viejo=base/'NodaraTech_Visor_Incendios'
        for candidate in (viejo, viejo/'NodaraTech_Visor_Incendios'):
            if (candidate/'visor_incendios.py').exists() and candidate.resolve() not in posibles:
                posibles.append(candidate.resolve())
    return posibles

if __name__=='__main__':
    try:
        if len(sys.argv)>1:
            ruta=Path(sys.argv[1])
        else:
            disponibles=detectar_anteriores()
            if disponibles:
                print('Carpetas anteriores encontradas:')
                for i,d in enumerate(disponibles,1):print(f'{i}. {d}')
                indice=input('Selecciona numero [1] o pega otra ruta: ').strip()
                if indice.isdecimal() and 1<=int(indice)<=len(disponibles):
                    ruta=disponibles[int(indice)-1]
                elif not indice:
                    ruta=disponibles[0]
                else:
                    ruta=Path(indice.strip('"'))
            else:
                ruta=Path(input('Pega ruta de carpeta ANTERIOR: ').strip().strip('"'))
        print('\nSe copiarán únicamente archivos de datos y resultados faltantes.')
        print('Origen:',ruta)
        if input('¿Continuar? (s/n): ').strip().lower() not in ('s','si','sí'):
            print('Operación cancelada.');sys.exit(0)
        migrar(ruta)
    except (OSError, ValueError) as e:
        print('ERROR:',e)
        sys.exit(1)
