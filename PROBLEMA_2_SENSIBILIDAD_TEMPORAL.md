# Nodara Tech v3.3 — Problema 2: sensibilidad temporal

## Qué problema se abordó

En la v3.2, la etiqueta **"Ambos con pasada cercana"** dependía de una única ventana temporal de 30 minutos. Era un parámetro de ingeniería, no una tolerancia demostrada como óptima. Contar más parejas al aumentar el margen no significa mejorar exactitud.

## Qué se implementó

1. **Ventanas de 15, 30, 60 y 120 minutos**, seleccionables en el visor. El valor 30 queda como **referencia histórica del prototipo**, no como valor validado científicamente.
2. Todas las ventanas se evalúan sobre **los mismos registros** y la **misma cuadrícula v2**, con los mismos algoritmos `make_passes` y `paired_passes`, distancia de centroides, condición día/noche, coincidencia de celda, FRP y reglas 1 a 1 por par de plataformas. Solo cambia el tope temporal. La agrupación interna por pasada permanece en **12 minutos** y sigue siendo experimental.
3. **Dos indicadores independientes**: número de parejas candidatas y número de **celdas-día compartidas con al menos una pareja cercana**. El segundo evita interpretar varias parejas dentro de una celda como varios incendios.
4. La vista **Zonas → Cuadrícula v2**, la vista **Cruces**, el panel **"¿Coinciden también en el tiempo?"** y el nuevo panel **"Sensibilidad de la ventana temporal"** se sincronizan con la selección. **Las celdas activas y las detecciones originales no cambian.**
5. Se calculan intervalos bootstrap re-muestreando días con actividad de ambos sensores para describir **variación interna** del porcentaje de celdas compartidas con pareja cercana. **No son intervalos de precisión, sensibilidad clínica, especificidad ni probabilidad de incendio real.**
6. **H3 no cambia**: sus polígonos siguen reflejando coincidencia diaria. La ventana seleccionable se aplica a los pares de la cuadrícula v2, **no** al método H3 (problema 3, pendiente).
7. Se comprueba automáticamente que el escenario base reproduce exactamente la partición de P1, que los conteos son coherentes y que aumentar la ventana no hace desaparecer celdas ya clasificadas como cercanas.

## Resultados reales 2024 (cuadrícula 2 km)

| País | Ventana | Parejas candidatas | Celdas-día con ambos sensores | Celdas con pareja cercana | Compartidas solo por día |
|---|---:|---:|---:|---:|---:|
| Costa Rica | 15 min | 167 | 527 | 167 | 360 |
| Costa Rica | 30 min | 370 | 527 | 313 | 214 |
| Costa Rica | 60 min | 532 | 527 | 374 | 153 |
| Costa Rica | 120 min | 625 | 527 | 399 | 128 |
| Afganistán | 15 min | 9 | 34 | 9 | 25 |
| Afganistán | 30 min | 18 | 34 | 17 | 17 |
| Afganistán | 60 min | 25 | 34 | 21 | 13 |
| Afganistán | 120 min | 34 | 34 | 25 | 9 |

**Costa Rica, 31 de marzo de 2024:**

| Ventana | Parejas de pasada del día | Compartidas con pareja cercana | Compartidas solo por fecha |
|---:|---:|---:|---:|
| 15 min | 33 | 33 | 18 |
| 30 min | 65 | 38 | 13 |
| 60 min | 65 | 38 | 13 |
| 120 min | 65 | 38 | 13 |

**Interpretación estadística:** pasar de 30 a 60 min aumenta las parejas anuales de Costa Rica de 370 a 532 (+43,8 %) y las celdas compartidas con pareja cercana de 313 a 374 (+19,5 %). De 60 a 120 min se agregan 93 parejas pero solo 25 nuevas celdas compartidas cercanas. Este rendimiento decreciente es un **diagnóstico**, no prueba de que 30 o 60 min tengan menos falsos positivos.

