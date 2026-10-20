# 0001. Stack y herramientas

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
El encargo fija el stack: Python 3.12 con uv, pandas, DuckDB, pydantic, Typer, Jinja2, Streamlit,
pytest, ruff y mypy. En el equipo de desarrollo no había uv y solo estaba instalado Python 3.14.

## Decisión
- uv se instala con `py -m pip install --user uv` (su carpeta ya está en el PATH; no requiere
  permisos de administrador). uv descarga y gestiona su propio Python 3.12 para el proyecto
  (`.python-version`), sin tocar otras instalaciones.
- Estructura `src/` con el paquete `company_analysis` y el backend de construcción `uv_build`.
  El comando de la CLI es `analisis` y sus subcomandos van en español porque son interfaz.
- Se añaden al stack, sin sustituir ninguna pieza:
  - **PyYAML**, para leer la configuración de la metodología.
  - **pandas-stubs** y **types-PyYAML**, para que mypy pueda trabajar en modo estricto.
  - **pytest-socket**, que bloquea cualquier conexión de los tests salvo las de loopback
    (garantiza que ningún test accede a internet).
- Calidad: `ruff format`, `ruff check`, `mypy --strict` y `pytest`, ejecutados por un hook de git
  versionado en `.githooks/` antes de cada commit.
- Finales de línea LF en el repositorio (`.gitattributes`) para que los datos de ejemplo
  regenerados coincidan byte a byte con los versionados también en Windows.

## Consecuencias
- Tras clonar el repositorio hay que activar el hook una vez: `git config core.hooksPath .githooks`.
- Las versiones exactas quedan fijadas en `uv.lock`; actualizar una dependencia es un cambio
  explícito y revisable.
