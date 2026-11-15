# Propuesta técnica final — armonización experimental de MODIS y VIIRS

**Equipo:** Nodara Tech  
**Reto:** NASA Space Apps Challenge 2026 — Harmonization of MODIS and VIIRS Hot Spots  
**Alcance:** Prototipo demostrativo. No es una aplicación de emergencias validada.

## 1. Necesidad que resuelve

MODIS ofrece observaciones desde 2000 y VIIRS desde 2012 (S-NPP). Tienen diferencias en geometría, hora de pasada, sensibilidad y respuesta radiométrica. Una unión simple de los CSV haría que aumentaran los conteos cuando VIIRS agrega detecciones que MODIS no podía registrar. La finalidad es permitir una lectura conjunta sin interpretar automáticamente píxeles extra como incendios nuevos.

## 2. Metodología seleccionada

**Unidad primaria para el calendario:** una celda espacial de 2 × 2 km en un día UTC con al menos una detección de presunto incendio de vegetación (`type=0`). Cada celda-día vale 1 en el indicador de presencia. Se guardan por separado MODIS, S-NPP y NOAA-20, sin perder los conteos originales.

**Unidad secundaria para comparar radiación:** una *pasada* satelital por celda y plataforma, formada con observaciones próximas en una ventana interna experimental de 12 min. Un par MODIS–VIIRS se propone solo si comparte celda, día/noche y presenta una separación temporal no mayor de 30 min. Además, para disminuir falsos emparejamientos se exige que la separación entre centroides esté dentro de un umbral geométrico **aproximado**: la suma de las medias diagonales de sus píxeles máximos (`scan`, `track`) más 250 m. No sustituye polígonos de huella reales.

Separa expresamente Terra, Aqua, S-NPP y NOAA-20. El FRP se suma **dentro de un solo satélite y pasada** por celda; se deja en columnas separadas para MODIS y VIIRS. Nunca se suman FRP de distintos satélites para producir una única intensidad.

**Relación exploratoria:** mediana de `FRP_VIIRS / FRP_MODIS` en parejas con FRP válido >= 5 MW en ambos lados, separando plataforma y condición día/noche. Se entrena con el 70 % inicial de las fechas observadas y se evalúa con el resto. Las pruebas para distintos tamaños de celda (2, 5, 10 km) y ventanas (15, 30, 60, 120 min) comprueban dependencia de parámetros.

Los umbrales de agrupación, error y muestras son **decisiones experimentales del prototipo, no recomendaciones oficiales NASA**.

## 3. Resultados reales — Costa Rica, 2024

Basado en los CSV aportados de NASA FIRMS:

| Métrica | Resultado |
|---|---:|
| MODIS, registros originales | 1.241 |
| VIIRS S-NPP, registros originales | 6.341 |
| VIIRS NOAA-20, registros originales | 6.359 |
| Total original | 13.941 |
| Filas `type=0` utilizadas | 13.836 |
| Celdas-día activas únicas (2 km) | 6.023 |
| Celdas-día con MODIS y VIIRS | 527 |
| Celdas-día solo MODIS | 413 |
| Celdas-día solo VIIRS | 5.083 |
| Parejas candidatas por pasada <=30 min y geometría aproximada | 370 |

Estas 370 parejas son *candidatas*; no son 370 incendios verificados.

### Prueba de equivalencia de FRP (día)

| Par | Parejas aptas para prueba | Factor mediano exploratorio VIIRS/MODIS en entrenamiento | Error relativo mediano en fechas reservadas | ¿Pasa criterios experimentales? |
|---|---:|---:|---:|---|
| MODIS Aqua – VIIRS NOAA-20 | 165 | 0,6992 | 48,8 % | No |
| MODIS Aqua – VIIRS S-NPP | 142 | 0,7323 | 55,1 % | No |

Los números obtenidos **descartan la idea de utilizar esos factores como una equivalencia confiable de FRP**. Son relaciones locales de esta muestra y cambian con la selección de celdas, tiempo y condiciones de observación. En otras palabras, el experimento aportó un resultado valioso aunque negativo: **se logró comparar, pero no se validó una transformación directa**.

