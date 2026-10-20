# 0003. Almacenamiento solo por inserción y lectura a fecha

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
El encargo pide dos cosas:
- Trazabilidad: cada ejecución registra qué datos usó y los datos históricos no se sobrescriben.
- Poder reconstruir qué se sabía en cada momento, para evitar el sesgo de anticipación (look-ahead).

## Decisión
- **Lotes de carga.** Cada carga es un lote (`load_batches`) con su fecha de carga (UTC), el
  proveedor y una huella SHA-256 del contenido. Toda fila de datos apunta a su lote.
- **Solo inserción.** Las tablas de datos de entrada nunca se actualizan ni se borran. Una
  corrección llega como una fila nueva en un lote posterior, y una reexpresión como una fila con
  fecha de publicación posterior.
- **Tres fechas por dato financiero:**
  - cierre del periodo (`period_end`);
  - publicación (`published_at`);
  - carga (la del lote).
- **Lectura a fecha** (`read_bundle(as_of, cutoff)`). Para cada clave se toma la versión más
  reciente con las dos condiciones:
  - publicada como tarde en `as_of`, para evitar el look-ahead;
  - cargada como tarde en `cutoff`, para que una ejecución se pueda reproducir.

  Los precios, cotizaciones y tipos de cambio se leen hasta `as_of`. Los bonos, solo los vivos en
  esa fecha.
- **Carga idempotente.** Cargar exactamente el mismo contenido no crea un lote nuevo.
- **Migraciones.** El esquema evoluciona con migraciones SQL numeradas (`storage/migrations/`),
  registradas en `schema_migrations`. Nunca se recrean tablas con datos.

## Consecuencias
- El volumen crece con cada corrección. Es aceptable a esta escala.
- No se representan las bajas: un emisor que deja de venir en las cargas sigue visible. Las
  bajas del universo se gestionarán con una lista de universo (ver siguientes pasos).
- Los atributos de los emisores (sector, nombre…) no tienen vigencia temporal: se usa su última
  versión cargada.
- Cada lote debe ser autocontenido: sus cotizaciones y datos deben referirse a emisores e
  instrumentos incluidos en el mismo lote.