### ¿Qué ventana conviene?

- **15 min:** escenario estricto; puede omitir coincidencias plausibles cuando las pasadas son más separadas.
- **30 min:** referencia previa; conserva comparabilidad con P1 y el modelo de FRP original.
- **60 min:** análisis secundario para estudiar el impacto de diferencias de horario, especialmente NOAA-20 respecto de Aqua; todavía sin validación independiente.
- **120 min:** prueba de estrés, no se recomienda usarla como umbral por defecto sin evidencia externa.

NASA describe horarios de pasada diferentes para Terra, Aqua y las plataformas VIIRS. Un mismo incendio puede cambiar de intensidad entre pasadas; la mayor cercanía temporal no prueba por sí misma identidad del fuego.

**Decisión estadística:** mantener 30 min como valor de referencia, mostrar resultados de sensibilidad a 15/60/120 y **no escoger automáticamente** la ventana con más parejas. Una selección científica necesitará máscaras de observación/nubosidad, geometría de huellas mejor definida y coincidencias verificadas con información independiente. La ventana afecta los emparejamientos pero no elimina el problema de cobertura ni calibra el FRP.

## Archivos adicionales producidos por conjunto

La subcarpeta `sensibilidad_temporal_v3_3/` se genera automáticamente al abrir el observatorio:

- `resumen_ventanas.csv`: indicadores globales, proporciones e intervalos bootstrap internos.
- `concordancia_ventanas_diaria.csv`: resumen por día UTC y ventana.
- `concordancia_ventanas_celdas.csv`: clasificación por celda compartida y ventana.
- `parejas_ventanas.csv`: pares originales reestimados para cada ventana, con plataforma, distancia y tiempo.
- `plataformas_ventanas.csv`: comparaciones por plataforma y día/noche.
- `diagnostico_sensibilidad.json`: parámetros, firma del procesamiento y limitaciones.

Los datos NASA y todos los archivos originales de v2, P1 y H3 **se conservan sin modificar**.

## Cómo actualizar el proyecto de Windows

1. Cierra el servidor (`Ctrl+C`).
2. Extrae `NodaraTech_PARCHE_V3_3_PROBLEMA2.zip`.
3. Copia **el contenido**, incluida la carpeta `aplicacion`, en `Descargas\\NodaraTech_Observatorio_V3_H3` (la carpeta donde está `requirements.txt`). Acepta **Combinar** y **Reemplazar**.
4. NO elimines `datos`, `resultados` ni `cache`. La nueva versión crea automáticamente los archivos de sensibilidad para los conjuntos que abras.
5. En VS Code, desde la raíz del proyecto, ejecuta:

```powershell
py aplicacion\pruebas_problema1.py
py aplicacion\pruebas_problema2.py
py aplicacion\visor_incendios.py
```

6. En Chrome abre `http://127.0.0.1:8765` y pulsa `Ctrl + F5`.
7. Costa Rica 2024 → **Zonas** → **Cuadrícula v2** → fecha **31/03/2024**. Cambia **Ventana de coincidencia por pasada** y revisa el panel **Sensibilidad de la ventana temporal**. La vista **Cruces** también debe cambiar.

## Qué no corrige todavía

- Problema 3: ventanas y emparejamientos temporales específicos para H3.
- Problema 4: comparación de H3 y cuadrícula con áreas o escalas armonizadas.
- Problema 5: evaluación de confianza de detecciones y cobertura de observación.
- Independientemente de estos puntos, la equivalencia radiométrica de FRP continúa **no validada**.

## Fuentes externas

- NASA FIRMS: https://firms.modaps.eosdis.nasa.gov/
- NASA Active Fire / archivos históricos: https://firms.modaps.eosdis.nasa.gov/content/active_fire/
- NASA FIRMS FAQ / horarios de pasada: https://www.earthdata.nasa.gov/data/tools/firms/faq
