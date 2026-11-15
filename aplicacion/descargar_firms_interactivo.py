"""Descargador interactivo de archivos anuales de NASA FIRMS.

Equipo: Nodara Tech - prototipo de armonizacion MODIS/VIIRS.
Datos publicos: https://firms.modaps.eosdis.nasa.gov/data/country/

Ejecutar en Visual Studio Code:
    python descargar_firms_interactivo.py

NO requiere MAP_KEY para los CSV/ZIP historicos del catalogo anual por pais.
NO incluye NOAA-21: su historial se obtiene por otros servicios de NASA,
no mediante estos ZIP/CSV anuales del catalogo utilizado aqui.
"""

import csv
import difflib
import io
import re
import time
import unicodedata
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
CATALOGO_URL = f"{BASE}/yearly_summary_files.txt"
DESTINO = Path(__file__).resolve().parent.parent / "datos" / "datos_firms"
HEADERS = {"User-Agent": "NodaraTech-FIRMS-Downloader/2.0"}
SENSORES = {
    "1": ("modis", "MODIS (Terra/Aqua)", 2000),
    "2": ("viirs-snpp", "VIIRS Suomi-NPP", 2012),
    "3": ("viirs-jpss1", "VIIRS NOAA-20", 2018),
}


def pregunta_opcion(texto, validas):
    while True:
        opcion = input(texto).strip().lower()
        if opcion in validas:
            return opcion
        print(f"Opcion no reconocida. Usa: {', '.join(validas)}")


