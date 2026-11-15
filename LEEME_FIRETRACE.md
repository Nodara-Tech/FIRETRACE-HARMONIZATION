# FIRETRACE HARMONIZATION — entrega basada en Nodara Tech v3.6

## Qué incluye

- La apariencia de las dos referencias entregadas por el equipo: `HOME.pdf` y `Harmonization.pdf`. Se respetan encabezado, emblema, panel lateral, colores, mapa satelital, tarjetas, gráfica y mapa de calor.
- **HOME:** mapa satelital a pantalla completa, filtros de fechas y ubicación.
- **HARMONIZATION:** mapa, cuatro indicadores, curvas de detecciones y calendario de calor por día.
- Los datos que se muestran son NASA FIRMS procesados por el motor v3.6; **no son los números decorativos de los PDF**.
- Se conservan íntegros `armonizar_firms_v2.py`, `emparejamiento_h3_v3_4.py`, `comparacion_espacial_v3_5.py`, `calidad_detecciones_v3_6.py`, `nodara_usa.py` y las auditorías P1–P5.
- El **observatorio técnico v3.6** permanece accesible desde el icono del menú (`☰` → **ADVANCED OBSERVATORY**) o en `http://127.0.0.1:8765/observatorio`.

## Ejecución en Windows

1. Extraer el ZIP completo y **abrir la carpeta que contiene `requirements.txt`** en VS Code.
2. Terminal:

```powershell
py --version
py -m pip install -r requirements.txt
py PRUEBAS_FIRETRACE.py
py aplicacion\pruebas_problema5.py
py aplicacion\visor_incendios.py
```

3. Abrir `http://127.0.0.1:8765`.
4. Con el menú superior derecho, cambiar entre **HOME** y **HARMONIZATION**.
5. En **Additional Filters** cambiar H3/cuadrícula, fuentes, día/noche, modo de mapa y fondo. Para las cinco auditorías detalladas abrir el observatorio avanzado.
6. Detener con `Ctrl+C` en la terminal.

## macOS (Apple Silicon o Intel)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python PRUEBAS_FIRETRACE.py
python aplicacion/visor_incendios.py
```

## ¿Por qué el ZIP no pesa 1,5 GB?

La única copia del respaldo enviada a un compañero por WhatsApp **no está dentro de este paquete**. Aquí hay **código íntegro v3.6** y **resultados reales de ejemplo de Costa Rica y Afganistán**. Si necesitas conservar los otros estados y los datos que ocupaban 1,5 GB, importa el respaldo desde el ZIP original:

```powershell
py IMPORTAR_DATOS_V3_6.py "C:\RUTA\NodaraTech_Observatorio_V3_H3 (2).zip"
```

El importador **únicamente copia archivos faltantes dentro de `datos/` y `resultados/`**, sin sustituir el motor, el código del visor ni modificar la versión original.

Una vez importado, reinicia el visor; las regiones nuevas aparecerán automáticamente en el selector **Select State** / **Processed dataset**.

## Significado estadístico correcto

- **Detections:** registros térmicos, no cantidad de incendios individuales.
- **Multi-source cells:** cantidad de celdas espaciales distintas que incluyen observaciones MODIS y VIIRS dentro del rango elegido.
- **Co-occurrence:** proporción de celdas-día compartidas entre todas las celdas-día activas, **no un porcentaje de confianza científica**.
- **Active cell-days:** número total de unidades espaciales y fechas con detección.
- Las curvas tienen una **media móvil retrospectiva de 7 días**, que suaviza el gráfico sin cambiar los totales.
- El mapa muestra una **muestra uniforme** de puntos cuando hay demasiados para visualizar; los contadores y gráficos usan todos los registros seleccionados.
- H3 y cuadrícula agrupan de forma distinta. La visualización de coincidencias diarias no implica equivalencia radiométrica o verificación de un mismo incendio.

## Sobre las fuentes / Internet

El servidor, los CSV y el cálculo de estadísticas funcionan localmente. Para los mapas se necesita conexión a Internet: Leaflet se carga desde `unpkg.com`; el fondo satelital usa Esri World Imagery y, opcionalmente, NASA GIBS y OpenStreetMap. Mantener la atribución en pantalla.

## Fuentes y créditos

- NASA FIRMS: https://firms.modaps.eosdis.nasa.gov/
- H3: https://h3geo.org/ y https://github.com/uber/h3-py
- Leaflet: https://leafletjs.com/
- NASA Worldview: https://worldview.earthdata.nasa.gov/ (referencia visual; no reutilización de su código)
- NASA GIBS: https://nasa-gibs.github.io/gibs-api-docs/
- OpenStreetMap: https://www.openstreetmap.org/copyright
- Esri World Imagery: servicios de mapas con atribución en la interfaz.

## Limitaciones de la entrega

No incluye un historial totalmente armonizado 2000–2026 ni una evaluación de exactitud frente a incendios verificados; ambas cosas quedan fuera del prototipo v3.6. Las nuevas pantallas trabajan con los **años y regiones realmente procesados** y nunca inventan detecciones.
