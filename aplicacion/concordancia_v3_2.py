"""Nodara Tech v3.2 — SOLAMENTE corrección del problema 1.

Separa coincidencia diaria (misma celda/cuadrícula y fecha UTC) de
coincidencia cercana por pasada (par MODIS-VIIRS del motor v2 dentro
sus filtros espaciales y temporales). No reinterpreta detecciones como
incendios individuales ni añade umbrales científicos no validados.

El análisis por pasada procede de la cuadrícula v2, NO de H3. Los
hexágonos H3 conservan su clasificación de actividad diaria.
"""
from __future__ import annotations
import csv
import json
import os
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

LEVELS = ('ambos_paso_cercano', 'ambos_solo_dia', 'solo_modis', 'solo_viirs')
OUTPUT = 'concordancia_v3_2'
VERSION = '3.2-P1'


def read_rows(filename):
    with Path(filename).open('r', encoding='utf-8-sig', newline='') as file:
        yield from csv.DictReader(file)


def write_rows(filename, cols, rows):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    with filename.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=cols, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def classify(cell_class, nearby):
    if cell_class == 'ambos':
        return 'ambos_paso_cercano' if nearby else 'ambos_solo_dia'
    if cell_class in ('solo_modis', 'solo_viirs'):
        return cell_class
    raise ValueError(f'Clasificación inesperada: {cell_class}')


