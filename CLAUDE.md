# CLAUDE.md

## Propósito
Herramienta interna de un fondo multiactivos (acciones y bonos corporativos) que sistematiza el
análisis de empresas: cada emisor se ve como accionista y como acreedor. Usuarios: gestores y
analistas que no programan y hoy trabajan con Excel. Universo: cotizadas europeas y
estadounidenses de mediana y gran capitalización. Moneda base: EUR. Encargo original:
`docs/encargo-inicial.md`.

## Principios (no negociables)
- Apoya al gestor, no decide: métricas, puntuaciones y alertas; nunca recomendaciones.
- Toda puntuación se descompone en sus factores y toda métrica tiene su fórmula documentada.
- Un dato que falta o no aplica nunca se inventa ni se rellena en silencio: se marca con su motivo.
- Trazabilidad: cada ejecución queda registrada (fecha, datos usados, versión de la
  configuración) y los datos históricos no se sobrescriben (solo inserción).
- Los datos reales de mercado nunca se suben al repositorio; solo los sintéticos de `data/sample/`.
- Sencillez: sin microservicios, Docker, autenticación ni despliegue.

## Comandos
```powershell
uv sync                                       # instalar
uv run python -m pytest                       # tests
uv run ruff format . ; uv run ruff check .    # formato y lint
uv run python -m mypy                         # tipos (modo estricto)
uv run python -m company_analysis --help      # CLI (atajo en Windows: .\analisis)
```
- Usa siempre `python -m …`: el antivirus del equipo (Panda) bloquea los lanzadores `.exe` que
  uv genera (`pytest.exe`, `analisis.exe`…). `ruff.exe` sí arranca.
- Si `.venv` se recrea y Python da "Acceso denegado", ejecuta
  `& (uv python find --system 3.12) scripts/fix_windows_venv.py`.
- El hook `.githooks/pre-commit` ejecuta formato, lint, tipos y tests; se activa con
  `git config core.hooksPath .githooks`.

## Arquitectura (`src/company_analysis/`)
| Módulo | Responsabilidad |
|---|---|
| `settings.py` | Rutas y secretos desde `.env` (prefijo `ANALYSIS_`). |
| `clock.py` | Fechas y horas; en la base, marcas de tiempo UTC sin zona. |
| `models/` | Modelos de dominio validados (pydantic): emisores, instrumentos, estados financieros en formato largo, mercado y `DataBundle` (lote autocontenido). |
| `providers/` | Interfaz `DataProvider`, `SampleProvider` (CSV de `data/sample`) y generador determinista de datos sintéticos. |
| `storage/` | DuckDB: migraciones SQL, carga solo por inserción en lotes y lectura a fecha (`read_bundle`). |
| `cli.py` | Comando `analisis` (Typer); subcomandos y mensajes en español. |

Datos: `data/sample/` (sintéticos, versionados; ver su README) y `data/*.duckdb` (local, ignorado).

## Convenciones
- Código, nombres y comentarios en inglés; documentación y textos de interfaz en español.
- Todo el código tipado (`mypy --strict`); ruff para lint y formato (línea de 100).
- Los tests nunca acceden a internet (pytest-socket solo permite loopback).
- Commits por fase, solo con ruff, mypy y pytest en verde.
- Decisiones de diseño: una nota corta en `docs/decisiones/NNNN-titulo.md`.
- Ideas fuera de alcance: `docs/siguientes-pasos.md`, no en el código.

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
- **Look-ahead**: usar un dato antes de su fecha de publicación; el sistema lo impide.
