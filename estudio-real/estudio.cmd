@echo off
rem Estudio con datos reales: usa su propia base de datos, metodologia y carpeta de salida
rem (todo dentro de esta carpeta). Ejemplos:
rem   estudio-real\estudio todo        descarga, carga, analiza a dos fechas y genera el informe
rem   estudio-real\estudio informe     vuelve a generar el informe de la ultima ejecucion
rem   estudio-real\estudio panel       abre el panel con los datos del estudio
uv run --project "%~dp0.." python -m company_analysis.study %*
