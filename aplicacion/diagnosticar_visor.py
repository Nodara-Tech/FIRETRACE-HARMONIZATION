"""Comprueba por HTTP los datos del visor Nodara Tech que corre en el PC."""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8765"

def consultar(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=90) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {"error": "Error HTTP sin información adicional"}
    except Exception as exc:
        return None, {"error": str(exc)}

print("=== DIAGNOSTICO NODARA TECH ===")
status, datos = consultar("/api/catalogo")
print("Catalogo HTTP:", status)
if status != 200 or not isinstance(datos, list):
    print("ERROR DEL CATALOGO:", datos)
    raise SystemExit(1)
print("Conjuntos detectados:")
for d in datos:
    print(" -", d.get("id"))
if not datos:
    print("No hay conjuntos disponibles: revisa las carpetas de resultados.")
    raise SystemExit(1)
preferido = next((d for d in datos if d.get("id") == "California__2024"), None)
if preferido is None:
    preferido = next((d for d in datos if d.get("id") == "Costa_Rica__2024"), datos[0])
did = preferido["id"]
status, perfil = consultar("/api/perfil?id=" + urllib.parse.quote(did))
print("Perfil:", did, "HTTP", status)
if status != 200:
    print("ERROR:", perfil)
    raise SystemExit(1)
fecha = perfil.get("default_date", "")
print("Fecha de prueba:", fecha)
for modo in ("points", "cells", "pairs"):
    path = ("/api/dia?" + urllib.parse.urlencode({"id": did, "fecha": fecha, "modo": modo}))
    status, datos = consultar(path)
    print(f"  {modo}: HTTP {status}", end="")
    if status == 200 and "features" in datos:
        print(", elementos =", len(datos["features"]))
    else:
        print(", ERROR =", datos.get("error", datos))
print("=== FIN DEL DIAGNOSTICO ===")
