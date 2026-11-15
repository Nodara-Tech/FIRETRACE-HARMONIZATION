# Adaptación visual FIRETRACE (manteniendo motor Nodara Tech v3.6)

Se preservan sin cambios los cinco módulos de auditoría y emparejamiento de la v3.6. La capa nueva añade:

- `aplicacion/web/firetrace.html`, `firetrace.css`, `firetrace.js`, `firetrace-logo.png` — las vistas HOME y HARMONIZATION del diseño proporcionado por el equipo.
- `aplicacion/firetrace_api.py` — consulta por fecha inicial y final, filtro satélites, día/noche, vegetación, coordenadas y modo espacial H3/cuadrícula. Agregación con indicadores reales y muestreo de puntos únicamente en el mapa.
- Nueva ruta `/` para FIRETRACE; el observatorio original sigue en `/observatorio`.
- `PRUEBAS_FIRETRACE.py` y `IMPORTAR_DATOS_V3_6.py`.
- Menú con descarga CSV del período y enlace a los cinco análisis estadísticos completos.

**No se han copiado los números del mockup** (219.480, 5.947, 27,1 %) a la aplicación. Los indicadores se calculan a partir de los registros cargados.

El mapa satelital necesita Internet y las capas externas con atribución. Las referencias visuales originales se incluyen en `referencias_diseno/`.

No están incluidos los 1,5 GB de archivos no adjuntados a este chat, pero el importador puede traerlos directamente desde el respaldo v3.6 original sin cambiar código ni resultados existentes.
