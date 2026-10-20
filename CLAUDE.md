# CLAUDE.md

## Propósito
Herramienta interna de un fondo multiactivos (acciones y bonos corporativos) que sistematiza el
análisis de empresas: cada emisor se ve como accionista y como acreedor.
- Usuarios: gestores y analistas que no programan y hoy trabajan con Excel.
- Universo: cotizadas europeas y estadounidenses de mediana y gran capitalización.
- Moneda base: EUR.
- Encargo original: `docs/encargo-inicial.md`.

## Principios (no negociables)
- Apoya al gestor, no decide: métricas, puntuaciones y alertas; nunca recomendaciones.
- Toda puntuación se descompone en sus factores y toda métrica tiene su fórmula documentada.
- Un dato que falta o no aplica nunca se inventa ni se rellena en silencio: se marca con su motivo.
- Trazabilidad: cada ejecución queda registrada (fecha, datos usados, versión de la
  configuración) y los datos históricos no se sobrescriben (solo inserción).
- Los datos reales de mercado nunca se suben al repositorio; solo los sintéticos de `data/sample/`.
- Sencillez: sin microservicios, Docker ni autenticación. Lo único publicado es una web estática
  (GitHub Pages) con datos republicables.

## Comandos
```powershell
uv sync                                          # instalar
uv run python scripts/remove_unused_launchers.py # tras instalar: borra lanzadores .exe sin uso
uv run python -m pytest                          # tests
uv run ruff format . ; uv run ruff check .       # formato y lint
uv run python -m mypy                            # tipos (modo estricto)
.\analisis demo                                  # carga ejemplo, 2 ejecuciones, ranking y fichas
.\analisis cargar | ejecutar [--fecha AAAA-MM-DD] | fichas | ejecuciones | panel
.\analisis nota nueva VALD "texto" --decision seguimiento ; .\analisis nota listar VALD
.\analisis plantilla [--ejemplo] ; .\analisis importar data\import\libro.xlsx   # datos reales
uv run python scripts/probar_apis.py             # prueba de conexión a las APIs públicas (no guarda nada)
estudio-real\estudio todo | descargar | cargar | ejecutar | informe | panel   # estudio con datos reales (aislado)
uv run python -m company_analysis.web construir [--abrir]   # web pública (GitHub Pages): solo datos republicables
```
- `.\analisis` equivale a `uv run python -m company_analysis`.
- Python 3.14 del equipo (oficial, firmado). uv nunca descarga intérpretes (`[tool.uv]` en
  `pyproject.toml`); no lo cambies sin hablar con informática.
- Usa siempre `python -m …`: el antivirus del equipo (Panda) bloquea los lanzadores `.exe` que
  genera uv. El proyecto no declara comandos instalables por ese motivo.
- El hook `.githooks/pre-commit` ejecuta formato, lint, tipos y tests; se activa con
  `git config core.hooksPath .githooks`.

## Arquitectura (`src/company_analysis/`)
Flujo de una ejecución (`pipeline.py`):
1. Lectura a fecha (`storage`).
2. "Foto" de cada empresa (`normalization`).
3. Métricas (`metrics`).
4. Puntuaciones (`scoring`).
5. Filtros y alertas (`screening`).
6. Registro de la ejecución y sus resultados (`storage/runs.py`).

Las fichas y el panel leen esos resultados guardados (`reports`, `app`).

| Módulo | Responsabilidad |
|---|---|
| `settings.py` | Rutas y secretos desde `.env` (prefijo `ANALYSIS_`). |
| `config.py`, `config_loader.py` | Metodología de `config/analysis.yaml`: modelos, validación y huella. |
| `models/` | Modelos de dominio validados (pydantic): emisores, instrumentos, estados financieros en formato largo, mercado y `DataBundle` (lote autocontenido). |
| `providers/` | Interfaz `DataProvider`, `SampleProvider` (CSV de `data/sample`), generador determinista de datos sintéticos y `WorkbookProvider` (plantilla de Excel para datos reales; `docs/importar-datos.md`). |
| `providers/public/` | Datos reales de fuentes públicas (SEC EDGAR, Nasdaq/Yahoo, BCE): descarga a carpetas con fecha y manifiesto, lectura a fecha de la SEC y revisión de calidad. Solo lo usan el estudio y la web. |
| `study.py` | Estudio con datos reales, aislado en `estudio-real/` (rutas fijas en el código; nunca toca la base principal). Decisión 0017. |
| `web.py` | Web pública estática (GitHub Pages): ejemplo completo y empresas reales sin cotizaciones, construida en una carpeta temporal. Decisión 0018. |
| `i18n/` | Versión inglesa de la web: traduce los textos del HTML generado con el catálogo `en.yaml` (frases exactas y patrones) y pasa las cifras a notación inglesa. Lo que falta se queda en español y se lista. |
| `storage/` | DuckDB: migraciones SQL, carga solo por inserción, lectura a fecha (`read_bundle`) y ejecuciones con sus resultados (`runs.py`). |
| `figures.py` | `Status` y `Figure`: un valor o el motivo por el que no está disponible. |
| `normalization/` | Periodo de referencia, LTM, divisas (`FxTable`), alineación de ejercicios y `CompanySnapshot`. |
| `metrics/` | Registro central de métricas (renta variable, crédito, magnitudes en euros) y generador de `docs/metricas.md`. |
| `scoring/` | Percentiles por sector (o universo) y puntuaciones con desglose y cobertura. |
| `screening/` | Filtros con nombre y reglas de alerta. |
| `pipeline.py`, `provenance.py` | Ejecución completa y su procedencia (código, commit, usuario). |
| `journal.py` | Diario del analista (solo inserción; la decisión es siempre del analista). |
| `reports/` | Vistas de una ejecución, fichas HTML (Jinja2), ranking HTML y CSV para Excel. |
| `app/dashboard.py` | Panel Streamlit de solo lectura: ranking con filtros y detalle por empresa. |
| `cli.py`, `formatting.py` | CLI (Typer) y formato español de números y fechas. |

