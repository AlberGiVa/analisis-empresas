# 0012. Registro de ejecuciones y trazabilidad

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
Cada ejecución debe quedar registrada (fecha, datos usados y versión de la configuración), y los
resultados históricos no se sobrescriben.

## Decisión
- **Tabla `runs`.** Cada ejecución inserta una fila con:
  - identificador ordenable (`RAAAAMMDDTHHMMSS-xxxxxx`);
  - fechas de inicio y fin;
  - fecha de análisis;
  - corte de datos (el inicio de la ejecución) y lista de lotes de carga visibles;
  - versión, huella SHA-256 y copia íntegra de la configuración;
  - versión del código y commit de git (con `-dirty` si había cambios sin confirmar);
  - usuario y estado.
- **Ejecuciones fallidas.** También se registran, con su error y sin resultados.
- **Resultados por ejecución.** Métricas (con sus entradas), puntuaciones y su desglose, filtros
  y alertas se guardan con el identificador de la ejecución, en una sola transacción. Nunca se
  actualizan; repetir una ejecución crea otra.
- **Reproducibilidad.** Los datos de entrada son de solo inserción. Con la misma fecha de análisis,
  el mismo corte y la misma configuración se obtiene el mismo resultado; un test de integración lo
  comprueba.
- **Fecha de análisis por defecto:** la última con cotizaciones cargadas.

## Consecuencias
- La base crece con cada ejecución. A esta escala es despreciable; se podrían archivar
  ejecuciones antiguas más adelante.
- Un comando para "reproducir la ejecución X" sería sencillo con este diseño: está en siguientes
  pasos.
