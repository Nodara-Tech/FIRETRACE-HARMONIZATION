# Nodara Tech v3.5 — Problema 4: área, geometría y efectos de borde

## Diagnóstico

En v3.4 se comparaban **370 parejas de la cuadrícula v2, restringidas a la misma celda**, con **452 parejas de H3 r7, con la misma celda O seis vecinas inmediatas** (ejecución en Windows del equipo, H3 4.5.0). Esos valores no demuestran que H3 encuentre más incendios reales, ni que H3 sea más exacto. Cambiaban a la vez la forma, el área, la vecindad y el protocolo de agregación.

## Cambio realizado

`aplicacion/comparacion_espacial_v3_5.py` genera **33 escenarios** para cada región y ventana temporal elegida:

1. H3 r7, con área media global de aproximadamente **5,16129336 km²** (un único mosaico global de índices H3).
2. Cuadrícula de **2,000000 km de lado**, área nominal 4 km², con **16 desplazamientos** del origen (0, 0,25, 0,5 y 0,75 de celda por eje).
3. Cuadrícula de **2,271848 km de lado** aproximadamente, área nominal igual al área media global de H3 r7, también con **16 desplazamientos**.

**Importante:** los desplazamientos afectan *solamente* la ubicación de los límites de la cuadrícula, no las coordenadas de NASA. La proyección utilizada para cuadrados es exactamente la proyección de igual área de v2 (`projection`), de modo que la superficie nominal es comparable. El área **individual** de los hexágonos H3 no es exactamente igual al promedio mundial.

Se utilizan las funciones de v3.4 `build_passes_h3`, `candidate_pairs_h3` y `assign_pairs` para **todos** los escenarios, con idénticos criterios de agrupación temporal (12 min), ventana de coincidencia seleccionada (15/30/60/120 min), compatibilidad día/noche, umbral aproximado de huellas y emparejamiento ávido uno a uno **por par de plataformas**. La comparación se separa en:

- **Parejas internas:** ambas pasadas de MODIS y VIIRS terminan en la MISMA celda del escenario.
- **Parejas con vecinos:** también se permite su búsqueda en celdas contiguas; H3 k=1 tiene 6 vecinos y la cuadrícula k=1 tiene 8.

Para cada escenario se informan celdas-día activas, celdas-día con ambos sensores, pares internos, pares con vecinos, pares entre vecinos, pasadas agregadas y celdas compartidas con pareja. Los archivos CSV quedan en `resultados/.../comparacion_espacial_v3_5/t_30min/` o en la ventana elegida. Se calculan al pulsar **Comparar área y efecto de bordes** en el panel derecho del visor.

## Comprobación numérica independiente del módulo cuadrado (Costa Rica 2024)

Los siguientes valores se reejecutaron localmente con **13.836** detecciones `type=0` y la misma lógica de emparejamiento de P3. **Los números H3 reales deben ratificarse ejecutando `pruebas_problema4_reales.py` con h3-py oficial en el equipo.**

| Modelo cuadrado | Área nominal (km²) | Parejas internas, 16 desplazamientos | Parejas con vecinos, 16 desplazamientos | Celdas-día compartidas, 16 desplazamientos |
|---|---:|---:|---:|---:|
| Cuadrados de 2 km | 4,00 | 367–378 (media 372,0) | 446–466 (media 456,2) | 505–540 |
| Cuadrados de área H3 r7 | 5,1613 | 359–383 (media 370,3) | **431–467 (media 444,8)** | 507–531 |

En el desplazamiento (0,0), cuadrados de 2 km reproducen exactamente **370 parejas internas** de v2 y encuentran **454 parejas al permitir vecinos**, usando el motor P3. Los **452 pares H3** del usuario (Windows, v3.4) caen dentro del rango **431–467** de los cuadrados comparables en área y con vecinos.

**Esto no prueba que H3 y los cuadrados sean equivalentes**, pero demuestra que la comparación anterior 370 frente a 452 no aislaba el efecto de usar hexágonos: al permitir vecindad en ambos métodos, la diferencia se reduce considerablemente.

## Afganistán 2024: segunda región, 1.169 registros type=0

| Modelo cuadrado | Parejas internas (rango) | Parejas con vecinos (rango) | Celdas-día compartidas (rango) |
|---|---:|---:|---:|
| Cuadrados de 2 km | 12–22 | 18–21 | 25–38 |
| Cuadrados de área H3 | 14–20 | 18–21 | 27–36 |

La v2 estricta se reproduce con 18 pares en la cuadrícula de 2 km y origen cero.

## Limitaciones que no desaparecen

1. **La topología no es idéntica:** H3 tiene seis vecinos y un cuadrado ocho. La distancia de huellas limita candidatos, pero no garantiza acceso idéntico a todos los vecinos posibles.
2. **Los grupos de píxeles por pasada dependen de la partición.** Esto puede alterar el número y la posición de centroides agregados, incluso con igual área promedio. La comparación controla la misma regla de agrupación, no hace idénticos los grupos.
3. **H3 tiene una única partición global fija.** Los cuadrados permiten desplazar el origen; no es legítimo desplazar artificialmente coordenadas reales para “desplazar H3”.
4. **Los rangos mínimo–máximo NO son intervalos de confianza estadísticos**, y las parejas candidatas no son incendios únicos ni emparejamientos confirmados en tierra.
5. El algoritmo de asignación es **greedy**, no asignación óptima global. FRP, cobertura nubosa, oportunidad de observación y sesgos propios de cada sensor siguen sin calibrarse.
6. Falta **validación externa** para establecer verdaderos positivos, falsos positivos y exactitud.

**Conclusión técnica:** el problema 4 queda abordado mediante un experimento espacial controlado, reproducible y visible en el visor, pero no es posible declarar que H3 supera o iguala científicamente a la cuadrícula. El problema 5 (confianza de las detecciones) sigue pendiente.

## Cómo ejecutarlo

```powershell
py -m pip install -r requirements.txt
py aplicacion\pruebas_problema4.py
py aplicacion\pruebas_problema4_reales.py
py aplicacion\visor_incendios.py
```

Abre `http://127.0.0.1:8765`, selecciona una región, la ventana temporal (30 min por defecto), baja hasta **Auditoría espacial controlada · v3.5** y pulsa **Comparar área y efecto de bordes**.

También puedes correrlo sin servidor:

```powershell
py aplicacion\comparacion_espacial_v3_5.py --carpeta resultados\resultados_armonizacion_v2\Costa_Rica\2024 --ventana 30
```

Fuentes: [documentación oficial H3 — áreas](https://h3geo.org/docs/core-library/restable/) y [API de h3-py](https://uber.github.io/h3-py/api_verbose.html), más las rutinas originales v2 y v3.4 de Nodara Tech.
