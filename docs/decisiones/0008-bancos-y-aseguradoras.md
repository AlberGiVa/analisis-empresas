# 0008. Bancos y aseguradoras

- Fecha: 2026-10-20
- Estado: aceptada (respuesta del usuario: "puntuar lo aplicable")

## Contexto
El encargo pide marcar como "no aplica" en bancos y aseguradoras las métricas basadas en EBITDA,
deuda neta o valor de empresa.

## Decisión
- No aplican a bancos y aseguradoras: EV/EBITDA, ROIC, margen EBITDA, deuda neta/EBITDA y
  cobertura de intereses, además de las magnitudes de valor de empresa, EBITDA y deuda neta.
- Se amplía a otras dos métricas, con el acuerdo del usuario:
  - FCF yield: sus flujos operativos incluyen depósitos y préstamos;
  - deuda/capital: su "deuda" incluye depósitos y financiación, y su solvencia se mide con ratios
    de capital.
- Su puntuación de renta variable se calcula solo con los factores que les aplican: PER, ROE y
  crecimiento. La de crédito no se muestra, porque solo les quedaría el diferencial de sus bonos
  (ver la regla de cobertura en la fase de puntuación).
- El diferencial de sus bonos sí se calcula y se muestra.

## Consecuencias
- Para puntuar su vista de crédito harán falta métricas propias (CET1, ratio de solvencia, ratio
  combinado…): está en siguientes pasos.
