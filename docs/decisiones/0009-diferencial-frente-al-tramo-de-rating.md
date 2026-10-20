# 0009. Diferencial frente al tramo de rating

- Fecha: 2026-10-20
- Estado: aceptada (sentido: respuesta del usuario, "más diferencial puntúa mejor")

## Contexto
El encargo pide el diferencial de cada bono frente a la mediana de su tramo de rating. Hay que
precisar qué es un tramo, cuántos bonos hacen falta y cómo se pasa del bono a la empresa.

## Decisión
- **Tramos por letra:** AAA-AA, A, BBB, BB, B, y CCC o inferior. Se configuran en YAML.
- **Rating de cada bono.** El vigente a la fecha de análisis; si lo califican varias agencias, el
  peor (criterio conservador).
- **Comparación.** Mediana de todos los bonos del tramo con el mismo tipo de diferencial
  (Z-spread, OAS…), incluido el propio bono. Hacen falta al menos 3 bonos con cotización vigente;
  si no, "sin comparables suficientes".
- **Valor de la empresa.** Mediana de los valores de sus bonos con dato. Sin bonos vivos, "no
  aplica".
- **Sentido.** Más diferencial que la mediana puntúa mejor: el bono paga más por el mismo rating.
  Es coherente con la vista de acción, donde lo barato puntúa mejor. El deterioro se vigila con
  las alertas (rebaja de rating, apalancamiento) y con los factores fundamentales.

## Consecuencias y limitaciones
- No se distingue por vencimiento ni por divisa dentro de un tramo; con un universo mayor
  convendría hacerlo.
- La diferencia se mide en puntos básicos. Entre tramos con dispersiones muy distintas (BB frente
  a A), una diferencia relativa (%) podría comparar mejor. Ambas cosas están en siguientes pasos.
