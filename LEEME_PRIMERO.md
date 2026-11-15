# Nodara Tech v3.6 — Calidad MODIS–VIIRS y auditoría de sensibilidad

La **v3.6** mantiene la v3.5 y los problemas 1–4, y añade el análisis **bajo demanda** de seis filtros de confianza por separado en MODIS (0–100) y VIIRS (`l/n/h`). Los escenarios vuelven a calcular agrupaciones y parejas H3 y cuadrados; el mapa original queda intacto, para evitar mezclar resultados filtrados con los conteos de referencia.

**Instalación Windows:** lee `INSTRUCCIONES_PARCHE_V3_6.txt`.

**Pruebas:** `py aplicacion\pruebas_problema5.py` y `py aplicacion\pruebas_problema5_reales.py`.

**Explicación y límites:** `PROBLEMA_5_CALIDAD_DETECCIONES.md`. Los filtros no miden precisión ni equivalencia de sensores.

---

# Actualización v3.5 — Comparación controlada de área y bordes

Consulta `PROBLEMA_4_CONTROL_AREA_BORDES.md` e `INSTRUCCIONES_PARCHE_V3_5.txt`. Conserva los cambios P1, P2 y P3. Para ejecutar prueba real: `py aplicacion\pruebas_problema4_reales.py`. En el visor encontrarás un botón «Comparar área y efecto de bordes» bajo demanda.

---

# Nodara Tech v3.4 — Problema 3 (H3 temporal)

**NOVEDAD v3.4:** H3 ya no es solo agrupación diaria. Al seleccionar H3, la vista de «Zonas», «Cruces», el conteo de parejas y la tabla de ventanas 15/30/60/120 usan un **emparejamiento propio H3** con misma celda / vecindad k=1, tiempo, geometría de huella aproximada y asignación ávida 1:1. Al seleccionar cuadrados, se mantiene íntegra la v3.3. No afirma incendios confirmados.

**Instalación desde la versión anterior:** copiar el contenido del parche v3.4 en la carpeta raíz que contiene `requirements.txt`; ver `INSTRUCCIONES_PARCHE_V3_4.txt`.

**Prueba con H3 oficial en Windows:** `py -m pip install -r requirements.txt` y luego `py aplicacion\pruebas_problema3_reales.py`. Los conteos temporales H3 reales se obtienen después de esta ejecución; no se inventan cifras.

**Informe nuevo:** `PROBLEMA_3_H3_TEMPORAL_SOLUCIONADO.md`.

---

## Material de versiones anteriores (historial)

# Actualización v3.3 — Problema 2: sensibilidad temporal

Ahora puedes seleccionar ventanas de **15, 30, 60 o 120 minutos** en el visor para comparar **parejas candidatas** y **celdas-día compartidas con parejas cercanas**. El mapa de **Zonas → Cuadrícula v2**, la vista **Cruces** y el panel de concordancia se actualizan juntos. H3, las detecciones originales y los análisis FRP v2 no cambian.

**Actualiza tu proyecto v3.2** copiando únicamente el contenido de `NodaraTech_PARCHE_V3_3_PROBLEMA2.zip` sobre la raíz que contiene `requirements.txt`. Conserva las carpetas `datos`, `resultados` y `cache`.

**Prueba en Windows (PowerShell, desde la carpeta del proyecto):**

```powershell
py aplicacion\pruebas_problema1.py
py aplicacion\pruebas_problema2.py
py aplicacion\visor_incendios.py
```

Después abre `http://127.0.0.1:8765`, presiona `Ctrl + F5` y prueba Costa Rica 2024 → 31/03/2024 → Zonas → Cuadrícula v2 → Ventana temporal (15, 30, 60, 120). **Ninguna ventana está validada como óptima.** Más detalles en `PROBLEMA_2_SENSIBILIDAD_TEMPORAL.md`.

---

# Actualización v3.2 — Problema 1 de la auditoría corregido

Separa **ambos sensores en una misma celda-día** de **ambos con una pareja candidata de pasadas cercanas**. No cambia el motor científico v2, H3 ni FRP; la nueva comparación por pasada aplica a la cuadrícula cuadrada v2. Ver `PROBLEMA_1_SOLUCIONADO.md` para metodología y pruebas.

**Para iniciar desde la raíz de este proyecto:**

```powershell
py -m pip install -r requirements.txt
py aplicacion\pruebas_problema1.py
py aplicacion\visor_incendios.py
```

Visor: `http://127.0.0.1:8765`. Elige **Costa Rica 2024**, **31 de marzo**, **Zonas**, **Cuadrícula v2** y revisa el panel **¿Coinciden también en el tiempo?**: 38 celdas con pareja candidata cercana y 13 solo diarias. No son porcentajes de confianza.

---

# Nodara Tech Observatorio v3 — H3 + Cuadrícula