def build(folder: Path, force=False):
    folder = Path(folder).resolve()
    cells_file = folder / 'armonizacion_celdas_dia_v2.csv'
    pairs_file = folder / 'coincidencias_pasadas_frp.csv'
    diag_file = folder / 'diagnostico_v2.json'
    for f in (cells_file, pairs_file, diag_file):
        if not f.is_file():
            raise FileNotFoundError(f'Falta un archivo necesario del motor v2: {f}')

    diag = json.loads(diag_file.read_text(encoding='utf-8-sig'))
    window = float(diag.get('parameters', {}).get('window_minutes', diag.get('parameters', {}).get('ventana', 30)))
    # Compatibilidad con las claves del diagnóstico existente.
    params = diag.get('parameters', {})
    window = float(params.get('pass_window_minutes', params.get('minutes', params.get('time_window_minutes', params.get('ventana', window)))))
    signature = {'version': VERSION,
                 'files': [(x.name, x.stat().st_size, x.stat().st_mtime_ns) for x in (cells_file, pairs_file, diag_file)]}
    dst = folder / OUTPUT
    manifest_file = dst / 'diagnostico_concordancia.json'
    cells_out = dst / 'concordancia_celdas_dia.csv'
    daily_out = dst / 'concordancia_diaria.csv'
    monthly_out = dst / 'concordancia_mensual.csv'
    if not force and all(p.is_file() for p in (manifest_file, cells_out, daily_out, monthly_out)):
        try:
            manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
            if manifest.get('signature') == signature:
                return dst, manifest
        except (ValueError, OSError):
            pass

    cells = {}
    for row in read_rows(cells_file):
        key = (row['fecha_utc'], row['celda'])
        if key in cells:
            raise ValueError(f'Celda-día duplicada: {key}')
        cells[key] = row

    near = Counter()
    unusual = Counter()
    for pair in read_rows(pairs_file):
        try:
            mtime = datetime.fromisoformat(pair['fecha_modis_utc'].rstrip('Z'))
            vtime = datetime.fromisoformat(pair['fecha_viirs_utc'].rstrip('Z'))
            dist = float(pair['distancia_centroides_km'])
            maxdist = float(pair['umbral_huella_aprox_km'])
            mins = abs((mtime - vtime).total_seconds()) / 60
        except (ValueError, KeyError, TypeError):
            unusual['pares_con_campos_invalidos'] += 1
            continue
        if mins > window + 1e-5 or dist > maxdist + 1e-5:
            unusual['pares_fuera_de_criterios'] += 1
            continue
        if mtime.date() != vtime.date():
            unusual['pares_cruzan_medianoche_utc'] += 1
            continue
        key = (mtime.date().isoformat(), pair['celda'])
        if key not in cells or cells[key]['clasificacion'] != 'ambos':
            unusual['pares_sin_celda_compartida'] += 1
            continue
        near[key] += 1

    output_rows = []
    daily = defaultdict(Counter)
    monthly = defaultdict(Counter)
    totals = Counter()
    for (day, cell), row in sorted(cells.items()):
        count = near[(day, cell)]
        level = classify(row['clasificacion'], count > 0)
        output_rows.append({**row, 'nivel_concordancia': level,
                            'parejas_pasada_cercana': count,
                            'criterio_pasada_min': window,
                            'nota': ('Hay al menos una pareja candidata de pasadas' if count else
                                     'Ambos sensores en el día; sin pareja cercana identificada' if level == 'ambos_solo_dia' else
                                     'Solo una familia con detección registrada')})
        daily[day][level] += 1
        monthly[day[:7]][level] += 1
        totals[level] += 1
        daily[day]['celdas_activas'] += 1
        monthly[day[:7]]['celdas_dia_activas'] += 1

    # Fechas sin detecciones en el calendario v2 también se incluyen con cero.
    calendar = folder / 'calendario_diario_v2.csv'
    if calendar.exists():
        for row in read_rows(calendar):
            daily[row['fecha_utc']]

    allcols = list(next(iter(output_rows)).keys()) if output_rows else [
        'fecha_utc', 'celda', 'clasificacion', 'nivel_concordancia', 'parejas_pasada_cercana',
        'criterio_pasada_min', 'nota']
    write_rows(cells_out, allcols, output_rows)
    level_cols = ['ambos_paso_cercano','ambos_solo_dia','solo_modis','solo_viirs']
    write_rows(daily_out, ['fecha_utc', 'celdas_activas']+level_cols,
               [{'fecha_utc':dt, 'celdas_activas':n['celdas_activas'], **{z:n[z] for z in level_cols}}
                for dt,n in sorted(daily.items())])
    write_rows(monthly_out, ['mes_utc', 'celdas_dia_activas']+level_cols,
               [{'mes_utc':dt, 'celdas_dia_activas':n['celdas_dia_activas'], **{z:n[z] for z in level_cols}}
                for dt,n in sorted(monthly.items())])
    if sum(totals.values()) != len(cells):
        raise AssertionError('La partición dejó celdas sin clasificar')
    both = totals['ambos_paso_cercano'] + totals['ambos_solo_dia']
    diag2 = {'version': VERSION, 'signature':signature, 'time_window_minutes':window,
             'geometry_for_nearby':'cuadricula_v2', 'matching_source':'coincidencias_pasadas_frp.csv',
             'daily_both':both, 'daily_both_with_nearby_pair':totals['ambos_paso_cercano'],
             'daily_both_without_nearby_pair':totals['ambos_solo_dia'],
             'only_modis':totals['solo_modis'], 'only_viirs':totals['solo_viirs'],
             'cell_days':len(cells), 'candidate_pairs_in_linked_cells':sum(near.values()),
             'unlinked_pair_reasons':dict(unusual),
             'notice':'Indicadores exploratorios de correspondencia, NO porcentajes de confianza ni incendios confirmados. H3 solo agrupa por día.'}
    manifest_file.write_text(json.dumps(diag2, indent=2, ensure_ascii=False), encoding='utf-8')
    return dst, diag2


def main():
    import argparse
    p=argparse.ArgumentParser(description='Separar concordancia diaria de coincidencia por pasada (P1).')
    p.add_argument('carpeta', type=Path, help='Carpeta que contiene las salidas CSV v2.')
    p.add_argument('--recalcular', action='store_true')
    args=p.parse_args()
    dest, d = build(args.carpeta, force=args.recalcular)
    print('RESULTADO P1:', dest)
    print('Ambos diarios:', d['daily_both'])
    print('Ambos con pareja próxima:', d['daily_both_with_nearby_pair'])
    print('Ambos solo mismo día:', d['daily_both_without_nearby_pair'])
    print('Solo MODIS:', d['only_modis'], '| Solo VIIRS:', d['only_viirs'])
    print('ADVERTENCIA: ninguna categoría confirma el mismo incendio ni constituye confianza estadística.')

if __name__ == '__main__':
    main()
