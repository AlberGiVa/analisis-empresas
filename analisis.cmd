@echo off
rem Atajo para Windows: ejecuta la CLI del proyecto desde cualquier carpeta.
rem Equivale a "uv run python -m company_analysis" y no depende de los lanzadores .exe de uv,
rem que algunos antivirus corporativos bloquean.
uv run --project "%~dp0." python -m company_analysis %*
