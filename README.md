# Análisis de empresas — Fondo multiactivos

Herramienta interna que sistematiza el análisis de empresas cotizadas desde dos ángulos: como
**accionista** (valoración, rentabilidad, crecimiento) y como **acreedor** (endeudamiento,
capacidad de pago, diferencial de sus bonos).

Produce métricas, puntuaciones y alertas transparentes para apoyar al gestor. **No emite
recomendaciones de compra o venta.**

> Estado: en construcción (fase 4 de 5). El encargo completo está en
> [docs/encargo-inicial.md](docs/encargo-inicial.md).

## Puesta en marcha

Requisitos:
- Python 3.14, del instalador oficial de [python.org](https://www.python.org/).
- [uv](https://docs.astral.sh/uv/), que se instala con `py -m pip install --user uv`.
- git.

```powershell
uv sync                                          # crea el entorno e instala dependencias
uv run python scripts/remove_unused_launchers.py # borra lanzadores .exe que no se usan
git config core.hooksPath .githooks              # comprobaciones antes de cada commit
.\analisis --help                                # comandos disponibles
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

**Antivirus corporativo y ejecutables.** El antivirus bloquea los programas que no conoce. Para
convivir con él:
- se usa el Python oficial instalado en el equipo;
- uv tiene prohibido descargar otro;
- todos los comandos ejecutan código Python con `python -m …`.

| Ejecutable | Firma | Función |
|---|---|---|
| `uv.exe`, `uvx.exe`, `uvw.exe` | Firmados | Gestor de paquetes de Python (PyPI). |
| `.venv\Scripts\python.exe`, `pythonw.exe` | Python Software Foundation | Lanzador oficial del entorno virtual. |
| `.venv\Scripts\ruff.exe` | Firmado | Revisor de estilo del código. |
| Otros `.venv\Scripts\*.exe` | Sin firma | Lanzadores que uv crea al instalar paquetes. No se usan: bórralos con `scripts/remove_unused_launchers.py`. |

Más detalle en
[docs/decisiones/0002-antivirus-y-entorno-virtual.md](docs/decisiones/0002-antivirus-y-entorno-virtual.md).

## Documentación

- [CLAUDE.md](CLAUDE.md): guía del proyecto (principios, arquitectura, convenciones, glosario).
- [docs/metricas.md](docs/metricas.md): diccionario de métricas.
- [docs/decisiones/](docs/decisiones/): una nota por cada decisión de diseño relevante.
- [docs/siguientes-pasos.md](docs/siguientes-pasos.md): ideas fuera del alcance actual.
