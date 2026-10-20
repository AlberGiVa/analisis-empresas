# 0011. Filtros y alertas

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
El encargo pide filtros configurables y tres reglas sencillas de alerta: rebaja de rating, deuda
neta/EBITDA por encima de un umbral y cambio grande de puntuación entre ejecuciones. La herramienta
no recomienda: filtros y alertas solo señalan.

## Decisión
- **Filtros con nombre en el YAML.** Combinan sectores, países y condiciones sobre cualquier
  métrica (`<`, `<=`, `>`, `>=`). El resultado tiene tres valores:
  - "cumple";
  - "no cumple", si alguna condición falla;
  - "indeterminado", si ninguna falla pero falta algún dato.

  Se guarda el detalle de cada condición, con el valor de la empresa o el motivo de la falta.
- **Rebaja de rating.**
  - Compara el rating vigente en la fecha de análisis con el de 182 días antes (configurable),
    usando el peor rating si hay varias agencias.
  - Solo depende de los datos, no de ejecuciones anteriores, así que se puede reproducir.
  - Si el bono pasa de grado de inversión a high yield, el mensaje lo indica.
- **Apalancamiento.** Salta con deuda neta/EBITDA por encima de 3,5x, y también con EBITDA cero o
  negativo y deuda neta positiva: el ratio "no significativo" no debe esconder el caso más grave.
- **Cambio de puntuación.** Compara con la ejecución anterior, que es la última completada con
  fecha de análisis anterior. Salta si la diferencia es de 15 puntos o más, nombra los dos
  factores que más contribuyen y avisa si la configuración cambió entre ambas ejecuciones.
- Las alertas se guardan con un mensaje en español y un detalle estructurado (JSON).

## Consecuencias
- La primera ejecución no tiene alertas de cambio de puntuación.
- La atribución del cambio a cada factor es aproximada: si un factor gana o pierde dato, cambian
  también los pesos del resto.
