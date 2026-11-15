# Nodara Tech — Metodología y criterios de la v3

## Objetivo y alcance

Incorporar H3 sin sustituir la cuadrícula v2 ni modificar detecciones originales de NASA FIRMS. Dos métodos espaciales proporcionan un análisis de sensibilidad a la geometría. **Ninguno corrige por sí mismo las diferencias de detección entre MODIS y VIIRS ni estima áreas quemadas.**

## Entrada

El motor v2 normaliza los CSV MODIS y VIIRS a `registros_normalizados_v2.csv`, conservando fecha UTC, coordenadas del centro del píxel, fuente, satélite, tipo, FRP, brillo y confianza original. v3 lee ese archivo y aplica el mismo filtro `type = 0` y, si el escenario v2 lo especifica, descarta VIIRS con `confidence = l`. No reescribe los CSV NASA.

## Método A — Cuadrícula heredada

Se mantiene el procedimiento v2: proyección simplificada, celdas de 2, 5 o 10 km configuradas por cada ejecución, una unidad celda-día por cada cuadrícula con detección. La proyección v2 es aproximada y NO produce cuadrados de área exactamente constante sobre toda la Tierra. Preserva los calendarios y comparaciones FRP del motor ya probado.

## Método B — H3 (nuevo)

Utiliza la biblioteca oficial `h3-py` 4.x y sus funciones `latlng_to_cell(lat, lon, resolution=7)`, `cell_to_boundary(h3_id)`, `cell_to_latlng(h3_id)`, `cell_area(h3_id, unit='km^2')`, `average_hexagon_area(7, unit='km^2')` y `grid_disk(h3_id, 1)`.

La resolución **H3 r7 tiene área media de ~5,1613 km² por hexágono**, frente a ~4 km² de un cuadrado nominal de 2 × 2 km y ~25 km² de 5 × 5 km. Las áreas H3 individuales varían: se informa el área de cada celda, no se pretende convertir una resolución en la otra. H3 contiene algunos pentágonos globales.

Unidad común del análisis: `fecha UTC + identificador de celda H3`. Si hay varias detecciones de cualquier sensor dentro de esa unidad, se cuenta **una celda-día activa** y se preservan los conteos independientes por sensor.

La comparación diaria y mensual muestra los dos totales, su presencia compartida y diferencias. Las diferencias de conteos entre H3 y cuadrícula **NO equivalen a mayor precisión** porque cambia el contorno y el tamaño de las unidades.

### Vecindad para evaluar bordes

Para una celda solo MODIS o solo VIIRS, se consulta `grid_disk(cell,1)` en la misma fecha UTC. Si aparece una detección de la otra familia en un hexágono vecino, se exporta como **posible relación de vecindad**, nunca como coincidencia temporal confirmada. Este análisis no sustituye la comparación de pasadas de 30 minutos ni las huellas reales de los sensores.

## Qué permanece desde v2

- 2 sistemas de fuentes: MODIS Terra/Aqua y VIIRS S-NPP/NOAA-20.
- FRP agrupado **por satélite, pasada y celda de la cuadrícula v2**, no se suman diferentes satélites.
- Parejas candidatas por proximidad espacio-temporal; umbral geométrico aproximado con `scan`/`track`.
- Comparación de temperaturas alrededor de 4 y 11 micras, sin igualarlas directamente.
- Confianza MODIS numérica y VIIRS `l/n/h` sin porcentaje universal.
- Datos de un sensor ausentes no se convierten en detecciones de cero incendios.

## Ficheros nuevos

`espacial_h3_v3/h3_r7/h3_celdas_dia.csv`: presencia por H3 y UTC, conteos de sensores y área individual de la celda.

`h3_calendario_diario.csv`, `h3_calendario_mensual.csv`: calendario en unidades H3, incluidos días sin detecciones reportadas (no implica ausencia de incendios).

`h3_vecindad_exploratoria.csv`: celdas solitarias con vecinos de la familia opuesta; proximidad diaria, NO mismo evento.

`comparacion_metodos_por_dia.csv`: conteos v2 cuadrícula vs H3 por fecha.

`manifiesto_v3.json`: área media, parámetros, registros de entrada, totales y límites científicos.

## Fuentes y lecturas

- H3 API 4.x: https://uber.github.io/h3-py/api_quick.html
- H3 áreas promedio: https://h3geo.org/docs/core-library/restable/
- NASA FIRMS: https://firms.modaps.eosdis.nasa.gov/

## Estado de validación

La sintaxis y la integración de los archivos, API y visor se probaron localmente con simulaciones de la interfaz H3 para verificar el flujo, **no con geometrías H3 reales en este entorno**. La biblioteca H3 no estaba disponible aquí para una prueba física completa. `COMPROBAR.bat` incluye una prueba con `h3-py` real para ejecutar en Windows tras instalar dependencias. Los números H3 reales **solo deben comunicarse después de pasar esa prueba**.
