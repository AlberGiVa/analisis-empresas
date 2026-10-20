# 0010. Puntuaciones: percentiles, grupo de referencia y cobertura

- Fecha: 2026-10-20
- Estado: aceptada (los valores no significativos se excluyen: respuesta del usuario)

## Contexto
El encargo pide dos puntuaciones separadas, una de renta variable y otra de crédito, basadas en
percentiles dentro de cada sector. Si el sector tiene pocas empresas, se usa el universo completo
como referencia. Factores y pesos van en YAML; cada puntuación lleva su cobertura, y por debajo de
un umbral no se muestra.

## Decisión
- **Percentil clásico, de 0 a 100, donde 100 es el mejor del grupo.** Se calcula como (valores
  peores + la mitad de los iguales, incluido el propio) / tamaño del grupo. Es robusto a valores
  extremos, reparte los empates y se explica en una frase. El sentido de cada métrica (más alto o
  más bajo es mejor) viene del registro de métricas.
- **Grupo de referencia, por factor.** Las empresas de su sector con dato en ese factor si son al
  menos `min_peers` (5); si no, el universo, siempre que llegue a ese mínimo. Si tampoco, el factor
  queda "sin comparables suficientes". El desglose indica qué grupo se usó y cuántas empresas
  tenía.
- **Pesos relativos.** Se reparten entre los factores con dato. La puntuación es la media
  ponderada de sus percentiles, y la contribución de cada factor suma exactamente la puntuación.
- **Cobertura.** Es el peso de los factores con dato dividido entre el peso de los factores que
  aplican a la empresa; los "no aplica" no cuentan. La puntuación no se muestra si la cobertura
  baja del mínimo (60 %) o si hay menos factores con dato del mínimo (3 en renta variable, 2 en
  crédito). Se guarda el motivo. Así un banco puntúa en renta variable con PER, ROE y crecimiento,
  y no en crédito, donde solo le quedaría el diferencial.
- **Valores no significativos** (PER con pérdidas, EV/EBITDA con EBITDA negativo…). Se excluyen:
  bajan la cobertura en lugar de contar como el peor del grupo. Esas empresas ya puntúan bajo en
  rentabilidad y hacen saltar alertas.
- **Pesos iniciales iguales**, como punto de partida neutral. El equipo puede ajustarlos en
  `config/analysis.yaml`.

## Consecuencias
- Con pocos datos, los percentiles son poco finos (con 5 empresas solo hay 5 niveles). Con un
  universo real conviene subir `min_peers`.
- Comparar con el universo mezcla sectores. Es lo que pide el encargo para sectores pequeños, y el
  desglose lo hace visible.
- Las magnitudes en euros son informativas y no pueden ser factores; la configuración lo
  comprueba.
