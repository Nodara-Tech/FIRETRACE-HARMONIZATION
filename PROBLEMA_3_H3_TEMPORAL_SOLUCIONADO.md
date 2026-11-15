# Nodara Tech v3.4 — Problema 3: H3 en el emparejamiento temporal

## Qué problema se corrigió

Hasta v3.3, H3 solo servía para agrupar observaciones en hexágonos por día. La vista «Cruces» y las 4 ventanas temporales seguían leyendo las parejas calculadas por la cuadrícula v2 incluso cuando la interfaz mostraba H3. **Esa mezcla ya se eliminó**. Con H3 seleccionado, se genera y consulta un archivo de parejas específico de H3; con cuadrados, sigue intacto el sistema v3.3.

## Método implementado (no es una calibración científica)

1. Filtrar `type=0` y aplicar la misma política de calidad que tiene el escenario v2 original.
2. Asignar cada centro de píxel a su hexágono con `h3.latlng_to_cell(lat, lon, 7)`.
3. Agrupar detecciones por **hexágono, plataforma, día/noche y fecha UTC** en pasadas de máximo 12 minutos desde la primera detección de cada grupo.
4. Buscar candidatos de una pasada MODIS y otra VIIRS en **la misma celda H3** o cualquiera de sus **seis vecinas inmediatas** (`h3.grid_disk(k=1)`). Esto solo abre un conjunto de candidatos; no supone por sí mismo que los registros sean el mismo incendio.
5. Exigir simultáneamente **mismo día UTC**, **misma categoría diurna/nocturna**, **separación temporal ≤ 15/30/60/120 minutos**, y **distancia entre centros agregados ≤ media diagonal de `scan`/`track` de cada pasada + 0,25 km**. Las huellas son aproximaciones, no polígonos instrumentales exactos.
6. Elegir parejas mediante una asignación **ávida 1:1 por día y par concreto de plataformas** (ordenada primero por diferencia temporal y luego distancia). Una misma pasada no se reutiliza al emparejar Terra–S-NPP en distintas celdas H3 vecinas; puede sí participar en otro par de plataformas, como Aqua–S-NPP. Esta asignación **no es** una optimización global de máxima cardinalidad.
7. Clasificar por separado los hexágonos compartidos con pareja dentro de la celda, compartidos con pareja en una vecina y compartidos **solo por día**. Un hexágono solo-MODIS con pareja en otro solo-VIIRS **sigue siendo solo-MODIS**: la vecindad NO infla el número de celdas compartidas.

## Archivo nuevo y productos

- `aplicacion/emparejamiento_h3_v3_4.py`: motor temporal real de H3.
- `aplicacion/pruebas_problema3.py`: pruebas unitarias y HTTP con **índices H3 sintéticos** exclusivamente en directorios temporales; comprueban las reglas y que los endpoints están conectados.
- `aplicacion/pruebas_problema3_reales.py`: ejecución y pruebas de integridad con **h3-py 4.x auténtico** y CSV reales en la instalación del usuario.
- `resultados/.../espacial_h3_v3/h3_r7/`: agrupación H3 v3 preexistente, intacta.
- `resultados/.../emparejamiento_h3_v3_4/h3_r7/`: cuatro nuevos CSV `h3_parejas_ventanas.csv`, `h3_concordancia_celdas.csv`, `h3_concordancia_diaria.csv`, `h3_resumen_ventanas.csv`, más manifiesto de trazabilidad.

Los resultados P1, P2, FRP v2, la cuadrícula, el descargador NASA y los archivos de detecciones originales no cambian.

## Qué cambia en la interfaz

- **Zonas + H3:** los hexágonos compartidos se distinguen según pareja en la misma celda / hexágono vecino / solo coincidencia diaria. Las celdas individuales con pareja vecina se mantienen individuales y se resaltan.
- **Cruces + H3:** se muestran las parejas H3 propias, ubicadas en el punto medio de los centroides de las dos pasadas, no el centro de cuadrícula v2. El recuadro indica si fueron de la misma celda o celdas vecinas.
- **Ventana 15/30/60/120:** afecta al método espacial seleccionado; no solo al método cuadrado.
- **Tablas de sensibilidad y concordancia:** son específicas del método seleccionado. Los conteos H3 y cuadrados no son métricas de sensibilidad/especificidad y no pueden compararse como exactitud debido a superficies y reglas distintas.

## Verificaciones hechas en el entorno de desarrollo

1. P1 y P2 originales con datos reales Costa Rica y Afganistán: **PASS**.
2. Endpoints reales de cuadrícula del 31/03/2024, Costa Rica: 184 celdas, 51 compartidas, 38 parejas cercanas por celda y 13 solo por día; **PASS**, sin regresión.
3. Emparejador H3 con datos **sintéticos controlados**: misma celda, vecino, tiempo, distancia, deduplicación 1:1, preservación de la clasificación diaria y endpoints HTTP H3; **PASS**.
4. `python -m compileall` y `node --check`: **PASS**.
5. **PENDIENTE**: ejecución con la biblioteca oficial H3 4.x dentro de este entorno (no se pudo instalar); no se publican conteos H3 temporales reales hasta ejecutar el test nativo en Windows. Nunca se reemplazan resultados reales con datos sintéticos.

## Cómo verificar en Windows

Desde la carpeta donde está `requirements.txt`, cerrar el visor antiguo e instalar dependencias:

```powershell
py -m pip install -r requirements.txt
py aplicacion\pruebas_problema3.py
py aplicacion\pruebas_problema3_reales.py
py aplicacion\visor_incendios.py
```

El segundo script imprime para Costa Rica y Afganistán, por cada ventana, número de parejas H3 **misma celda** y **vecinas**, total de hexágonos compartidos y cuántos tienen pareja, y verifica temporalidad, proximidad y unicidad. Los datos FIRMS deben estar en `resultados/resultados_armonizacion_v2/...` como en el ejemplo incluido o la carpeta del usuario.

Para comprobar en la web: **Costa Rica 2024 → 31 de marzo → H3 hexagonal → Zonas**, ver categorías y **Cruces**; cambiar 15 a 30 y después a 60 minutos y verificar cambios en tabla y pares. Al volver a **Cuadrícula v2**, deben mantenerse los conteos previos.

## Limitaciones pendientes

- Una proximidad espacio-temporal no demuestra que dos satélites midieran el mismo incendio.
- La geometría de la pasada usa centros de píxeles, no el polígono de la huella georreferenciado realmente.
- H3 res. 7 tiene superficie nominal diferente de 2x2 km; el problema 4 deberá comparar escalas de área más similares.
- No hay ajuste de oportunidad de observación, nubosidad, falsas alarmas, ni cuantificación de incertidumbre real. Ese trabajo sigue pendiente.
- Se usa el mismo día **UTC** para definir celda-día; no se enlazan observaciones a ambos lados de medianoche, incluso si están próximas.

Referencia API oficial: https://uber.github.io/h3-py/api_quick.html