Datos y salidas: `data/sample/` (sintéticos, versionados), `data/*.duckdb` y `output/<ejecución>/`
(locales, ignorados por git). El estudio real guarda descargas, base e informes en
`estudio-real/datos/` y `estudio-real/salida/`, también ignorados: nunca subas datos reales. La web
se genera en `_site/` (ignorada) y la publica GitHub Actions (`.github/workflows/web.yml`).

## Convenciones
- Código, nombres y comentarios en inglés; documentación y textos de interfaz en español.
- Todo el código tipado (`mypy --strict`); ruff para lint y formato (línea de 100).
- Los tests nunca acceden a internet (pytest-socket solo permite loopback).
- Commits por fase, solo con ruff, mypy y pytest en verde.
- Decisiones de diseño: una nota corta en `docs/decisiones/NNNN-titulo.md`.
- Ideas fuera de alcance: `docs/siguientes-pasos.md`, no en el código.
- Cambiar la metodología (pesos, umbrales, filtros): edita `config/analysis.yaml` y sube su
  `version`. Las ejecuciones guardan la configuración que usaron.

## Añadir una métrica
1. Si necesita una partida nueva, añádela al catálogo `FinancialItem` (`models/financials.py`).
2. Escribe la función en `metrics/equity.py`, `credit.py` o `magnitudes.py`. Recibe un
   `CompanySnapshot` y devuelve un `MetricResult`; usa `first_unavailable`, `inputs_of` y `divide`
   para propagar motivos y registrar las entradas.
3. Regístrala con `register(CompanyMetric(...))`, con todos los textos en español: descripción,
   fórmula, interpretación, casos límite y, si no aplica a alguna industria, el motivo.
4. Añade tests con valores calculados a mano y cada caso límite (`tests/unit/test_metrics_*.py`).
5. Regenera el diccionario: `uv run python scripts/generate_metrics_doc.py`.
6. Si debe puntuar, añádela como factor en `config/analysis.yaml`.

## Añadir un proveedor de datos
1. Crea `providers/<nombre>.py` con una clase que herede de `DataProvider`, con un `name` estable y
   un `fetch()` que devuelva un `DataBundle` autocontenido. Las cifras van en la divisa de reporte,
   en millones, con las convenciones de signo de `models/financials.py`.
2. Regístrala en `PROVIDERS` (`providers/__init__.py`) con su nombre para la CLI.
3. Añádela a `PROVIDER_FACTORIES` en `tests/unit/test_providers.py` para que pase el contrato. Los
   tests usan respuestas sintéticas grabadas, nunca la red.
4. Credenciales en `.env` (documentadas en `.env.example`), nunca en el código.

## Glosario mínimo
- **LTM** (*last twelve months*): suma de los últimos doce meses de una magnitud de flujo.
- **EBITDA**: resultado operativo antes de amortizaciones; aproxima la generación de caja operativa.
- **Deuda neta**: deuda financiera menos caja y equivalentes.
- **EV** (*enterprise value*): capitalización bursátil más deuda neta.
- **FCF** (*free cash flow*): flujo de caja operativo menos inversiones en inmovilizado (capex).
- **Diferencial (spread)**: rentabilidad extra de un bono sobre la referencia sin riesgo, en puntos
  básicos (pb; 100 pb = 1 %).
- **Tramo de rating**: grupo de calificaciones de la misma letra (A, BBB, BB…).
- **Prelación**: orden de cobro de un bono en caso de impago (garantizado, sénior, subordinado).
- **Percentil**: posición de un valor dentro de un grupo, de 0 a 100 (100 es el mejor).
- **Cobertura**: parte del peso de los factores aplicables que tiene dato.
- **Look-ahead**: usar un dato antes de su fecha de publicación; el sistema lo impide.