def limpiar_pais(texto):
    """Comparacion flexible: Costa Rica, costa_rica, COSTA-RICA."""
    normal = unicodedata.normalize("NFKD", texto.casefold())
    sin_acentos = "".join(c for c in normal if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", sin_acentos)


def pedir_anios():
    while True:
        entrada = input(
            "Ano(s), ejemplo 2025 / 2020-2025 / 2000,2005,2022-2025: "
        ).strip().replace(" ", "")
        try:
            anios = set()
            for parte in entrada.split(","):
                if not parte:
                    raise ValueError("parte vacia")
                if "-" in parte:
                    inicio, fin = parte.split("-", 1)
                    a, b = int(inicio), int(fin)
                    if a > b:
                        raise ValueError("rango invertido")
                    anios.update(range(a, b + 1))
                else:
                    anios.add(int(parte))
            if not anios or min(anios) < 2000 or max(anios) > 2100:
                raise ValueError("anos fuera de rango")
            return sorted(anios)
        except (ValueError, TypeError):
            print("Formato incorrecto. Ejemplo valido: 2001,2005,2020-2025")


def pedir_sensores():
    print("\nSelecciona fuente(s):")
    print("  1. MODIS (Terra y Aqua)")
    print("  2. VIIRS Suomi-NPP")
    print("  3. VIIRS NOAA-20")
    print("  4. Ambos VIIRS (S-NPP y NOAA-20)")
    print("  5. MODIS + ambos VIIRS")
    while True:
        eleccion = input("Numero (1-5): ").strip()
        mapa = {"1": ["1"], "2": ["2"], "3": ["3"],
                "4": ["2", "3"], "5": ["1", "2", "3"]}
        if eleccion in mapa:
            return [SENSORES[n][0] for n in mapa[eleccion]]
        print("Selecciona un numero del 1 al 5.")


def agregar_solicitud(solicitudes):
    print("\n--- NUEVA SOLICITUD ---")
    sensores = pedir_sensores()
    print("\nTipo de descarga:")
    print("  1. CSV de un pais, uno por ano y sensor")
    print("  2. ZIP anual completo, con todos los paises")
    tipo = pregunta_opcion("Numero (1-2): ", {"1", "2"})
    modo = "pais" if tipo == "1" else "zip"
    pais = None
    if modo == "pais":
        while not pais:
            pais = input("Pais (ejemplo: Afghanistan o Costa Rica): ").strip()
            if not pais:
                print("Debes escribir un pais.")
    anios = pedir_anios()
    solicitudes.append({"sensores": sensores, "modo": modo, "pais": pais, "anios": anios})
    print("Solicitud agregada. Puedes anadir otra con distintos anos o pais.")


def mostrar_solicitudes(solicitudes):
    if not solicitudes:
        print("\nTodavia no hay solicitudes.")
        return
    print("\n--- SOLICITUDES ---")
    for i, s in enumerate(solicitudes, 1):
        anios = ", ".join(map(str, s["anios"]))
        fuente = ", ".join(s["sensores"])
        detalle = f"CSV de {s['pais']}" if s["modo"] == "pais" else "ZIP de todos los paises"
        print(f"  {i}. {fuente} | {detalle} | {anios}")


def obtener_catalogo():
    solicitud = urllib.request.Request(CATALOGO_URL, headers=HEADERS)
    with urllib.request.urlopen(solicitud, timeout=60) as respuesta:
        contenido = respuesta.read().decode("utf-8-sig")
    lector = csv.DictReader(io.StringIO(contenido))
    if not lector.fieldnames or not {"filename", "size"}.issubset(lector.fieldnames):
        raise ValueError("El formato del catalogo anual ha cambiado.")
    resultado = {}
    for fila in lector:
        try:
            resultado[fila["filename"].strip()] = int(fila["size"])
        except (ValueError, TypeError, KeyError):
            continue
    if not resultado:
        raise ValueError("El catalogo llego vacio.")
    return resultado


def localizar_csv(catalogo, sensor, anio, pais):
    """Busca el pais por nombre normalizado en el catalogo real."""
    prefijo = f"{sensor}_{anio}_"
    candidatos = {
        limpiar_pais(nombre[len(prefijo):-4]): nombre
        for nombre in catalogo
        if nombre.startswith(prefijo) and nombre.endswith(".csv")
    }
    buscado = limpiar_pais(pais)
    if buscado in candidatos:
        return candidatos[buscado], []
    similares = difflib.get_close_matches(buscado, list(candidatos), n=4, cutoff=0.5)
    nombres = [candidatos[x][len(prefijo):-4].replace("_", " ") for x in similares]
    return None, nombres


def construir_plan(solicitudes, catalogo):
    archivos = {}
    for solicitud in solicitudes:
        for sensor in solicitud["sensores"]:
            for anio in solicitud["anios"]:
                if solicitud["modo"] == "zip":
                    nombre = f"{sensor}_{anio}_all_countries.zip"
                    ruta = DESTINO / sensor / "zips" / nombre
                    url = f"{BASE}/zips/{nombre}"
                    sugerencias = []
                else:
                    nombre, sugerencias = localizar_csv(
                        catalogo, sensor, anio, solicitud["pais"]
                    )
                    if nombre:
                        ruta = DESTINO / sensor / str(anio) / nombre
                        url = f"{BASE}/{sensor}/{anio}/{nombre}"
                if not nombre or nombre not in catalogo:
                    detalle = (f"Pais '{solicitud['pais']}'" if solicitud["modo"] == "pais"
                               else "ZIP anual")
                    print(f"No disponible: {sensor}, {anio}, {detalle}.")
                    if sugerencias:
                        print("  Paises de nombre parecido:", ", ".join(sugerencias))
                    continue
                # Clave por ruta para evitar descargar la misma solicitud dos veces.
                archivos[str(ruta)] = (nombre, url, ruta, catalogo[nombre])
    return list(archivos.values())


def validar_archivo(ruta, esperado):
    if not ruta.exists() or ruta.stat().st_size != esperado:
        return False
    if ruta.suffix.lower() == ".zip":
        return zipfile.is_zipfile(ruta)
    if ruta.suffix.lower() == ".csv":
        with ruta.open("rb") as f:
            cabecera = f.readline(4096).decode("utf-8-sig", errors="replace").lower()
        return "latitude" in cabecera and "longitude" in cabecera
    return False


def descargar_archivo(nombre, url, ruta, esperado):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if validar_archivo(ruta, esperado):
        print(f"  Ya existe y es valido; se omite: {nombre}")
        return True
    temporal = ruta.with_name(ruta.name + ".part")
    for intento in range(1, 4):
        try:
            peticion = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(peticion, timeout=90) as respuesta:
                total = 0
                siguiente = 10 * 1024 * 1024
                with temporal.open("wb") as salida:
                    while True:
                        trozo = respuesta.read(1024 * 1024)
                        if not trozo:
                            break
                        salida.write(trozo)
                        total += len(trozo)
                        if total >= siguiente:
                            print(f"  {total / 1048576:.1f} MB / {esperado / 1048576:.1f} MB")
                            siguiente += 10 * 1024 * 1024
            if temporal.stat().st_size != esperado:
                raise ValueError("Tamano incorrecto respecto al catalogo de NASA")
            if ruta.suffix == ".zip":
                if not zipfile.is_zipfile(temporal):
                    raise ValueError("El archivo no es un ZIP valido")
            else:
                with temporal.open("rb") as f:
                    cabecera = f.readline(4096).decode("utf-8-sig", errors="replace").lower()
                if "latitude" not in cabecera or "longitude" not in cabecera:
                    raise ValueError("No se reconocen las columnas de un CSV FIRMS")
            temporal.replace(ruta)
            print(f"  Descargado: {ruta}")
            return True
        except (urllib.error.URLError, OSError, ValueError, zipfile.BadZipFile) as exc:
            temporal.unlink(missing_ok=True)
            print(f"  Error en intento {intento}/3: {exc}")
            if intento < 3:
                time.sleep(intento * 2)
    return False


def procesar(solicitudes):
    if not solicitudes:
        print("Agrega al menos una solicitud antes de descargar.")
        return
    print("\nConsultando catalogo oficial de NASA FIRMS...")
    try:
        catalogo = obtener_catalogo()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"No se pudo consultar el catalogo: {exc}")
        return
    plan = construir_plan(solicitudes, catalogo)
    if not plan:
        print("No se encontraron archivos. Revisa anos, paises y sensores.")
        return
    faltantes = [x for x in plan if not validar_archivo(x[2], x[3])]
    total = sum(x[3] for x in faltantes) / 1048576
    print(f"\nArchivos encontrados: {len(plan)}")
    print(f"Ya descargados: {len(plan) - len(faltantes)}")
    print(f"Pendientes: {len(faltantes)} (~{total:,.1f} MB)")
    print(f"Carpeta destino: {DESTINO}")
    if not faltantes:
        print("Ya tienes todos los archivos solicitados.")
        return
    if pregunta_opcion("\nComenzar descargas? (s/n): ", {"s", "n", "si", "sí"}) not in {"s", "si", "sí"}:
        print("Cancelado, sin borrar las solicitudes.")
        return
    correctos = 0
    for indice, item in enumerate(faltantes, 1):
        print(f"\n[{indice}/{len(faltantes)}] {item[0]}")
        if descargar_archivo(*item):
            correctos += 1
    print(f"\nListo: {correctos}/{len(faltantes)} descargas nuevas correctas.")
    print("Los archivos se guardaron por sensor y ano; puedes repetir sin duplicar.")


def main():
    print("=" * 55)
    print("   NASA FIRMS - DESCARGADOR INTERACTIVO NODARA TECH")
    print("   MODIS y VIIRS por separado")
    print("=" * 55)
    solicitudes = []
    while True:
        print("\nMENU PRINCIPAL")
        print("  1. Agregar solicitud (sensor, pais y anos)")
        print("  2. Ver solicitudes")
        print("  3. Eliminar ultima solicitud")
        print("  4. Descargar archivos solicitados")
        print("  5. Salir")
        opcion = pregunta_opcion("Elige 1-5: ", {"1", "2", "3", "4", "5"})
        if opcion == "1":
            agregar_solicitud(solicitudes)
        elif opcion == "2":
            mostrar_solicitudes(solicitudes)
        elif opcion == "3":
            if solicitudes:
                solicitudes.pop()
                print("Ultima solicitud eliminada.")
            else:
                print("No hay solicitudes que eliminar.")
        elif opcion == "4":
            mostrar_solicitudes(solicitudes)
            procesar(solicitudes)
        else:
            print("Hasta luego.")
            break


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nPrograma interrumpido por el usuario.")
