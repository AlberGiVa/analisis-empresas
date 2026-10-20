# Siguientes pasos

Ideas y mejoras detectadas durante el desarrollo que quedan fuera del alcance actual. Se apuntan
aquí en lugar de implementarse.

## Datos y proveedores
- Conectar Bloomberg o FactSet implementando la interfaz de proveedor. Los proveedores reales
  necesitarán recibir una petición (universo de emisores y rango de fechas).
- Cargas incrementales (por ejemplo, solo precios del día): hoy cada lote debe ser autocontenido.
- Lista de universo con altas y bajas: con el almacenamiento solo por inserción, un emisor que deja
  de venir en las cargas sigue visible.
- Vigencia temporal de los atributos de los emisores (cambios de sector o de nombre).
- Mapear la taxonomía sectorial del proveedor (BICS, RBICS) a la taxonomía propia.
- Regla para combinar ratings de varias agencias (p. ej., el peor o el intermedio de tres).
- Cotizaciones en peniques (GBp) de las acciones británicas: hoy se asumen en libras.

## Metodología
- Métricas específicas para bancos y aseguradoras (P/VC, CET1, ratio de solvencia, ratio
  combinado), para poder puntuar su vista de crédito.

## Uso
- Uso compartido entre varios analistas: DuckDB admite un único escritor, así que un diario de
  notas común requeriría otro almacenamiento.
