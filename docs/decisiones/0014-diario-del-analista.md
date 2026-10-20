# 0014. Diario del analista

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
El encargo pide un registro de tesis de inversión y notas del analista con empresa, fecha, autor,
texto y decisión.

## Decisión
- **Solo inserción.** Las notas nunca se modifican ni se borran; una corrección es una nota nueva.
  Así el diario es también un registro histórico.
- **Fecha y autor.** Cada nota tiene la fecha a la que se refiere (por defecto, hoy) y la fecha y
  hora en que se registró. El autor es, por defecto, el usuario del equipo.
- **La decisión es siempre del analista.** Se elige de una lista cerrada: sin decisión, en
  seguimiento, invertir, mantener, reducir o desinvertir. La herramienta nunca propone una.
- **Validación.** Solo se admiten notas de empresas que existen en los datos cargados.
- **Visibilidad.** Las notas aparecen en la ficha y en el panel, la más reciente primero.

## Consecuencias
- Con una base por equipo, el diario no se comparte entre analistas. Un diario común requeriría
  otro almacenamiento (ver siguientes pasos).
