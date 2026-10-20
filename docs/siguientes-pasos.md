# Siguientes pasos

Ideas y mejoras detectadas durante el desarrollo que quedan fuera del alcance actual. Se apuntan
aquí en lugar de implementarse.

## Datos y proveedores
- Conectar Bloomberg o FactSet implementando la interfaz de proveedor. Los proveedores reales
  necesitarán recibir una petición (universo de emisores y rango de fechas).
- Cargas incrementales (por ejemplo, solo los precios del día): hoy cada lote debe ser
  autocontenido.
- Lista de universo con altas y bajas: con el almacenamiento solo por inserción, un emisor que deja
  de venir en las cargas sigue visible.
- Vigencia temporal de los atributos de los emisores (cambios de sector o de nombre).
- Mapear la taxonomía sectorial del proveedor (BICS, RBICS) a la taxonomía propia.
- Regla para combinar ratings de varias agencias: hoy se usa el peor; los índices suelen usar el
  intermedio de tres.
- Cotizaciones en peniques (GBp) de las acciones británicas: hoy se asumen en libras.
- Datos de periodos intermedios en los datos de ejemplo: el cálculo LTM ya los admite y está
  probado con casos hechos a mano.

## Metodología
- Métricas específicas para bancos y aseguradoras (P/VC, CET1, ratio de solvencia, ratio
  combinado), para poder puntuar su vista de crédito.
- Valor de empresa con intereses minoritarios y otros ajustes (arrendamientos, pensiones).
- ROE y ROIC sobre saldos medios del periodo en lugar del saldo de cierre.
- Diferencial frente al tramo: segmentar por vencimiento y divisa cuando el universo lo permita, y
  valorar una diferencia relativa (%) en lugar de en puntos básicos.

## Uso
- Uso compartido entre varios analistas: DuckDB admite un único escritor, así que un diario de
  notas común requeriría otro almacenamiento.
