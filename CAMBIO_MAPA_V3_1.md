# Nodara Tech v3.1 — Mapa con geometrías visibles

Esta revisión mejora **únicamente la visualización** de la v3; conserva el motor, las comparaciones FRP y los registros originales.

## Qué cambió

- Al cambiar el selector «Método espacial», el visor pasa automáticamente a «Zonas» y dibuja **cuadrados** (cuadrícula v2) o **hexágonos H3 r7**.
- Hay un botón **Ver hexágonos H3 / Ver cuadrados v2** junto al título del mapa.
- El mapa indica cuál geometría está seleccionada.
- El modo «Detecciones» sigue mostrando los **mismos centros de píxel**, porque H3 no modifica las coordenadas originales.
- El modo «Cruces» sigue mostrando las **parejas candidatas v2**; el cambio a H3 no recalcula las coincidencias FRP.

## Instalación en proyecto que ya tiene datos

1. Cierra el visor con `Ctrl+C`.
2. Del ZIP `NodaraTech_PARCE_MAPA_V3_1.zip` copia el contenido de la carpeta `web` a `aplicacion/web` en tu proyecto v3, reemplazando los tres archivos indicados.
3. Vuelve a iniciar con `py aplicacion\visor_incendios.py` desde la carpeta que contiene `requirements.txt`.
4. Actualiza el navegador con `Ctrl+F5`.
5. Selecciona «Ver hexágonos H3» arriba del mapa; aparecen polígonos H3. Vuelve a pulsar el botón para ver los cuadrados.

**No elimines tus carpetas `datos/` y `resultados/` ni descargues de nuevo los ZIP de NASA.**

## Interpretación

Cambian la forma y el número de zonas agrupadas, no el número de registros originales. Un hexágono de H3 no es el contorno de un incendio. La equivalencia radiométrica MODIS–VIIRS sigue siendo experimental.
