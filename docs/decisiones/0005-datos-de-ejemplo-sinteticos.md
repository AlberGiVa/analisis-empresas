# 0005. Datos de ejemplo sintéticos

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
Hacen falta datos realistas para desarrollar y probar sin proveedor, y las licencias de los datos
reales impiden versionarlos.

## Decisión
- Un generador determinista dentro del paquete (`providers/sample_generator.py`), con semilla fija,
  invocado por `scripts/generate_sample_data.py`. Escribe CSV legibles (y abribles en Excel) en
  `data/sample/`, que se versionan.
- Identificadores imposibles de confundir con reales: ISIN con prefijo `ZZ` y LEI con prefijo
  `ZZZZ`, con dígitos de control válidos. Un test exige estos prefijos en todos los datos de
  ejemplo, como protección para que no se cuelen datos reales.
- Cotizaciones semanales y tipos de cambio diarios: es suficiente para calcular las métricas y las
  medias de tipos de cambio, y mantiene el repositorio ligero (unos 560 KB).
- Los casos límite del encargo se incluyen a propósito y están documentados en
  `data/sample/README.md`.

## Consecuencias
- Un test regenera los datos y exige que coincidan byte a byte con los versionados.
- NumPy no garantiza la misma secuencia aleatoria entre versiones. Si ese test falla tras
  actualizar NumPy, hay que regenerar los datos y versionarlos de nuevo.
- La empresa sin deuda no tiene bonos, aunque eso choca con "entre 1 y 3 bonos por empresa".
