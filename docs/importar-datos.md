# Cómo cargar datos reales (Bloomberg, FactSet o a mano)

La herramienta carga datos reales desde un libro de Excel con una plantilla fija. El libro se puede
rellenar con los complementos de Excel de Bloomberg o FactSet, o a mano. La conexión directa por
API llegará cuando haya licencia, credenciales y visto bueno de informática (ver
`docs/siguientes-pasos.md`).

## Pasos

1. **Crea la plantilla.**
   ```powershell
   .\analisis plantilla                # data\import\plantilla-importacion.xlsx, vacía
   .\analisis plantilla --ejemplo      # data\import\ejemplo-importacion.xlsx, rellena de ejemplo
   ```
   El libro de ejemplo contiene las 20 empresas ficticias: sirve para ver cómo se rellena cada hoja.

2. **Rellénala.** La hoja «Instrucciones» explica cada columna:
   - si es obligatoria;
   - qué poner y en qué unidades;
   - de qué campo de Bloomberg o FactSet puede salir.

   Las columnas con valores cerrados (país, sector, divisa, prelación…) tienen lista desplegable.

3. **Cárgala.**
   ```powershell
   .\analisis importar data\import\mis-datos.xlsx
   ```
   - Si hay problemas, no se carga nada. La herramienta lista cada error con su hoja, fila y
     columna; por ejemplo: `Hoja «Bonos», fila 7, columna «Vencimiento»: fecha no válida`.
   - Si todo está bien, crea un lote de carga. Volver a cargar el mismo libro no duplica nada.
   - Los avisos (por ejemplo, una fecha de publicación igual a la de cierre) no impiden la carga,
     pero conviene revisarlos.

4. **Analiza.**
   ```powershell
   .\analisis ejecutar --fecha 2026-09-30
   .\analisis fichas
   ```

## Reglas importantes

- **Cada libro es una carga completa.** Debe incluir siempre las hojas Emisores, Acciones y Bonos,
  aunque solo quieras actualizar precios.
- **Una celda vacía es "sin dato".** La herramienta nunca la rellena. No pongas cero si el dato es
  desconocido.
- **La fecha de publicación es imprescindible.** Es la que impide usar unos resultados antes de que
  se conocieran (en Bloomberg, `ANNOUNCEMENT_DT`).
- **Unidades:**
  - importes en millones de la divisa de reporte; acciones en millones;
  - gastos financieros y capex en positivo (el `CAPITAL_EXPEND` de Bloomberg viene en negativo:
    cambia el signo);
  - cupones y rentabilidades en %, diferenciales en puntos básicos;
  - tipos de cambio en unidades por 1 euro (como `EURUSD Curncy`).
- **Las fórmulas tienen que estar calculadas.** Si el libro usa fórmulas de Bloomberg o FactSet,
  guárdalo después de que se calculen: la herramienta lee los valores guardados.
- **Los códigos de Bloomberg y FactSet son orientativos.** Compruébalos en el terminal (`FLDS`) o en
  la ayuda de FactSet antes de usarlos.

## Licencias y confidencialidad

- Los libros con datos reales se guardan en `data\import` (git ignora esa carpeta) o fuera del
  proyecto. **Nunca se suben al repositorio.**
- Antes de cargar datos de forma sistemática, confirma con quien gestione el contrato con
  Bloomberg o FactSet que permite guardarlos en una base local y calcular puntuaciones con
  ellos. Las licencias de terminal suelen restringir ese uso.

## Errores frecuentes

| Mensaje | Qué hacer |
|---|---|
| `valor no admitido «…»; elige uno de la lista desplegable` | Usa la lista desplegable de esa columna. |
| `fecha no válida` | Escribe la fecha como fecha de Excel (dd/mm/aaaa). |
| `se esperaba un número` | Quita textos o símbolos de la celda (por ejemplo, «n.d.»): déjala vacía si no hay dato. |
| `ISIN no válido` / `LEI no válido` | Revisa el código; el dígito de control no cuadra. |
| `… de un emisor desconocido` | El identificador de la columna Emisor no existe en la hoja Emisores. |
| `divisa … distinta de la de reporte` | Las cifras deben ir en la divisa de reporte de la empresa. |
| `La hoja «Emisores» está vacía` | El libro no tiene empresas: la plantilla está sin rellenar. |
