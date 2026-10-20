Vas a crear desde cero, en esta carpeta vacía, la base de un proyecto: una herramienta interna para un fondo multiactivos que sistematiza el análisis de empresas. Quiero una base sólida, sencilla y bien probada sobre la que seguir construyendo, no un producto terminado.

## Contexto (ajusta lo que está entre corchetes)
- El fondo invierte en acciones y en bonos corporativos, así que cada empresa se analiza desde dos ángulos: como accionista (valoración, rentabilidad, crecimiento) y como acreedor (endeudamiento, capacidad de pago, diferencial de sus bonos).
- Usuarios: [gestores y analistas que no programan], que hoy trabajan con [hojas de Excel].
- Universo inicial: [empresas cotizadas europeas y estadounidenses de mediana y gran capitalización].
- Moneda base: [EUR].
- Proveedores de datos: [ninguno conectado todavía; más adelante, Bloomberg o FactSet].

## Principios
- La herramienta apoya al gestor, no decide por él: produce métricas, puntuaciones y alertas transparentes, nunca recomendaciones de compra o venta.
- Toda puntuación se puede descomponer en sus componentes y toda métrica tiene su fórmula documentada.
- Un dato que falta o no aplica nunca se inventa ni se rellena en silencio: se marca con su motivo (sin dato, no aplica, división por cero…).
- Trazabilidad: cada ejecución queda registrada (fecha, datos usados, versión de la configuración) y los datos históricos no se sobrescriben.
- Los datos reales de mercado nunca se suben al repositorio (sus licencias suelen prohibirlo); solo los datos sintéticos de ejemplo.
- Sencillez: sin microservicios, Docker, autenticación ni despliegue en esta fase.

## Stack
Python 3.12 gestionado con uv (pyproject.toml), pandas, DuckDB como almacenamiento local, pydantic y pydantic-settings para modelos y configuración, Typer para la línea de comandos, Jinja2 para informes, Streamlit para un panel mínimo, pytest, ruff (lint y formato) y mypy. Claves y secretos en .env, con .env.example y .gitignore desde el primer commit. Si propones cambiar alguna pieza, justifícalo en el plan.

## Arquitectura (punto de partida; propón mejoras si las ves)
Un paquete en src/ con estos módulos:
- providers: interfaz común de proveedor de datos y un SampleProvider que lee los datos de ejemplo. Los proveedores reales se añadirán después implementando la misma interfaz.
- models: modelos de dominio. Empresa/emisor (nombre, LEI, sector, país, divisa de reporte), estados financieros por periodo, datos de mercado e instrumentos: acciones y bonos (ISIN, cupón, vencimiento, prelación, rating, rentabilidad, diferencial).
- storage: esquema DuckDB y acceso a datos. Cada dato guarda fecha de cierre del periodo, fecha de publicación y fecha de carga, para poder reconstruir qué se sabía en cada momento y evitar el sesgo de anticipación (look-ahead).
- normalization: últimos doce meses (LTM), conversión a la moneda base de las magnitudes absolutas y alineación de ejercicios fiscales distintos.
- metrics: un registro central de métricas, cada una con id, nombre, descripción, fórmula, unidad, si más alto es mejor o peor y a qué sectores aplica.
  - Renta variable: PER, EV/EBITDA, FCF yield, ROE, ROIC, margen EBITDA, crecimiento de ventas.
  - Crédito: deuda neta/EBITDA, cobertura de intereses (EBITDA/gastos financieros), deuda/capital y diferencial de cada bono frente a la mediana de su tramo de rating.
  - En bancos y aseguradoras, las métricas basadas en EBITDA, deuda neta o EV se marcan como "no aplica".
- scoring: una puntuación de renta variable y otra de crédito, por separado, a partir de percentiles dentro de cada sector (con el universo completo como referencia si el sector tiene pocas empresas). Factores y pesos en un YAML de configuración. Cada puntuación lleva un indicador de cobertura (qué parte de los factores tenía dato) y por debajo de un umbral mínimo no se muestra.
- screening y alertas: filtros configurables y reglas sencillas (rebaja de rating, deuda neta/EBITDA por encima de un umbral, cambio grande de puntuación entre ejecuciones).
- reports: una ficha estandarizada por empresa en HTML, con la vista de acción y la de crédito lado a lado.
- journal: registro de tesis de inversión y notas del analista (empresa, fecha, autor, texto, decisión).
- cli y app: comandos para cargar datos, ejecutar el pipeline, generar fichas y añadir notas; un panel Streamlit con el ranking, filtros y el detalle de cada empresa.

## Datos de ejemplo
Genera datos sintéticos realistas de unas 20 empresas ficticias repartidas en 4–5 sectores (uno de ellos financiero), con 3 ejercicios anuales, cotizaciones, tipos de cambio y entre 1 y 3 bonos por empresa. Guárdalos como archivos en el repositorio, creados con un script reproducible. Incluye a propósito casos límite: EBITDA negativo, una empresa sin deuda, datos que faltan, una empresa que reporta en otra divisa y una rebaja de rating entre periodos.

## Calidad
- Cada métrica tiene tests con valores calculados a mano, incluidos sus casos límite.
- Un test de integración ejecuta el pipeline completo con los datos de ejemplo.
- Ningún test accede a internet.
- Todo el código va tipado; ruff, mypy y pytest pasan antes de cada commit.
- Código, nombres y comentarios en inglés; documentación y textos de la interfaz en español.

## Documentación
- CLAUDE.md breve: propósito, principios, mapa de la arquitectura, comandos (instalar, tests, lint, ejecutar), convenciones, un glosario financiero mínimo y los pasos para añadir una métrica o un proveedor nuevos.
- README.md: qué es y cómo ponerlo en marcha en pocos comandos.
- docs/metricas.md: diccionario de métricas (definición, fórmula, interpretación, casos límite).
- docs/decisiones/: una nota corta por cada decisión de diseño relevante.
- Guarda este encargo tal cual en docs/encargo-inicial.md.

## Forma de trabajar
1. Antes de escribir código, hazme las preguntas que necesites (cinco como máximo) y preséntame un plan con la estructura de carpetas, las dependencias, el esquema de datos y las fases. Espera mi aprobación. Orden de fases sugerido: esqueleto y herramientas; modelos, datos de ejemplo y almacenamiento; métricas; scoring, screening y alertas; fichas, journal, CLI y panel.
2. Inicializa git y trabaja fase a fase. Al acabar cada una, ejecuta ruff, mypy y pytest, corrige lo que falle, haz un commit con un mensaje claro y resúmeme en dos o tres líneas lo hecho. Pasa a la siguiente salvo que surja una decisión importante que no estuviera en el plan.
3. No añadas funcionalidades fuera de este alcance; si se te ocurren, apúntalas en docs/siguientes-pasos.md.

## Fuera de alcance por ahora
Conexión a proveedores reales, usuarios y permisos, despliegue, backtesting, optimización de carteras y cualquier ejecución de órdenes.

## Está terminado cuando
- Tras un uv sync limpio, ruff, mypy y pytest pasan sin errores.
- Un solo comando de la CLI carga los datos de ejemplo, ejecuta el pipeline y genera el ranking y las fichas.
- El panel de Streamlit muestra el ranking y el detalle de cada empresa.
- Me das un resumen final con lo construido, las decisiones tomadas y los siguientes pasos que recomiendas.
