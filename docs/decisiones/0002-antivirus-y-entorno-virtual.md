# 0002. Antivirus que bloquea ejecutables desconocidos

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
El equipo de desarrollo tiene un antivirus corporativo (Panda Security) que solo permite ejecutar
programas cuyo fichero ya conoce. Se comprobó así:
- una copia idéntica de `python.exe` arranca;
- la misma copia con un byte añadido da "Acceso denegado".

Quedan bloqueados dos tipos de ejecutables que uv genera:
- el lanzador `.venv/Scripts/python.exe` del entorno virtual;
- los lanzadores de los paquetes instalados (`pytest.exe`, `mypy.exe`, `streamlit.exe`, `analisis.exe`).

Los binarios distribuidos tal cual en los paquetes, como `ruff.exe`, sí arrancan. Es probable que
los equipos de los analistas tengan la misma política.

## Decisión
- Todos los comandos documentados usan `python -m …` (`python -m pytest`, `python -m mypy`,
  `python -m company_analysis`), que no dependen de los lanzadores `.exe`.
- `analisis.cmd` en la raíz es un atajo para Windows de `uv run python -m company_analysis`.
- `scripts/fix_windows_venv.py` sustituye el lanzador del entorno virtual por copias idénticas del
  intérprete base y sus DLL. CPython sigue reconociendo el entorno virtual gracias a `pyvenv.cfg`.
- El comando `analisis` se mantiene en `pyproject.toml` para los equipos sin esta restricción.

## Consecuencias
- Si se borra o se recrea `.venv`, hay que volver a ejecutar `scripts/fix_windows_venv.py`.
- Una alternativa más limpia es pedir al departamento de sistemas que autorice los ejecutables de
  la carpeta del proyecto o del entorno virtual.
