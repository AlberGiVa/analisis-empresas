# 0017. Estudio con datos reales de fuentes públicas, aislado

- Fecha: 2026-10-20
- Estado: aceptada (petición del usuario: "una simulación con datos y análisis reales a día de
  hoy, en un lugar aislado, lo más real y senior posible")

## Contexto
La herramienta solo se había probado con datos sintéticos. Sin licencia de Bloomberg o FactSet, la
única forma de probarla con datos reales era usar fuentes públicas gratuitas. Esos datos no pueden
mezclarse con la base principal ni subirse al repositorio, y su calidad es desigual.

## Decisión
- **Espacio aislado** en `estudio-real/`: universo, metodología, descargas, base de datos y salidas
  propias. Las rutas las fija el código del estudio (`company_analysis.study`), no el entorno, así
  que un comando del estudio no puede escribir en la base principal. El proveedor de datos
  públicos no se ofrece en la CLI principal por el mismo motivo. `datos/` y `salida/` están en
  `.gitignore`.
- **Fuentes:**
  - SEC EDGAR, para los estados financieros, con la fecha de presentación de cada informe;
  - Nasdaq, para las cotizaciones, contrastadas con Yahoo Finance;
  - BCE, para los tipos de cambio.
- **Descarga y lectura separadas.** Cada descarga crea una carpeta con fecha que nunca se modifica,
  con un manifiesto de URL, hora y SHA-256 de cada fichero. La lectura es determinista y los tests
  la prueban con respuestas sintéticas, sin red.
- **Lectura de la SEC:**
  - **Clasificación de periodos.** Los periodos se clasifican por sus fechas, no por la etiqueta
    del informe; solo se usan los acumulados desde el inicio del ejercicio.
  - **Ejercicios válidos.** Solo cuentan los que cierran en el mes de cierre fiscal de la empresa.
  - **Publicaciones.** Las comparativas repetidas no son publicaciones nuevas; una cifra que
    cambia en un informe posterior se guarda como corrección, con su fecha.
  - **Una etiqueta por partida y empresa** para todos los periodos: la que llega al periodo más
    reciente.
  - **EBITDA** = resultado operativo publicado + amortizaciones.
  - **Deuda:** las líneas del balance de cada empresa, revisadas a mano en el universo. Una línea
    que no aparece en un balance cuenta como cero, y se avisa.
- **Revisión de calidad** que se ve en el informe:
  - informe presentado pero aún no en los datos estructurados;
  - partidas sin dato o con una etiqueta alternativa;
  - líneas de deuda no presentadas;
  - diferencias de cotización con la segunda fuente;
  - mercado de cotización;
  - trimestres con un resultado operativo atípico (probable partida no recurrente) dentro de los
    doce meses analizados.
- **Metodología del estudio** = la del fondo, salvo la puntuación de crédito, que solo usa
  fundamentales. No hay fuente gratuita y fiable de diferenciales de bonos ni de ratings.
- **Corrección en el núcleo** detectada con los datos reales: el ejercicio anterior a un periodo
  intermedio se busca con un margen de un mes, para que funcionen los calendarios con trimestres de
  12 y 16 semanas.

## Consecuencias
- La vista de acreedor del estudio es más pobre que la del fondo, y así se indica.
- Las cifras son las publicadas, sin ajustes: los deterioros y las plusvalías distorsionan el EBITDA
  de los doce meses. Se señalan; no se corrigen.
- Las cotizaciones vienen de servicios sin licencia de datos: válidas para esta prueba interna, no
  para un uso habitual.
- Añadir empresas al estudio exige revisar sus etiquetas de deuda; el resto es automático.
