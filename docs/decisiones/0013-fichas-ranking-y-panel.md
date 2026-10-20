# 0013. Fichas, ranking y panel

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
Los usuarios no programan y trabajan con Excel. Necesitan una ficha estandarizada por empresa, con
la vista de acción y la de crédito lado a lado, un ranking y un panel con filtros.

## Decisión
- **Fichas y panel muestran lo que guardó la ejecución.** Métricas, puntuaciones, filtros y
  alertas no se recalculan. El contexto descriptivo (cotización, bonos, histórico) se reconstruye
  con la fecha de análisis, el corte de datos y la configuración de esa misma ejecución. Como los
  datos son de solo inserción, es exactamente lo que vio la ejecución.
- **Vistas comunes** (`reports/views.py`). Textos en español y valores formateados; las usan tanto
  las fichas HTML como el panel, así que siempre dicen lo mismo.
- **Fichas HTML autocontenidas.**
  - Jinja2, sin JavaScript ni recursos externos; se pueden enviar por correo e imprimir.
  - Escape automático: lo que escribe un analista nunca se interpreta como HTML.
  - Incluyen:
    - el desglose de cada factor y el motivo de cada dato ausente;
    - las fórmulas y los datos de entrada (desplegables);
    - el pie de trazabilidad: ejecución, configuración y código;
    - el aviso de que no son recomendaciones.
- **Ranking.**
  - Uno para cada puntuación: las empresas con puntuación primero; las demás al final, con su
    motivo.
  - Además un `ranking.csv` con separador `;`, coma decimal y UTF-8 con BOM, que se abre
    directamente en Excel en español.
- **Panel Streamlit de solo lectura.**
  - Conexiones cortas de solo lectura, para no bloquear la CLI.
  - Caché que se invalida cuando cambia la base.
  - Solo accesible desde el propio equipo (`server.address = "localhost"`): no escucha en la red
    ni consulta servicios externos para averiguar la IP pública, como hace Streamlit por defecto.
  - Sin envío de estadísticas de uso (`.streamlit/config.toml`).
  - `analisis panel` lo arranca y abre el navegador cuando el servidor está listo.

## Consecuencias
- Las notas del diario se añaden desde la CLI; hacerlo desde el panel está en siguientes pasos.
- Si en el futuro se renombra una métrica, las ejecuciones antiguas con el nombre anterior no se
  podrán mostrar sin una correspondencia de nombres.
