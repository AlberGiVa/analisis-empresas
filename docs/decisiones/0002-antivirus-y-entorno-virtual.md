# 0002. Antivirus que bloquea ejecutables desconocidos

- Fecha: 2026-10-20
- Estado: aceptada (revisada el mismo día, al pasar a Python 3.14)

## Contexto
El equipo tiene un antivirus corporativo (Panda Security) que solo deja ejecutar programas cuyo
fichero ya conoce. Se comprobó así:
- una copia idéntica de `python.exe` arranca;
- la misma copia con un byte añadido da "Acceso denegado".

Con el Python 3.12 descargado por uv, dos tipos de ejecutables quedaban bloqueados:
- el lanzador del entorno virtual (`.venv\Scripts\python.exe`, sin firmar);
- los lanzadores de comandos de las librerías (`pytest.exe`, `mypy.exe`, `streamlit.exe`…): un
  ejecutable genérico con unas líneas de Python añadidas, distinto en cada caso.

Esas pruebas y bloqueos generaron avisos que revisó el departamento de informática.

## Decisión
- **Python del equipo.** Se usa el Python 3.14 instalado (firmado por la Python Software
  Foundation). El lanzador del entorno virtual es entonces el oficial, también firmado, y el
  antivirus lo deja ejecutar. uv tiene prohibido descargar intérpretes.
- **Comandos con `python -m …`.** Todos los comandos documentados (`python -m pytest`,
  `python -m mypy`, `python -m company_analysis`) ejecutan el código Python de las librerías sin
  pasar por lanzadores `.exe`.
- **Lanzadores sin uso.** `scripts/remove_unused_launchers.py` borra los lanzadores que uv genera
  al instalar paquetes. Solo quedan `python.exe`, `pythonw.exe` (PSF) y `ruff.exe` (firmado).
- **Atajo `analisis.cmd`** en la raíz: en Windows equivale a
  `uv run python -m company_analysis`.

## Consecuencias
- Tras cada `uv sync` que instale o actualice paquetes conviene ejecutar
  `uv run python scripts/remove_unused_launchers.py`.
- El comando `analisis` se mantiene en `pyproject.toml` para los equipos sin esta restricción.
- Inventario de ejecutables y su función: ver el README ("Problemas conocidos").