Proyecto organizado para Windows / Visual Studio Code. Incluye el motor v2, descarga automática NASA FIRMS y **nuevo motor espacial H3 v3**, con comparaciones en el visor. No necesitas colocar manualmente los ZIP de NASA para procesar un estado estadounidense.

## PASO 1 — Abrir la carpeta correcta

Descomprime `NodaraTech_OBSERVATORIO_V3_H3.zip`, entra en `NodaraTech_Observatorio_V3_H3_Cuadricula` y abre **esa carpeta interior** con `File > Open Folder` en VS Code. La terminal debe contener `requirements.txt`.

## PASO 2 — Instalar dependencias (solo primera vez)

En terminal PowerShell de VS Code:

```powershell
py -m pip install -r requirements.txt
```

Instala `pyshp` para límites estatales y **`h3` 4.x** para celdas hexagonales. Si el comando `py` no aparece, revisa la instalación de Python.

## PASO 3 — Comprobar H3 REAL (sin arrancar el visor)

```powershell
py aplicacion\pruebas_v3.py
```

O haz doble clic en `COMPROBAR.bat`. Debes ver `PASS` varias veces. Usa el ejemplo de referencia H3 real y verifica que los datos originales de Costa Rica de 2024 no hayan cambiado.

## PASO 4 — Abrir el visor

```powershell
py aplicacion\visor_incendios.py
```

Abre **http://127.0.0.1:8765**. La vista inicial `Costa Rica 2024` se alimenta de resultados v2 reales incluidos.

- Selecciona **Zonas**.
- En «Método espacial para Zonas y calendario», cambia de **Cuadrícula v2** a **H3 hexagonal (resolución 7)**.
- El visor generará el análisis H3 al seleccionarlo por primera vez. La comparación de los dos métodos aparece en el panel derecho.
- Puedes utilizar **Detecciones** y **Cruces** igual que antes. Los **Cruces** siguen calculados por el método de pasadas v2: no se reemplazaron por coincidencias H3 sin tiempo.
- Cambia la fecha. Los gráficos y KPI se actualizan al método espacial seleccionado.

## PASO 5 — Procesar Estados Unidos automáticamente

En el panel del visor «Procesar otro estado de EE. UU.» selecciona California y 2024, o ejecuta directamente:

```powershell
py aplicacion\nodara_usa.py ejecutar --estado California --anios 2024
```

El proceso descarga los ZIP de NASA que falten, obtiene límites oficiales, filtra detecciones por estado, ejecuta el motor v2 **y después genera el H3 r7**. Si los ZIP y resultados están presentes, los reutiliza. El procesamiento puede ser pesado para estados grandes.

Para importar datos de tu carpeta anterior usa `IMPORTAR_DATOS_ANTERIORES.bat`, no copies bases SQLite ni cachés manualmente.

## PASO 6 — Ejecución H3 fuera del visor

Si ya tienes una carpeta de resultados v2:

```powershell
py aplicacion\espacial_h3_v3.py --carpeta "resultados\resultados_armonizacion_v2\Costa_Rica\2024" --resolucion 7
```

Obtendrás `espacial_h3_v3\h3_r7` dentro de ese resultado, con calendario diario, mensual, comparación de métodos y vecindad. Los CSV originales nunca se alteran.

## Organización

```
NodaraTech_Observatorio_V3_H3_Cuadricula/
  INICIAR_VISOR.bat
  COMPROBAR.bat
  INSTALAR_DEPENDENCIAS.bat
  requirements.txt
  aplicacion/
    visor_incendios.py
    nodara_usa.py
    armonizar_firms_v2.py
    espacial_h3_v3.py       <-- NUEVO
    pruebas_v3.py           <-- NUEVO
    web/
      index.html
      styles.css
      app.js
  datos/
  resultados/
    resultados_armonizacion_v2/
      Costa_Rica/2024/
      Afghanistan/2024/
  cache/
  documentacion/
    METODOLOGIA_H3_V3.md
```

## Límites científicos

- H3 y cuadrados son **sistemas de agrupación**; no corrigen los sesgos de sensibilidad, cobertura nubosa o horarios de MODIS y VIIRS.
- H3 r7 tiene área media ~5,16 km²; la cuadrícula cuadrada depende de la configuración original (2 km → área nominal ~4 km²; 5 km → ~25 km²).
- Una celda-día cuenta **presencia de detección**, no superficie quemada ni número de incendios.
- La vecindad H3 diaria es una pista para estudiar bordes, **no un emparejamiento temporal confirmado**.
- Todavía falta validar la serie histórica 2000–2025 con varios años y máscaras de cobertura.

**Evidencia de pruebas:** la v2 original y el flujo de programación e interfaz v3 se verificaron localmente. En este entorno no se pudo instalar `h3-py`; por tanto, **no se atribuyen cifras H3 finales a la v3 hasta ejecutar `COMPROBAR.bat` con el paquete real en tu equipo**.
