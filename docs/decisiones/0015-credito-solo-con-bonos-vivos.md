# 0015. Puntuación de crédito solo para emisores con bonos vivos

- Fecha: 2026-10-20
- Estado: aceptada (respuesta del usuario: "exigir bonos vivos")

## Contexto
Con la regla de cobertura, una empresa sin deuda ni bonos (HELV en los datos de ejemplo) puntuaba
en crédito solo por sus ratios de endeudamiento, que son los mejores del universo, y encabezaba el
ranking de crédito con un 97. Un acreedor no puede invertir en ella.

## Decisión
- Las puntuaciones admiten **factores obligatorios** (`required_factors` en `config/analysis.yaml`).
  Si uno de ellos no aplica a la empresa, la puntuación no se calcula. El motivo indica qué falta;
  por ejemplo: "La empresa no tiene bonos vivos (factor obligatorio: Diferencial frente a su
  tramo de rating)".
- La puntuación de crédito tiene como factor obligatorio el diferencial frente al tramo de
  rating. Sin bonos vivos, no hay puntuación de crédito.
- Si la empresa tiene bonos pero sin cotización vigente, el factor sí aplica y decide la regla de
  cobertura habitual.
- Los ratios de deuda de la empresa se siguen calculando y mostrando en la ficha.

## Otras decisiones tomadas a la vez
- **Pesos:** se mantienen iguales hasta que el equipo de gestión acuerde otros.
- **Mínimo de comparables:** se mantiene en 5 mientras se trabaja con los datos de ejemplo; hay que
  subirlo a 10 al conectar datos reales (anotado en la configuración y en siguientes pasos).

## Consecuencias
- La versión de la configuración pasa a `2026.10-2`. Las ejecuciones anteriores conservan la suya,
  y la alerta de cambio de puntuación avisa si se comparan ejecuciones con configuraciones
  distintas.
