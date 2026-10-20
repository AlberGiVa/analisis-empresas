# Análisis de empresas — Fondo multiactivos

Herramienta interna que sistematiza el análisis de empresas cotizadas desde dos ángulos: como
**accionista** (valoración, rentabilidad, crecimiento) y como **acreedor** (endeudamiento,
capacidad de pago, diferencial de sus bonos).

Produce métricas, puntuaciones y alertas transparentes para apoyar al gestor. **No emite
recomendaciones de compra o venta.**

> Estado: en construcción (fase 1 de 5). El encargo completo está en
> [docs/encargo-inicial.md](docs/encargo-inicial.md).

## Puesta en marcha

Requisitos: [uv](https://docs.astral.sh/uv/) (descarga por sí mismo Python 3.12) y git.

```powershell
uv sync                                  # crea el entorno e instala dependencias
git config core.hooksPath .githooks      # activa las comprobaciones antes de cada commit
.\analisis --help                        # comandos disponibles
```

`.\analisis` es un atajo de Windows equivalente a `uv run python -m company_analysis`, que
funciona en cualquier sistema.

## Comprobaciones de calidad

```powershell
uv run ruff format --check .   # formato
uv run ruff check .            # lint
uv run python -m mypy          # tipos
uv run python -m pytest        # tests (sin acceso a internet)
```

## Problemas conocidos

**"Acceso denegado" al ejecutar Python o los tests.** Algunos antivirus corporativos solo dejan
ejecutar programas que ya conocen y bloquean los lanzadores `.exe` que uv crea en el entorno
virtual. Por eso todos los comandos usan `python -m …`. Si tampoco arranca Python, repara el
entorno (copia el intérprete original, que el antivirus sí permite):

```powershell
& (uv python find --system 3.12) scripts/fix_windows_venv.py
```

Hay que repetirlo si se borra o se vuelve a crear la carpeta `.venv`. Más detalle en
[docs/decisiones/0002-antivirus-y-entorno-virtual.md](docs/decisiones/0002-antivirus-y-entorno-virtual.md).

## Documentación

- [CLAUDE.md](CLAUDE.md): guía del proyecto (principios, arquitectura, convenciones, glosario).
- [docs/decisiones/](docs/decisiones/): una nota por cada decisión de diseño relevante.
- [docs/siguientes-pasos.md](docs/siguientes-pasos.md): ideas fuera del alcance actual.