### Sensibilidad al tamaño de celda

| Configuración | Celdas-día activas únicas | Celdas-día vistas por ambas familias |
|---|---:|---:|
| 2 km, sin desplazamiento | 6.023 | 527 |
| 5 km, sin desplazamiento | 4.893 | 529 |
| 10 km, sin desplazamiento | 4.113 | 518 |

El indicador de presencia depende de la escala espacial. Por ello el prototipo debe **mostrar explícitamente la escala**; no se deben comparar series calculadas con cuadrículas de distinto tamaño.

## 4. Otros casos probados

- **Afganistán 2024:** 1.246 registros válidos; 1.169 tipo 0, 740 celdas-día, 18 parejas candidatas.
- **Afganistán 2000 (solo MODIS):** 6 registros válidos; 6 celdas-día, 0 parejas. La inexistencia de VIIRS en 2000 no se interpreta como ausencia de fuego.
- **Costa Rica 2024, sin confianza VIIRS `l`:** 12.182 observaciones utilizadas tras el filtro; 5.529 celdas-día, 348 parejas. Es una **prueba de sensibilidad, no un filtro universal recomendado**.

## 5. Interpretación y limitaciones

- La ubicación reportada es el centro del píxel, no la posición exacta de la llama. La aproximación de huella no reconstruye polígonos orientados.
- Una detección por sensor no representa un incendio individual. Una celda puede contener varios focos o uno observado varias veces.
- `brightness` (MODIS) y `bright_ti4` (VIIRS), `bright_t31` (MODIS) y `bright_ti5` (VIIRS), no son idénticos. Sus correlaciones son solo diagnósticas.
- `confidence` MODIS 0–100 y VIIRS `l/n/h` no tienen equivalencias porcentuales válidas.
- La suma FRP de varios píxeles se restringe a una pasada y sensor; los FRP VIIRS de 375 m se pueden derivar de observaciones de 750 m y repartir entre subpíxeles.
- Sin máscaras de nubes y cobertura, un sensor que no registra foco no prueba observación válida sin incendio. La armonización histórica requiere esta distinción.
- La disponibilidad desde 2000 (MODIS) y 2012 (VIIRS S-NPP) implica que añadir VIIRS modifica la sensibilidad histórica; no se ha corregido aún ese salto.

## 6. Qué falta para una armonización histórica validada

1. Años de traslape adicionales en el mismo territorio (idealmente 2012–2025 para S-NPP, períodos más recientes para NOAA-20).
2. Información de cobertura/nubes, ángulo de observación y oportunidades de pasada.
3. Huellas reales de píxel o productos geoespaciales precisos si se busca correspondencia física.
4. Validación fuera de muestra por **año** y región, no solo por fechas del mismo año.
5. Comparar también el producto **VIIRS de 750 m**, que NASA diseñó para continuidad con MODIS de 1 km (línea futura de investigación; no incluido en los CSV actuales).

## 7. Recomendación para presentar el prototipo

La afirmación defendible es:

> «Desarrollamos un prototipo que mantiene MODIS y VIIRS por separado, los representa en una unidad espacio-temporal común y compara pasadas con FRP agregado. Probamos la estabilidad del método y demostramos que una conversión directa entre sensores no es fiable con una sola región y un año; por eso documentamos incertidumbre y dejamos claramente identificada la calibración histórica pendiente».

NO afirmar que el sistema cuantifica incendios reales, superficie quemada o que reconstruyó automáticamente todo el historial calibrado desde 2000.

## Referencias científicas

- NASA FIRMS, descripción MODIS: https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_MODIS_Firehotspots.html
- NASA FIRMS, descripción VIIRS: https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html
- NASA GSFC, VIIRS Active Fire Product: https://viirsland.gsfc.nasa.gov/Products/NASA/FireESDR.html
- Li et al. (2018), *Comparison of Fire Radiative Power Estimates From VIIRS and MODIS Observations*, JGR Atmospheres: https://doi.org/10.1029/2017JD027823
- NASA FIRMS, datos activos y archivo: https://firms.modaps.eosdis.nasa.gov/active_fire/
