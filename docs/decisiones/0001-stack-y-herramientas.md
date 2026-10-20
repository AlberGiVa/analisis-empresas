# 0001. Stack y herramientas

- Fecha: 2026-10-20
- Estado: aceptada (revisada el mismo día: Python 3.14 en lugar de 3.12)

## Contexto
El encargo fija el stack: Python 3.12 con uv, pandas, DuckDB, pydantic, Typer, Jinja2, Streamlit,
pytest, ruff y mypy. En el equipo de desarrollo no había uv y estaba instalado Python 3.14 (versión
oficial, firmada por la Python Software Foundation).

Al principio se descargó un Python 3.12 gestionado por uv. El antivirus corporativo lo señaló y el
departamento de informática preguntó por qué descargar Python si ya había uno instalado.

## Decisión
- **Python 3.14 del equipo.** Se usa el Python 3.14 ya instalado, en lugar de un 3.12
  descargado. Se comprobó que las 64 librerías del proyecto tienen versión compilada para 3.14.
  `pyproject.toml` impide que uv descargue intérpretes (`python-downloads = "never"`,
  `python-preference = "only-system"`).
- **uv.** Se instala con `py -m pip install --user uv`: su carpeta ya está en el PATH y no
  requiere permisos de administrador. Sus ejecutables están firmados digitalmente.
- **Estructura.** Carpeta `src/` con el paquete `company_analysis` y el backend de construcción
  `uv_build`. El comando de la CLI es `analisis`, con subcomandos en español porque son interfaz.
- **Añadidos al stack, sin sustituir ninguna pieza:**
  - PyYAML, para leer la configuración de la metodología.
  - pandas-stubs y types-PyYAML, para que mypy pueda trabajar en modo estricto.
  - pytest-socket, que bloquea cualquier conexión de los tests salvo las de loopback: garantiza que
    ningún test accede a internet.
- **Calidad.** `ruff format`, `ruff check`, `mypy --strict` y `pytest`, ejecutados por un hook de
  git versionado en `.githooks/` antes de cada commit.
- **Finales de línea LF** en el repositorio (`.gitattributes`), para que los datos de ejemplo
  regenerados coincidan byte a byte con los versionados también en Windows.

## Consecuencias
- El proyecto requiere Python 3.14 instalado en el equipo (instalador oficial de python.org).
- Tras clonar el repositorio hay que activar el hook una vez: `git config core.hooksPath .githooks`.
- Las versiones exactas quedan fijadas en `uv.lock`; actualizar una dependencia es un cambio
  explícito y revisable.
