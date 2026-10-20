# 0016. Importación de datos reales por Excel

- Fecha: 2026-10-20
- Estado: aceptada (respuesta del usuario: "importación por ficheros")

## Contexto
El usuario quería meter datos reales de Bloomberg o FactSet. La conexión directa por API depende de
cuatro cosas que aún no están resueltas:
- el tipo de licencia (terminal frente a Data License o API);
- las credenciales;
- el visto bueno de informática, porque la librería de Bloomberg trae binarios y el antivirus
  bloquea lo desconocido;
- confirmar que el contrato permite guardar los datos y puntuar con ellos.

Los analistas ya usan los complementos de Excel de ambos proveedores.

## Decisión
- **Plantilla de Excel en español** (`.\analisis plantilla`).
  - Una hoja por tipo de dato, con listas desplegables.
  - Una hoja de instrucciones generada desde el propio código, con unidades y campos orientativos
    de Bloomberg y FactSet.
  - Los estados financieros van en formato ancho (una columna por partida), que es como los
    devuelven los complementos. Al cargarlos se convierten al formato largo de la base.
- **Lectura directa del `.xlsx`** con `openpyxl` (Python puro, sin ejecutables). Evita los
  problemas del CSV de Excel en español (separador, coma decimal, fechas). También admite números
  y fechas escritos como texto en notación española o inglesa.
- **Validación completa antes de cargar.** Si hay un solo error no se carga nada, y cada error
  indica hoja, fila y columna en español. Los avisos (por ejemplo, una fecha de publicación igual a
  la de cierre) no bloquean la carga.
- **Mismo contrato que el resto de proveedores.** `WorkbookProvider` implementa la interfaz común y
  pasa el test de contrato. Un test comprueba que los datos de ejemplo, pasados por Excel, se
  recuperan idénticos.
- **Carga:** `.\analisis importar libro.xlsx`. Los libros con datos reales viven en `data\import`,
  que git ignora.

## Consecuencias
- Cada libro debe ser una carga completa (empresas, acciones y bonos incluidos). Las cargas
  incrementales siguen en siguientes pasos.
- Los códigos de Bloomberg y FactSet de la plantilla son orientativos y hay que verificarlos en
  cada terminal.
- La conexión directa por API se podrá añadir después sin cambiar el resto: será otro proveedor
  más.
