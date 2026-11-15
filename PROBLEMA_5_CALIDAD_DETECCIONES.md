# Nodara Tech · v3.6 · Problema 5: evaluación de sensibilidad a confianza de detecciones

## Qué se corrigió

Se agregó un módulo independiente `aplicacion/calidad_detecciones_v3_6.py` que **conserva y compara** los indicadores nativos de calidad de NASA FIRMS. No convierte MODIS `confidence` (numérico 0–100) a las clases `l/n/h` de VIIRS. Los umbrales MODIS 50 y 80 son **escenarios elegidos para sensibilidad**, NO probabilidades ni recomendaciones universales.

Seis escenarios sobre el **mismo universo de detecciones `type=0`**:

| ID | MODIS | VIIRS |
|---|---|---|
| `todas` | Sin umbral | l, n, h y valores originales |
| `viirs_nh` | Sin umbral | Solo n y h |
| `modis50` | 50–100 | Todas |
| `ambos50` | 50–100 | Solo n y h |
| `modis80` | 80–100 | Todas |
| `ambos80` | 80–100 | Solo n y h |

Los datos de calidad ausentes o no válidos quedan conservados en el escenario `todas`, pero no pasan un umbral MODIS ni el filtro de clases VIIRS n/h. La auditoría incluye la distribución de categorías por fuente y período diurno/nocturno para descubrir exclusiones selectivas.

## Procedimiento reproducible

1. Leer `registros_normalizados_v2.csv` **sin alterar el archivo** y seleccionar `type=0` (criterio fijo).
2. Filtrar observaciones según las reglas originales de MODIS/VIIRS, **antes** de rearmar las pasadas.
3. Recalcular cuadrícula v2 (tamaño de celda propio del conjunto, sin vecinos) y H3 r7 (misma celda + vecinos, respetando tiempo, tolerancia aproximada de huella y asignación 1:1 por plataformas).
4. Utilizar la misma ventana temporal elegida en el visor para todos los seis escenarios.
5. Comparar registros admitidos, celdas-día activas/compartidas, parejas y celdas compartidas con pareja; añadir datos diarios y exportación a CSV.
6. Reportar variaciones **respecto de `todas`**, sin llamarlas mejoras de exactitud.

La partición espacial, agrupación de pasadas y asignación de candidatos se **vuelven a calcular** tras filtrar. Si una pasada cambia de composición, la pareja elegida puede cambiar; por tanto las diferencias de conteos no equivalen exactamente al número de parejas falsas descartadas.

## Resultados reproducidos aquí: Costa Rica 2024, cuadrados 2 km, 30 minutos

| Escenario | Registros type=0 | Parejas candidatas |
|---|---:|---:|
| Todas las detecciones | 13.836 | 370 |
| VIIRS solo n/h | 12.182 | 348 |
| MODIS ≥50 | 13.657 | 333 |
| MODIS ≥50 y VIIRS n/h | 12.003 | 312 |
| MODIS ≥80 | 13.015 | 133 |
| MODIS ≥80 y VIIRS n/h | 11.361 | 127 |

En Costa Rica se registran **1.654 detecciones `type=0` VIIRS categoría `l`**, todas clasificadas como diurnas en este archivo. Con `viirs_nh` las celdas-día cuadradas activas pasan de 6.023 a 5.529 y las celdas compartidas de 527 a 508. Las celdas compartidas con pareja próxima pasan de 313 a 297.

La exclusión `l` elimina el 13,1 % de las detecciones VIIRS, pero la reducción de parejas candidatas en cuadrícula es de 5,9 %. **Ninguna de estas magnitudes es sensibilidad, precisión, especificidad ni porcentaje de falsas alarmas**.

## Información que el visor ofrece

El panel `Auditoría de calidad de detecciones · v3.6` se ejecuta **a solicitud**, para no recalcular todo el año al navegar el calendario. Muestra una tabla de seis escenarios con conteo anual de parejas por cuadrados y H3 y conteo de parejas correspondiente a la fecha seleccionada. El mapa central **conserva el escenario original sin filtros**; el panel es explícitamente una auditoría de sensibilidad, no un interruptor que modifique silenciosamente el mapa. El CSV de resultados se guarda junto al conjunto de datos, en:

`calidad_detecciones_v3_6/t_30min/escenarios_calidad.csv`

El calendario de escenarios se guarda en `calendario_calidad.csv`, y los datos de referencia y advertencias en `diagnostico_calidad.json`. También admite ventanas 15, 60 y 120 minutos.

## Verificación

- `py aplicacion\pruebas_problema5.py`: pruebas de filtros, valores desconocidos, reagrupación, SQL/API HTTP y Costa Rica/Afganistán en cuadrícula. **El H3 de esta prueba es sintético**.
- `py aplicacion\pruebas_problema5_reales.py`: en Windows, utiliza H3 **4.x oficial** instalado y verifica que la fila `todas` conserve las parejas H3 publicadas por v3.4 (Costa Rica 452, Afganistán 19) y por cuadrícula (370 y 18). No confundir verificación de código con validación externa de correspondencias.
- Las pruebas P1–P4 siguen disponibles y no se modifican sus datos ni módulos.

## Limitaciones científicas (obligatorias)

1. NASA especifica que la confianza MODIS 0–100 es experimental; no es probabilidad calibrada de incendio. En VIIRS, `h` se relaciona con saturación térmica, no con una garantía del 90 % o 100 % de certeza.
2. Filtrar modifica distribuciones diurnas/nocturnas, cobertura por sensor, tamaño de muestra y alcance de la comparación. En Costa Rica los 1.654 registros VIIRS `l` de `type=0` son diurnos; descartar indiscriminadamente `l` puede sesgar indicadores entre día y noche.
3. El filtro de 50/80 para MODIS es arbitrario en esta fase y sirve solamente para estudiar robustez de resultados.
4. Un filtro más estricto puede excluir focos reales y no compensa errores de observación por nubes, humo, horarios o tamaños de píxel.
5. La auditoría no estima tasa de falsas alarmas, falsos negativos, precisión, recall, calibración radiométrica ni área quemada. Faltan observaciones independientes, máscaras de cobertura, años adicionales y validación por región/plataforma/horario.
6. El conjunto normalizado de cada región/año se utiliza como universo base. Si el resultado v2 anterior se ejecutó con un filtro `sin_l_viirs`, su calendario habitual podría no coincidir con la fila de referencia sin filtro. Este hecho queda explicitado en `calidad_original_v2`.

## Fuentes institucionales

- NASA FIRMS — descripción VIIRS 375 m: https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html
- NASA FIRMS — notas y confianza MODIS: https://firms.modaps.eosdis.nasa.gov/alerts/notes.php
- NASA FIRMS — portal y datos: https://firms.modaps.eosdis.nasa.gov/
