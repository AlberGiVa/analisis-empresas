# 0006. Métricas: valor o motivo, y un registro central

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
Dos principios del encargo afectan a las métricas:
- toda métrica tiene su fórmula documentada;
- un dato que falta o no aplica nunca se inventa ni se rellena en silencio.

Además, los gestores tienen que poder entender de dónde sale cada número.

## Decisión
- **Resultado de cada métrica (`MetricResult`).** Es un valor con los datos de entrada usados, o un
  estado con su motivo en español. Los estados son:
  - sin dato;
  - no aplica;
  - división por cero;
  - no significativo;
  - dato desactualizado;
  - sin comparables suficientes.

  Nunca hay NaN sin explicación.
- **Registro central (`metrics/registry.py`).** Cada métrica se define una sola vez con:
  identificador, nombre, categoría, descripción, fórmula, unidad, interpretación, casos límite,
  si es mejor más alta o más baja y a qué industrias no aplica. La aplicabilidad la comprueba el
  registro, no cada fórmula.
- **`docs/metricas.md` se genera a partir del registro.** Un test falla si el documento no
  coincide, así que la fórmula documentada y la calculada no pueden divergir.
- **Dos clases de métricas:**
  - de empresa: se calculan con la "foto" de una sola empresa;
  - de universo: necesitan a todas, como el diferencial frente al tramo de rating.
- **Magnitudes en euros.** Capitalización, valor de empresa, ventas, EBITDA y deuda neta son
  entradas del mismo registro (categoría "Magnitudes en euros", sin sentido preferido). Así
  tienen la misma trazabilidad y se pueden usar en los filtros.
- **Lógica sobre objetos tipados.** Las fórmulas trabajan con objetos tipados (dataclasses y
  modelos pydantic), no con DataFrames: son más fáciles de leer, de probar con valores
  calculados a mano y de verificar con mypy. pandas se usa en los bordes (carga en DuckDB,
  tablas de informes y panel).

## Consecuencias
- Añadir una métrica es escribir su función y su definición, y regenerar el diccionario (ver
  CLAUDE.md).
- Rendimiento: con miles de emisores sigue siendo suficiente. Si algún día no lo fuera, se podría
  vectorizar sin cambiar el contrato del registro.
