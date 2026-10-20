# Siguientes pasos

Ideas y mejoras detectadas durante el desarrollo que quedan fuera del alcance actual. Se apuntan
aquí en lugar de implementarse.

## Datos y proveedores
- Conexión directa por API con Bloomberg (Desktop API o Data License) o FactSet (API), como un
  proveedor más. Hoy los datos reales entran por la plantilla de Excel (`docs/importar-datos.md`).
  Requisitos previos:
  - saber qué tiene contratado el fondo;
  - credenciales en `.env`;
  - visto bueno de informática (la librería de Bloomberg trae binarios);
  - confirmar que el contrato permite guardar los datos y puntuar con ellos.

  Además, la interfaz tendrá que recibir una petición (universo de emisores y rango de fechas).
- Verificar en cada terminal los códigos orientativos de Bloomberg y FactSet de la plantilla.
- Estudio con datos reales (`estudio-real/`, decisión 0017). Mejoras detectadas al hacerlo:
  - fuente de diferenciales de bonos y ratings (hoy la vista de acreedor del estudio solo usa
    fundamentales);
  - leer el XBRL del propio informe cuando la SEC tarda en pasarlo a sus datos estructurados (hace
    falta identificarse con un correo de contacto en `ANALYSIS_HTTP_USER_AGENT`);
  - datos de dos clases de acciones (excluida Hershey) y empresas sin resultado operativo
    publicado (excluida Clorox);
  - EBITDA ajustado de un proveedor con licencia, para comparar con el contable;
  - ampliar el universo, incluidas cotizadas europeas: ESMA o los registros nacionales no dan
    estados financieros estructurados como la SEC.
- Proveedores con APIs públicas y gratuitas, sin licencia. Hay una prueba de conexión
  (`scripts/probar_apis.py`), una demostración en vivo en `docs/muestra-luceiro-capital.html` y el
  estudio con datos reales (SEC, Nasdaq y BCE). Pendientes:
  - BCE: tipos de cambio diarios, para sustituir la hoja «Tipos de cambio»;
  - BCE: curva de la deuda AAA del euro, para calcular un diferencial propio de cada bono;
  - GLEIF: comprobar los LEI (caducados, matriz y grupo);
  - ESMA FIRDS: datos de referencia de bonos (cupón, vencimiento, nominal);
  - SEC EDGAR: llevar a la herramienta principal lo que ya usa el estudio;
  - FRED: diferenciales de mercado ICE BofA como contexto (solo tres años de historia);
  - OpenFIGI: traducir ISIN a ticker para pedir datos a Bloomberg.

  Antes de usarlas, revisar las condiciones de uso de cada fuente.
- Cargas incrementales (por ejemplo, solo los precios del día): hoy cada lote debe ser
  autocontenido.
- Lista de universo con altas y bajas: con el almacenamiento solo por inserción, un emisor que deja
  de venir en las cargas sigue visible.
- Vigencia temporal de los atributos de los emisores (cambios de sector o de nombre).
- Mapear la taxonomía sectorial del proveedor (BICS, RBICS) a la taxonomía propia.
- Regla para combinar ratings de varias agencias: hoy se usa el peor; los índices suelen usar el
  intermedio de tres.
- Cotizaciones en peniques (GBp) de las acciones británicas: hoy se asumen en libras.
- Datos de periodos intermedios en los datos de ejemplo: el cálculo LTM ya los admite y está
  probado con casos hechos a mano.

## Metodología
- Métricas específicas para bancos y aseguradoras (P/VC, CET1, ratio de solvencia, ratio
  combinado), para poder puntuar su vista de crédito.
- Valor de empresa con intereses minoritarios y otros ajustes (arrendamientos, pensiones).
- ROE y ROIC sobre saldos medios del periodo en lugar del saldo de cierre.
- Diferencial frente al tramo: segmentar por vencimiento y divisa cuando el universo lo permita, y
  valorar una diferencia relativa (%) en lugar de en puntos básicos.
- Pesos por bloques temáticos (valoración, rentabilidad, crecimiento) en lugar de por factor.
- Alerta específica de "ángel caído" (paso de grado de inversión a high yield), hoy solo indicado
  en el mensaje de la rebaja.
- Pesos de los factores acordados por el equipo de gestión (hoy son iguales, como punto de
  partida neutral).
- Al conectar datos reales, subir el mínimo de comparables por sector (`min_peers`) de 5 a 10.

## Trazabilidad
- Comando para reproducir una ejecución pasada (misma fecha, mismo corte de datos y su
  configuración guardada) y comparar los resultados.
- Archivado de ejecuciones antiguas si la base crece mucho.

## Fichas y panel
- Añadir notas al diario desde el panel (hoy solo desde la CLI, para que el panel no escriba).
- Gráficos de evolución (cotización, diferencial, puntuaciones entre ejecuciones) en fichas y
  panel.
- Comparar dos ejecuciones en el panel (qué ha cambiado y por qué).
- Exportación a Excel (.xlsx) con formato, además del CSV actual.
- Lanzador del panel con doble clic para quien no use la consola.

## Uso
- Uso compartido entre varios analistas: DuckDB admite un único escritor, así que un diario de
  notas común requeriría otro almacenamiento.
- Pedir a informática que autorice los ejecutables del entorno, o mantener el procedimiento actual
  (Python oficial y `python -m`).
