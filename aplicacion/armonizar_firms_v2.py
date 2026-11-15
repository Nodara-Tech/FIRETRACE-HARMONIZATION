"""Nodara Tech / NASA FIRMS — motor experimental MODIS–VIIRS v2.

Uso en VS Code:
    py armonizar_firms_v2.py
    py armonizar_firms_v2.py --pais "Costa Rica" --anio 2024
    py armonizar_firms_v2.py --pais Afghanistan --anio 2024 --cuadricula 2 --ventana 30

Lee los CSV del descargador, o ZIP datos_firms*.zip colocados junto al script.
No altera fuentes. NO infiere numero real de incendios ni corrige cobertura nubosa.
Solo utiliza biblioteca estandar Python >= 3.9.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import statistics
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "datos" / "datos_firms"
OUT = ROOT / "resultados" / "resultados_armonizacion_v2"
SENSORS = ("modis", "viirs-snpp", "viirs-jpss1")
PAT = re.compile(r"^(modis|viirs-snpp|viirs-jpss1)_(\d{4})_(.+)\.csv$", re.I)
EARTH_KM = 6371.0088
COS_STD = math.cos(math.radians(30.0))
WINDOWS = (15, 30, 60, 120)
GRID_SIZES = (2.0, 5.0, 10.0)
PASS_SPAN_MIN = 12  # ventana interna por celda y satelite, experimental


def keytext(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).casefold())
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c))


def parse_name(name: str):
    m = PAT.match(Path(name).name)
    return (m[1].lower(), int(m[2]), m[3].replace("_", " ")) if m else None


def sources():
    # Priorizar archivos locales sobre ZIP (evita descargarlos de nuevo).
    found = {}
    if DATA.exists():
        for file in sorted(DATA.rglob("*.csv")):
            info = parse_name(file.name)
            if info:
                found.setdefault((info[0], info[1], keytext(info[2])), (info, "csv", file, None))
    zips = set(ROOT.glob("datos_firms*.zip")) | set(ROOT.glob("*all_countries.zip"))
    if DATA.exists():
        zips |= set(DATA.rglob("*.zip"))
    for file in sorted(zips):
        try:
            with zipfile.ZipFile(file) as z:
                for name in z.namelist():
                    info = parse_name(name)
                    if info:
                        found.setdefault((info[0], info[1], keytext(info[2])), (info, "zip", file, name))
        except (zipfile.BadZipFile, OSError) as exc:
            print(f"AVISO: ZIP ignorado: {file.name} ({exc})")
    return found


def read_csv(source):
    _, typ, path, member = source
    if typ == "csv":
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            yield from csv.DictReader(f)
    else:
        with zipfile.ZipFile(path) as z, z.open(member) as binary:
            with io.TextIOWrapper(binary, newline="", encoding="utf-8-sig") as f:
                yield from csv.DictReader(f)


def number(x):
    try:
        f = float(x)
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def parse_row(row, sensor, pais, anio, idx):
    lat, lon = number(row.get("latitude")), number(row.get("longitude"))
    scan, track = number(row.get("scan")), number(row.get("track"))
    if None in (lat, lon, scan, track) or not (-90 <= lat <= 90 and -180 <= lon <= 180) or scan <= 0 or track <= 0:
        raise ValueError("coordenadas/dimensiones invalidas")
    h = str(row.get("acq_time", "")).strip().zfill(4)
    dt = datetime.strptime(str(row["acq_date"]).strip()+h, "%Y-%m-%d%H%M")
    if dt.year != anio:
        raise ValueError("anio inconsistente")
    platform = str(row.get("satellite", "")).strip()
    platform = {"A": "Aqua", "T": "Terra", "Aqua": "Aqua", "Terra": "Terra", "N": "S-NPP", "N20": "NOAA-20"}.get(platform, platform)
    family = "MODIS" if sensor == "modis" else "VIIRS"
    typ = str(row.get("type", "")).strip()
    confidence = str(row.get("confidence", "")).strip().lower()
    dn = str(row.get("daynight", "")).strip().upper()
    frp = number(row.get("frp"))
    # FRP 0, nulo o negativo no apto para comparar FRP; no se descarta deteccion.
    if frp is not None and frp <= 0:
        frp = None
    temp4 = number(row.get("brightness" if sensor == "modis" else "bright_ti4"))
    temp11 = number(row.get("bright_t31" if sensor == "modis" else "bright_ti5"))
    o = {"id": f"{sensor}:{anio}:{keytext(pais)}:{idx}", "source": sensor,
         "family": family, "platform": platform, "country": pais, "dt": dt,
         "date": dt.date(), "lat": lat, "lon": lon, "scan": scan, "track": track,
         "type": typ, "confidence": confidence, "daynight": dn,
         "version": row.get("version", ""), "frp": frp, "temp4": temp4,
         "temp11": temp11}
    return o


def projection(lat, lon):
    return (EARTH_KM * COS_STD * math.radians(lon),
            EARTH_KM * math.sin(math.radians(lat)) / COS_STD)


def grid_id(o, km, shift=0.):
    x, y = projection(o["lat"], o["lon"])
    return (math.floor(x/km + shift), math.floor(y/km + shift))


def csv_write(file, rows, columns):
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def normalized_csv(file, obs):
    cols = ["id", "country", "source", "family", "platform", "date_utc", "time_utc",
            "latitude", "longitude", "scan_km", "track_km", "pixel_area_km2_approx",
            "frp_mw", "brightness_4um_k", "brightness_11um_k", "confidence_original",
            "daynight", "type", "version", "included_type0"]
    rows = ({"id": o["id"], "country": o["country"], "source": o["source"],
             "family": o["family"], "platform": o["platform"],
             "date_utc": o["date"].isoformat(), "time_utc": o["dt"].strftime("%H:%M"),
             "latitude": o["lat"], "longitude": o["lon"], "scan_km": o["scan"],
             "track_km": o["track"], "pixel_area_km2_approx": round(o["scan"]*o["track"], 5),
             "frp_mw": o["frp"], "brightness_4um_k": o["temp4"],
             "brightness_11um_k": o["temp11"], "confidence_original": o["confidence"],
             "daynight": o["daynight"], "type": o["type"], "version": o["version"],
             "included_type0": o["type"] == "0"} for o in obs)
    csv_write(file, rows, cols)


def choose(paises, requested, anio_requested, found):
    if requested is None:
        print("\nPaises disponibles:")
        for n, p in enumerate(paises, 1):
            if len(paises) <= 40:
                print(f" {n}. {p}")
        default = "Costa Rica" if "Costa Rica" in paises else paises[0]
        a = input(f"Pais (nombre o numero) [Enter = {default}]: ").strip()
        requested = default if not a else (paises[int(a)-1] if a.isdigit() and 1 <= int(a) <= len(paises) else a)
    pais = next((p for p in paises if keytext(p) == keytext(requested)), None)
    if pais is None:
        raise ValueError(f"Pais no encontrado: {requested}")
    yrs = sorted({v[0][1] for v in found.values() if keytext(v[0][2]) == keytext(pais)})
    if anio_requested is None:
        a = input(f"Anio disponible {', '.join(map(str,yrs))} [Enter = {yrs[-1]}]: ").strip()
        anio_requested = int(a) if a else yrs[-1]
    if anio_requested not in yrs:
        raise ValueError(f"El anio {anio_requested} no esta disponible para {pais}: {yrs}")
    return pais, anio_requested


def is_allowed(o, quality):
    if o["type"] != "0":
        return False
    if quality == "sin_l_viirs" and o["family"] == "VIIRS" and o["confidence"] == "l":
        return False
    return True


def presence(records, km, shift=0.):
    cells = defaultdict(lambda: {"modis": 0, "viirs-snpp": 0, "viirs-jpss1": 0})
    for o in records:
        cells[(o["date"].isoformat(), grid_id(o, km, shift))][o["source"]] += 1
    return cells


def presence_stats(cells):
    n = Counter()
    for counts in cells.values():
        m = counts["modis"] > 0
        v = counts["viirs-snpp"] + counts["viirs-jpss1"] > 0
        n["ambos" if m and v else "solo_modis" if m else "solo_viirs"] += 1
    return dict(n, union=len(cells), modis=n["ambos"]+n["solo_modis"],
                viirs=n["ambos"]+n["solo_viirs"])


def presence_files(folder, records, km):
    cells = presence(records, km)
    cell_rows = []
    grouped_day = defaultdict(list)
    for (dt, c), counter in sorted(cells.items()):
        m, a, b = (counter[z] for z in SENSORS)
        clas = "ambos" if m and (a+b) else "solo_modis" if m else "solo_viirs"
        row = {"fecha_utc": dt, "celda": f"{c[0]}_{c[1]}", "tamano_celda_km": km,
               "presencia_armonizada_proxy": 1, "clasificacion": clas,
               "n_modis": m, "n_viirs_snpp": a, "n_viirs_noaa20": b,
               "n_original_sin_deduplicar": m+a+b}
        cell_rows.append(row)
        grouped_day[dt].append(row)
    cols = ["fecha_utc", "celda", "tamano_celda_km", "presencia_armonizada_proxy",
            "clasificacion", "n_modis", "n_viirs_snpp", "n_viirs_noaa20",
            "n_original_sin_deduplicar"]
    csv_write(folder/"armonizacion_celdas_dia_v2.csv", cell_rows, cols)
    year = records[0]["dt"].year if records else None
    rows_day = []
    rows_month = []
    if year is not None:
        d, end = date(year,1,1), date(year+1,1,1)
        while d < end:
            f = d.isoformat()
            xs = grouped_day[f]
            types = Counter(r["clasificacion"] for r in xs)
            rows_day.append({"fecha_utc": f, "celdas_activas_proxy": len(xs),
              "ambos": types["ambos"], "solo_modis": types["solo_modis"],
              "solo_viirs": types["solo_viirs"],
              "nota": "sin_detecciones_reportadas_no_equivale_sin_incendios" if not xs else ""})
            d += timedelta(days=1)
    csv_write(folder/"calendario_diario_v2.csv", rows_day,
              ["fecha_utc", "celdas_activas_proxy", "ambos", "solo_modis", "solo_viirs", "nota"])
    for month in range(1,13):
        f = f"{year}-{month:02d}" if year else f"desconocido-{month:02d}"
        xs = [r for r in cell_rows if r["fecha_utc"].startswith(f)]
        types = Counter(r["clasificacion"] for r in xs)
        rows_month.append({"mes_utc": f, "celdas_dia_activas_proxy": len(xs),
                           "ambos": types["ambos"], "solo_modis": types["solo_modis"],
                           "solo_viirs": types["solo_viirs"],
                           "dias_con_detecciones": len({r["fecha_utc"] for r in xs}),
                           "celdas_espaciales_unicas": len({r["celda"] for r in xs})})
    csv_write(folder/"calendario_mensual_v2.csv", rows_month,
              ["mes_utc", "celdas_dia_activas_proxy", "ambos", "solo_modis", "solo_viirs",
               "dias_con_detecciones", "celdas_espaciales_unicas"])
    return presence_stats(cells), rows_day


def make_passes(records, km, shift=0.):
    """Agrega observaciones por celda, plataforma, dia/noche y pasada (<=12 min)."""
    groups = defaultdict(list)
    for o in records:
        groups[(grid_id(o, km, shift), o["platform"], o["daynight"])].append(o)
    passes = []
    for (cell, platform, dn), items in groups.items():
        items.sort(key=lambda o:o["dt"])
        slices = []
        for o in items:
            if not slices or (o["dt"] - slices[-1][0]["dt"]).total_seconds() > PASS_SPAN_MIN*60:
                slices.append([o])
            else:
                slices[-1].append(o)
        for slice_ in slices:
            first, last = slice_[0]["dt"], slice_[-1]["dt"]
            frps = [o["frp"] for o in slice_ if o["frp"] is not None]
            t4s = [o["temp4"] for o in slice_ if o["temp4"] is not None]
            t11s = [o["temp11"] for o in slice_ if o["temp11"] is not None]
            k = len(passes)+1
            passes.append({"id": f"P{k:06d}", "cell": cell, "source": slice_[0]["source"],
                           "family": slice_[0]["family"], "platform": platform,
                           "daynight":dn, "t": first + (last-first)/2, "start":first,
                           "end":last, "n": len(slice_), "frp": sum(frps) if frps else None,
                           "n_frp_ok": len(frps), "n_frp_not_ok": len(slice_)-len(frps),
                           "t4_mean": statistics.mean(t4s) if t4s else None,
                           "t11_mean": statistics.mean(t11s) if t11s else None,
                           "lat":statistics.mean(o["lat"] for o in slice_),
                           "lon":statistics.mean(o["lon"] for o in slice_),
                           "n_low_viirs": sum(o["family"]=="VIIRS" and o["confidence"]=="l" for o in slice_),
                           "max_scan_km": max(o["scan"] for o in slice_),
                           "max_track_km": max(o["track"] for o in slice_)})
    return passes


def haversine(a, b):
    la1, la2 = map(math.radians, (a["lat"],b["lat"]))
    dla = la2-la1
    dlo = math.radians(b["lon"]-a["lon"])
    x = math.sin(dla/2)**2+math.cos(la1)*math.cos(la2)*math.sin(dlo/2)**2
    return 2*EARTH_KM*math.asin(min(1.,math.sqrt(max(0.,x))))


def paired_passes(passes, minutes):
    """Parejas 1-a-1 para cada combinacion concreta de plataformas, dentro de celda.
    No se reutiliza una pasada dentro del mismo par de plataformas. Las mismas
    pasadas pueden aparecer en otro par (ej. NOAA20 vs Aqua y NOAA20 vs Terra).
    """
    by_cell = defaultdict(list)
    for p in passes:
        by_cell[p["cell"]].append(p)
    pairs = []
    for cell, groups in by_cell.items():
        ms = [x for x in groups if x["family"]=="MODIS"]
        vs = [x for x in groups if x["family"]=="VIIRS"]
        by_platform = defaultdict(list)
        for x in ms: by_platform["m",x["platform"]].append(x)
        for x in vs: by_platform["v",x["platform"]].append(x)
        mplats = sorted({x["platform"] for x in ms})
        vplats = sorted({x["platform"] for x in vs})
        for mp in mplats:
            for vp in vplats:
                cand = []
                for m in by_platform["m",mp]:
                    for v in by_platform["v",vp]:
                        if m["daynight"] != v["daynight"]:
                            continue
                        delta = abs((m["t"]-v["t"]).total_seconds())/60
                        if delta <= minutes:
                            # Los centros pueden compartir una celda pero estar alejados.
                            # Este umbral de huella es solo geometrico exploratorio:
                            # radio de media diagonal de cada pixel + tolerancia 250 m.
                            dist = haversine(m, v)
                            radio_m = 0.5*math.hypot(m["max_scan_km"], m["max_track_km"])
                            radio_v = 0.5*math.hypot(v["max_scan_km"], v["max_track_km"])
                            if dist <= radio_m + radio_v + 0.25:
                                cand.append((delta, dist, m, v))
                cand.sort(key=lambda x:(x[0],x[1]))
                used_m,used_v = set(),set()
                for delta, dist, m, v in cand:
                    if m["id"] in used_m or v["id"] in used_v:
                        continue
                    used_m.add(m["id"]); used_v.add(v["id"])
                    ratio = (v["frp"]/m["frp"]) if m["frp"] and v["frp"] else None
                    pairs.append({"celda":f"{cell[0]}_{cell[1]}",
                                  "id_paso_modis":m["id"],"id_paso_viirs":v["id"],
                                  "fecha_modis_utc":m["t"].isoformat()+"Z",
                                  "fecha_viirs_utc":v["t"].isoformat()+"Z",
                                  "dia_noche":m["daynight"], "plataforma_modis":mp,
                                  "plataforma_viirs":vp, "diferencia_min":round(delta,2),
                                  "distancia_centroides_km":round(dist,4),
                                  "umbral_huella_aprox_km":round(0.5*math.hypot(m["max_scan_km"],m["max_track_km"])+0.5*math.hypot(v["max_scan_km"],v["max_track_km"])+0.25,4),
                                  "n_pix_modis":m["n"], "n_pix_viirs":v["n"],
                                  "frp_modis_mw":m["frp"],"frp_viirs_mw":v["frp"],
                                  "frp_ratio_viirs_modis":round(ratio,5) if ratio is not None else None,
                                  "frp_viirs_menos_modis_mw":round(v["frp"]-m["frp"],3) if ratio is not None else None,
                                  "t11_modis_media_k":m["t11_mean"],
                                  "t11_viirs_media_k":v["t11_mean"],
                                  "t4_modis_media_k":m["t4_mean"],
                                  "t4_viirs_media_k":v["t4_mean"],
                                  "frp_faltante_pix_modis":m["n_frp_not_ok"],
                                  "frp_faltante_pix_viirs":v["n_frp_not_ok"],
                                  "nota":"misma_celda_y_pasos_cercanos_no_prueba_mismo_incendio"})
    return pairs


PAIR_COLUMNS = ["celda", "id_paso_modis", "id_paso_viirs", "fecha_modis_utc",
 "fecha_viirs_utc", "dia_noche", "plataforma_modis", "plataforma_viirs",
 "diferencia_min", "distancia_centroides_km", "umbral_huella_aprox_km", "n_pix_modis", "n_pix_viirs",
 "frp_modis_mw", "frp_viirs_mw", "frp_ratio_viirs_modis",
 "frp_viirs_menos_modis_mw", "t11_modis_media_k", "t11_viirs_media_k",
 "t4_modis_media_k", "t4_viirs_media_k", "frp_faltante_pix_modis",
 "frp_faltante_pix_viirs", "nota"]


def pearson(xs, ys):
    if len(xs)<3: return None
    xm,ym=statistics.mean(xs),statistics.mean(ys)
    xx=sum((x-xm)**2 for x in xs); yy=sum((y-ym)**2 for y in ys)
    if xx==0 or yy==0: return None
    return sum((x-xm)*(y-ym) for x,y in zip(xs,ys))/math.sqrt(xx*yy)


def robust_relation(pairs):
    """Calibracion EXPLORATORIA de FRP agrupado, por par de plataforma.
    No se debe aplicar fuera de las muestras validadas.
    """
    grouped = defaultdict(list)
    for p in pairs:
        if (p["frp_modis_mw"] is not None and p["frp_viirs_mw"] is not None
              and p["frp_modis_mw"]>=5 and p["frp_viirs_mw"]>=5
              and not p["frp_faltante_pix_modis"] and not p["frp_faltante_pix_viirs"]):
            grouped[(p["plataforma_modis"],p["plataforma_viirs"],p["dia_noche"])].append(p)
    result = []
    for key, items in sorted(grouped.items()):
        items.sort(key=lambda p:p["fecha_modis_utc"])
        days = sorted({p["fecha_modis_utc"][:10] for p in items})
        split = max(1,math.floor(len(days)*.7))
        train_days = set(days[:split])
        train = [p for p in items if p["fecha_modis_utc"][:10] in train_days]
        test = [p for p in items if p["fecha_modis_utc"][:10] not in train_days]
        k = statistics.median(p["frp_ratio_viirs_modis"] for p in train) if train else None
        pred_error = [abs(k*p["frp_modis_mw"]-p["frp_viirs_mw"])/p["frp_viirs_mw"]
                      for p in test] if k is not None else []
        ntrdays=len(train_days); ntestdays=len(days)-ntrdays
        ok=len(train)>=20 and len(test)>=8 and ntrdays>=8 and ntestdays>=3
        rtest = pearson([p["frp_modis_mw"] for p in test], [p["frp_viirs_mw"] for p in test])
        median_err = statistics.median(pred_error) if pred_error else None
        # Reglas de calidad propuestas, NO umbrales oficiales NASA:
        # no damos por valida una equivalencia con alto error fuera de muestra.
        usable = ok and median_err is not None and median_err <= .25 and rtest is not None and rtest >= .75
        result.append({"modis":key[0],"viirs":key[1],"dia_noche":key[2],
                       "pares_frp_validos":len(items), "dias_distintos":len(days),
                       "train_pares":len(train),"test_pares":len(test),
                       "train_dias":ntrdays,"test_dias":ntestdays,
                       "factor_mediano_viirs_sobre_modis_EXPLORATORIO":round(k,4) if k else "",
                       "error_relativo_mediano_test":round(median_err,4) if median_err is not None else "",
                       "correlacion_test":round(rtest,4) if rtest is not None else "",
                       "tiene_muestra_minima": "si" if ok else "no",
                       "supera_criterio_exploratorio": "si" if usable else "no",
                       "advertencia":"diagnostico_exploratorio_NO_calibracion_historica"})
    cols = ["modis","viirs","dia_noche","pares_frp_validos","dias_distintos",
            "train_pares","test_pares","train_dias","test_dias",
            "factor_mediano_viirs_sobre_modis_EXPLORATORIO","error_relativo_mediano_test",
            "correlacion_test","tiene_muestra_minima","supera_criterio_exploratorio","advertencia"]
    return result,cols


def thermal_relations(pairs):
    """Resume respuestas de bandas similares SIN suponer equivalencia física."""
    bins=defaultdict(list)
    for p in pairs:
        bins[(p["plataforma_modis"],p["plataforma_viirs"],p["dia_noche"])].append(p)
    rows=[]
    for (m,v,dn),grupo in sorted(bins.items()):
        for name,ma,va in (("11um","t11_modis_media_k","t11_viirs_media_k"),
                            ("4um","t4_modis_media_k","t4_viirs_media_k")):
            valid=[(p[ma],p[va]) for p in grupo if p[ma] is not None and p[va] is not None]
            x=[a for a,b in valid]; y=[b for a,b in valid]
            r=pearson(x,y)
            diffs=[b-a for a,b in valid]
            rows.append({"modis":m,"viirs":v,"dia_noche":dn,"banda":name,
                         "pares":len(valid),"pearson_exploratoria":round(r,4) if r is not None else "",
                         "mediana_viirs_menos_modis_k":round(statistics.median(diffs),4) if diffs else "",
                         "nota":"no_conversion_directa_entre_bandas"})
    cols=["modis","viirs","dia_noche","banda","pares",
          "pearson_exploratoria","mediana_viirs_menos_modis_k","nota"]
    return rows,cols


def quality_diagnostics(obs):
    return {s:{"detecciones_type0":sum(o["source"]==s and o["type"]=="0" for o in obs),
               "baja_confianza":sum(o["source"]==s and o["confidence"]=="l" for o in obs),
               "frp_invalido_cero_nulo":sum(o["source"]==s and o["frp"] is None for o in obs)}
            for s in SENSORS}


def sensitivity(records):
    out = []
    for km in GRID_SIZES:
        for shift in (0.0,.5):
            cells = presence(records,km,shift)
            pr = presence_stats(cells)
            passes = make_passes(records, km, shift)
            for window in WINDOWS:
                pairs = paired_passes(passes,window)
                out.append({"celda_km":km,"desplazamiento_fraccion_celda":shift,
                            "ventana_min":window,"celdas_dia_union":pr["union"],
                            "celdas_dia_ambos":pr.get("ambos",0),
                            "celdas_dia_solo_modis":pr.get("solo_modis",0),
                            "celdas_dia_solo_viirs":pr.get("solo_viirs",0),
                            "pares_pasadas_candidatas":len(pairs),
                            "pares_frp_ambos_validos":sum(p["frp_modis_mw"] is not None and
                                                       p["frp_viirs_mw"] is not None for p in pairs)})
    return out


def report(folder, pais, anio, stats, pairs, relations, quality, args, sens, diag):
    sources_desc = ', '.join(diag['sources'])
    warnings = [
      'Las celdas-día registran presencia de detecciones, NO cantidad de incendios ni área quemada.',
      'La grilla utiliza centros de píxel y una proyección aproximada; NO representa huellas exactas.',
      'Una coincidencia por celda, pasada y tiempo no confirma que ambos sensores observaron el mismo fuego.',
      'Falta la máscara de cobertura, nubes y observaciones negativas: sin detección no equivale a ausencia de fuego.',
      'Las bandas de 4 y 11 micrómetros y las escalas de confianza NO son directamente equivalentes.',
      'La agregación de FRP es SOLO dentro de un mismo satélite, celda y pasada; nunca se suman plataformas.',
      'VIIRS FRP puede repartirse desde información de píxeles de 750 m entre detecciones de 375 m.',
      'Un factor FRP basado en un año y una región NO sirve aún para convertir series históricas MODIS a VIIRS.',
      'En 2024 faltan datos NOAA-21 en esta muestra, aunque el sensor está disponible por separado en FIRMS.',
    ]
    text = f'''# Nodara Tech — Informe técnico de armonización v2

**Región:** {pais}  
**Año:** {anio}  
**Unidad común:** celda de {args.cuadricula:g} × {args.cuadricula:g} km / día UTC  
**Comparación de pasadas:** hasta {args.ventana} minutos, separando plataforma y día/noche  
**Filtro:** `type=0`; calidad VIIRS: {args.calidad}

## Qué se logró

- Leer MODIS, VIIRS S-NPP y VIIRS NOAA-20 desde CSV o ZIP sin cambiar originales.
- Crear un esquema común de fechas, ubicación, FRP, tamaño aproximado y procedencia.
- Registrar **una sola vez** cada celda-día con detección, sin sumar todos los píxeles.
- Separar por plataforma y pasada (grupo local de máximo {PASS_SPAN_MIN} minutos) para comparar FRP agregado dentro de una misma fuente.
- Emparejar pasadas por misma celda, día/noche y ventana horaria, usando además una media diagonal aproximada de `scan/track` de cada fuente más tolerancia de 250 m. Emparejamiento 1 a 1 **dentro de cada par concreto de plataformas**; NO reconstruye huellas exactas.
- Examinar relación FRP entre pares satelitales y guardar un diagnóstico exploratorio, condicionado a tamaño muestral.
- Probar sensibilidad con celdas de 2, 5 y 10 km y ventanas de 15, 30, 60, 120 minutos.

## Resultados con los datos recibidos

| Indicador | Valor |
|---|---:|
| Detecciones validas (todos los tipos) | {diag['valid_total']:,} |
| Detecciones type=0, filtro calidad aplicado | {diag['used_total']:,} |
| Celdas-día activas, unión | {stats['union']:,} |
| Coincidencias en celdas-día de ambas familias | {stats.get('ambos',0):,} |
| Solo MODIS, celdas-día | {stats.get('solo_modis',0):,} |
| Solo VIIRS, celdas-día | {stats.get('solo_viirs',0):,} |
| Parejas candidatas de pasadas ({args.ventana} min) | {len(pairs):,} |
| Pares con FRP válido en ambos lados | {sum(p['frp_modis_mw'] is not None and p['frp_viirs_mw'] is not None for p in pairs):,} |

## Relación empírica de FRP

Se estima, como **diagnóstico**, la mediana de la relación `FRP_VIIRS_agregado / FRP_MODIS_agregado` por plataforma y por día/noche. Se exige FRP >= 5 MW en ambos lados y datos completos. Se separan fechas de entrenamiento y evaluación cronológicamente, sin mezclar observaciones de un mismo día entre ambos grupos. Los resultados por plataforma están en `diagnostico_frp_por_plataforma.csv`.

Un criterio experimental mínimo exige 20 pares de entrenamiento, 8 de prueba, 8/3 fechas independientes respectivamente, correlación en prueba ≥ 0.75 y error relativo mediano en prueba ≤ 25 %. Estos umbrales son decisiones del prototipo, NO estándares de NASA. El campo `supera_criterio_exploratorio` indica si alguna relación consigue superar todos.

El diagnóstico **no constituye un modelo calibrado** para traducir datos de 2000–2025. Se requieren más años, regiones, datos de cobertura, estudio de calidad y validación externa.

## Límites importantes

'''+ '\n'.join(f'- {x}' for x in warnings)+f'''

## Archivos del motor

- `registros_normalizados_v2.csv`: entradas con sus magnitudes conservadas.
- `armonizacion_celdas_dia_v2.csv`: indicador de presencia y fuente por celda y día.
- `calendario_diario_v2.csv`, `calendario_mensual_v2.csv`: series para el prototipo.
- `coincidencias_pasadas_frp.csv`: pares candidatos Terra/Aqua frente a S-NPP/NOAA-20.
- `diagnostico_frp_por_plataforma.csv`: razón FRP agregada, tamaño de muestra, prueba temporal y control de error.
- `comparacion_termica_por_plataforma.csv`: correlaciones/diferencias de bandas cercanas a 4 y 11 µm.
- `sensibilidad_parametros.csv`: estabilidad al cambiar parámetros.
- `diagnostico_v2.json`: parámetros, procedencia y validaciones.

## Fuentes

- NASA FIRMS MODIS: https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_MODIS_Firehotspots.html
- NASA FIRMS VIIRS: https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html
- Li et al. (2018), comparación FRP: https://doi.org/10.1029/2017JD027823
- NASA VIIRS Active Fire Algorithm: https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html

**Origen de datos:** {sources_desc}
'''
    (folder/"INFORME_NODARA_v2.md").write_text(text, encoding="utf-8")


def run(args):
    found = sources()
    if not found:
        raise RuntimeError("No se encontraron CSV; coloca la carpeta datos_firms o datos_firms.zip junto al programa")
    paises = sorted({v[0][2] for v in found.values()})
    pais, anio = choose(paises, args.pais, args.anio, found)
    folder = OUT / pais.replace(" ", "_") / str(anio)
    if (args.cuadricula, args.ventana, args.calidad) != (2.,30,"todas"):
        folder = folder / "escenarios" / f"celda_{args.cuadricula:g}km_t_{args.ventana}min_{args.calidad}"
    folder.mkdir(parents=True,exist_ok=True)
    obs=[]; diag_sources=[]; invalid=Counter(); input_counts=Counter()
    print(f"\nAnalizando {pais} / {anio} | cuadricula {args.cuadricula} km | ventana {args.ventana} min")
    for sensor in SENSORS:
        s = found.get((sensor,anio,keytext(pais)))
        if not s:
            print(f"  {sensor}: NO disponible (no confundir con cero incendios)")
            continue
        diag_sources.append(f"{sensor} ({s[2].name})")
        for idx,row in enumerate(read_csv(s),1):
            input_counts[sensor]+=1
            try:obs.append(parse_row(row,sensor,pais,anio,idx))
            except (ValueError,KeyError,TypeError,OverflowError):invalid[sensor]+=1
        print(f"  {sensor}: leidos {input_counts[sensor]}, invalidos {invalid[sensor]}")
    if not obs: raise RuntimeError("No hay observaciones validas")
    normalized_csv(folder/"registros_normalizados_v2.csv", obs)
    records = [o for o in obs if is_allowed(o,args.calidad)]
    stats,_=presence_files(folder, records,args.cuadricula)
    groups = make_passes(records, args.cuadricula)
    pairs = paired_passes(groups,args.ventana)
    csv_write(folder/"coincidencias_pasadas_frp.csv",pairs,PAIR_COLUMNS)
    relation, cols = robust_relation(pairs)
    csv_write(folder/"diagnostico_frp_por_plataforma.csv", relation, cols)
    therm, therm_cols = thermal_relations(pairs)
    csv_write(folder/"comparacion_termica_por_plataforma.csv", therm, therm_cols)
    sens = sensitivity(records)
    csv_write(folder/"sensibilidad_parametros.csv", sens,
              ["celda_km","desplazamiento_fraccion_celda","ventana_min",
               "celdas_dia_union","celdas_dia_ambos","celdas_dia_solo_modis",
               "celdas_dia_solo_viirs","pares_pasadas_candidatas","pares_frp_ambos_validos"])
    diag={"pais":pais,"anio":anio,"parameters":{"grid_km":args.cuadricula,
           "pass_window_minutes":args.ventana,"pass_span_minutes":PASS_SPAN_MIN,
           "quality":args.calidad},"sources":diag_sources,"input_counts":dict(input_counts),
           "invalid_rows":dict(invalid),"quality":quality_diagnostics(obs),
           "valid_total":len(obs),"used_total":len(records),
           "cell_day_proxy":stats,"candidate_pairs":len(pairs),
           "frp_relations":relation,
           "thermal_relations":therm,
           "limitations":"no observational coverage masks; no historical calibration; 1 cell-day != 1 fire"}
    (folder/"diagnostico_v2.json").write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding="utf-8")
    report(folder,pais,anio,stats,pairs,relation,quality_diagnostics(obs),args,sens,diag)
    print("\nRESULTADO V2 (aproximado):")
    print(f"  Registros validos: {len(obs)} | filtro type=0/calidad: {len(records)}")
    print(f"  Celdas-dia unicas: {stats['union']}")
    print(f"  Ambos MODIS-VIIRS: {stats.get('ambos',0)} | Solo MODIS: {stats.get('solo_modis',0)} | Solo VIIRS: {stats.get('solo_viirs',0)}")
    print(f"  Parejas candidatas por pasadas: {len(pairs)}")
    print(f"  Comparaciones FRP por plataforma: {len(relation)}")
    print(f"  Resultados guardados: {folder}")
    print("  IMPORTANTE: NO es una calibracion historica validada.")
    return folder,diag


def main():
    p=argparse.ArgumentParser(description="Motor experimental de armonizacion MODIS-VIIRS de Nodara Tech")
    p.add_argument("--pais", default=None, help='Ejemplo: "Costa Rica" o Afghanistan')
    p.add_argument("--anio", type=int, default=None, help="Ejemplo: 2024")
    p.add_argument("--cuadricula", type=float, choices=[2.,5.,10.], default=2., help="Tamano km, defecto 2")
    p.add_argument("--ventana", type=int, choices=[15,30,60,120], default=30, help="Diferencia temporal maxima minutos")
    p.add_argument("--calidad", choices=["todas","sin_l_viirs"], default="todas", help="Filtro VIIRS baja confianza (experimental)")
    args=p.parse_args()
    try:run(args)
    except (RuntimeError,ValueError) as e:
        print(f"ERROR: {e}")
        raise SystemExit(1)

if __name__ == "__main__":main()
