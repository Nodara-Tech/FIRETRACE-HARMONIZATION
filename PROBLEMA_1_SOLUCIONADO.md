# Nodara Tech v3.2 — corrección del problema 1

## Objetivo y alcance

Separamos **presencia en la misma celda-día** de **existencia de al menos una pareja candidata de pasadas cercanas**. No cambiamos los parámetros ni el emparejamiento del motor v2, H3, el descargador automático, las estadísticas de FRP ni las fuentes originales. Los problemas 2, 3, 4 y 5 de la auditoría siguen pendientes.

## Metodología implementada

A partir de `armonizacion_celdas_dia_v2.csv` identificamos cuatro categorías mutuamente excluyentes:

1. `ambos_paso_cercano`: ambos sensores registraron actividad en la **misma celda y fecha UTC**, y al menos una pareja del archivo `coincidencias_pasadas_frp.csv` satisface los filtros de distancia, día/noche y ventana temporal del motor (30 minutos en nuestros datos de ejemplo).
2. `ambos_solo_dia`: ambos sensores registraron actividad en la misma celda-día, **pero no hay una pareja candidata** que cumpla las reglas anteriores.
3. `solo_modis`: solamente detecciones MODIS en esa celda-día.
4. `solo_viirs`: solamente detecciones VIIRS en esa celda-día.

No se crea una categoría de «incendio confirmado». Un mismo día no significa misma pasada; una pareja candidata tampoco asegura que se trate del mismo incendio.

**Restricción explícita de H3**: los 4 niveles pertenecen a las **celdas cuadradas v2**. H3 sigue haciendo clasificación diaria por hexágono; no transferimos los conteos de pasadas de cuadrados a hexágonos, porque introduciría un error de denominador y geometría. La integración temporal H3 está pendiente (problema 3).

## Resultados de validación (datos originales NASA FIRMS, 2024)

| Métrica | Costa Rica | Afganistán |
|---|---:|---:|
| Celdas-día totales (cuadrícula v2, 2 km) | 6023 | 740 |
| Ambos sensores en la misma celda-día | 527 | 34 |
| Ambos con al menos una pareja candidata cercana | **313** | **17** |
| Ambos solo en el mismo día | **214** | **17** |
| Solo MODIS | 413 | 46 |
| Solo VIIRS | 5083 | 660 |

**Costa Rica, 31 de marzo de 2024:** 184 celdas-día activas; 51 compartidas, de las cuales **38** con pareja cercana y **13** solo diaria; 9 solo MODIS y 124 solo VIIRS. Los **65** pares originales del motor siguen siendo relaciones candidatas, no incendios únicos.

## Archivos nuevos

El programa genera automáticamente, por cada conjunto procesado, la subcarpeta `concordancia_v3_2/` con:

- `concordancia_celdas_dia.csv` — nivel y número de parejas cercanas por celda-día.
- `concordancia_diaria.csv` — conteos por fecha UTC.
- `concordancia_mensual.csv` — conteos mensuales de celdas-día.
- `diagnostico_concordancia.json` — parámetros, conteos y advertencias.

Se generan **a partir de los resultados ya existentes**, sin volver a descargar los ZIP ni recalcular FRP.

## Cambio en el visor

- En el panel «¿Coinciden también en el tiempo?» aparecen los dos niveles de coincidencia para la cuadrícula v2.
- En «Zonas» y modo de **cuadrados**, los polígonos con pareja próxima se distinguen de los que coinciden solo por fecha, estos últimos con trazo discontinuo.
- Al activar **H3**, se mantiene la visualización original y una advertencia indica que esos conteos temporales proceden únicamente del método cuadrado.
- El indicador superior «MODIS y VIIRS» continúa incluyendo TODAS las coincidencias diarias; no se renombra como «incendios confirmados».

## Pruebas

Desde la carpeta del proyecto (la que contiene `requirements.txt`):

```powershell
py aplicacion\pruebas_problema1.py
py aplicacion\visor_incendios.py
```

En el navegador: `http://127.0.0.1:8765` → Costa Rica 2024 → 31/03/2024 → Zonas → Cuadrícula v2. Deberías ver 38 compartidas con pareja cercana y 13 compartidas solo por fecha en el panel estadístico.

Para otro año o estado procesado, la clasificación se calcula al abrir el conjunto. **No reenvíes archivos manualmente ni vuelvas a descargar los ZIP.**

## Qué no modifica esta corrección

No valida que los pares sean un mismo incendio, no estima precisión ni porcentaje de confianza, no mejora la ventana de 30 minutos, no corrige cobertura/nubes y no calibra FRP. Estos pasos siguen pendientes para la armonización histórica.
