# Análisis de empresas — Fondo multiactivos

Herramienta interna que sistematiza el análisis de empresas cotizadas desde dos ángulos:
- como **accionista**: valoración, rentabilidad y crecimiento;
- como **acreedor**: endeudamiento, capacidad de pago y diferencial de sus bonos.

Calcula métricas con su fórmula documentada, puntuaciones que se descomponen factor a factor,
filtros y alertas. **No emite recomendaciones de compra o venta**: apoya al gestor, no decide por
él.

Es la base del proyecto, no un producto terminado. Trae datos sintéticos de ejemplo (20 empresas
ficticias) y carga datos reales desde una plantilla de Excel.

Para entender de un vistazo cómo está conectado y pensado, y qué podría llegar a tener, abre en el
navegador la muestra [docs/muestra-luceiro-capital.html](docs/muestra-luceiro-capital.html). Es un
único fichero: incluye los resultados de una ejecución sobre los datos de ejemplo y prueba en vivo
varias APIs públicas gratuitas.

## Puesta en marcha

Requisitos:
- Python 3.14 del instalador oficial de [python.org](https://www.python.org/).
- [uv](https://docs.astral.sh/uv/) (`py -m pip install --user uv`).
- git.

```powershell
uv sync                                           # instala las dependencias
uv run python scripts/remove_unused_launchers.py  # ver "Problemas conocidos"
.\analisis demo                                   # todo de una vez con los datos de ejemplo
.\analisis panel                                  # abre el panel en el navegador
```

`demo` hace cuatro cosas:
- carga los datos de ejemplo;
- ejecuta el análisis a 31/12/2025 y a 30/06/2026;
- genera el ranking y una ficha por empresa en `output\<ejecución>\`;
- muestra las alertas en pantalla.

`.\analisis` es un atajo de Windows para `uv run python -m company_analysis`.

## Uso diario

| Comando | Qué hace |
|---|---|
| `.\analisis cargar` | Carga los datos del proveedor en la base local. Nunca sobrescribe ni duplica. |
| `.\analisis ejecutar --fecha 2026-06-30` | Calcula métricas, puntuaciones, filtros y alertas a esa fecha y registra la ejecución. Sin fecha, usa la última con cotizaciones. |
| `.\analisis fichas` | Genera el ranking (HTML y CSV para Excel) y las fichas de la última ejecución. |
| `.\analisis nota nueva VALD "texto" --decision seguimiento` | Añade una nota o tesis al diario del analista. |
| `.\analisis nota listar VALD` | Muestra las notas de una empresa. |
| `.\analisis ejecuciones` | Muestra el registro de ejecuciones (fecha, datos, configuración y código). |
| `.\analisis panel` | Abre el panel: ranking con filtros y detalle de cada empresa. |

Qué se obtiene:
- **Ficha por empresa** (`fichas\<ID>.html`). Vista de acción y de crédito lado a lado, con el
  desglose de cada puntuación, los bonos, las alertas, los filtros, el histórico anual y las notas.
- **Ranking** (`ranking.html`), y **`ranking.csv`**, que se abre directamente en Excel.
- **Panel** en el navegador: el mismo contenido, con filtros.

La metodología se ajusta en [config/analysis.yaml](config/analysis.yaml) (factores, pesos, umbrales,
filtros y alertas). Las fórmulas están en [docs/metricas.md](docs/metricas.md).

## Datos reales

### Plantilla de Excel (Bloomberg, FactSet o a mano)

```powershell
.\analisis plantilla                          # crea data\import\plantilla-importacion.xlsx
.\analisis plantilla --ejemplo                # la misma plantilla, rellena con el ejemplo
.\analisis importar data\import\mis-datos.xlsx  # valida y carga el libro relleno
```

La plantilla se rellena con los complementos de Excel de Bloomberg o FactSet, o a mano. Su hoja
«Instrucciones» detalla cada columna. Si algo no cuadra, no se carga nada y se indica hoja, fila
y columna. Guía completa: [docs/importar-datos.md](docs/importar-datos.md). Los datos reales
nunca se suben al repositorio.

### Estudio con datos reales de hoy

```powershell
estudio-real\estudio todo   # 10 empresas reales: SEC, cotizaciones y BCE, en un espacio aislado
```

Prueba la herramienta con diez empresas reales de consumo básico de EE. UU. Las cuentas vienen de
la SEC, las cotizaciones de Nasdaq (contrastadas con Yahoo Finance) y los tipos de cambio del BCE.
Tiene su propia base de datos, metodología y carpeta de resultados, y genera un informe con
comparables, cambios entre dos fechas y la calidad y el origen de cada dato. Detalles en
[estudio-real/README.md](estudio-real/README.md).

## Web pública

**<https://albergiva.github.io/analisis-empresas/>**

Una web estática en GitHub Pages para consultar la herramienta desde cualquier sitio: basta con la
dirección de la web, sin usuario ni contraseña. Pide a los buscadores que no la muestren, así que
llega quien tenga el enlace (no es una protección: cualquiera con la dirección puede entrar). Solo
muestra datos que se pueden republicar:
- **Empresas reales:** el estudio de las diez empresas, con las cuentas de la SEC y los tipos de
  cambio del BCE. No hay cotizaciones, porque las condiciones de Nasdaq y Yahoo Finance no permiten
  publicarlas. Por eso faltan la capitalización, el PER, el EV/EBITDA y el FCF yield, y la
  puntuación de accionista es «sin valoración».
- **Ejemplo:** las 20 empresas ficticias con todas las funciones (cotizaciones, bonos y ratings).
- **Cómo funciona** (lectura de una puntuación, glosario, métricas, fuentes y límites),
  **Novedades** y la **Presentación** (la muestra de `docs/`).

Toda la web lleva la imagen de Luceiro Capital: logo, colores, tipografía y modo claro u oscuro.

El diario del analista nunca se publica.

```powershell
uv run python -m company_analysis.web construir --abrir   # la genera en _site\ y la abre
```

Se calcula en una carpeta temporal: no toca la base principal ni la del estudio.

En GitHub se actualiza sola, con cada cambio y cada mañana de martes a sábado. Si falla una
descarga, no se publica nada y sigue en línea la versión anterior. Dos avisos:
- GitHub detiene las actualizaciones programadas tras 60 días sin actividad en el repositorio. Se
  reactivan desde la pestaña Actions.
- La SEC pide identificarse con un nombre y un correo de contacto. En GitHub se indican en el
  secreto opcional `SEC_USER_AGENT`.

Detalles en [docs/decisiones/0018-web-publica.md](docs/decisiones/0018-web-publica.md).

## Comprobaciones de calidad

```powershell
uv run ruff format --check .   # formato
uv run ruff check .            # lint
uv run python -m mypy          # tipos
uv run python -m pytest        # tests (sin acceso a internet)
git config core.hooksPath .githooks   # las ejecuta antes de cada commit
```

## Problemas conocidos

**Antivirus corporativo y ejecutables.** El antivirus bloquea los programas que no conoce. Para
convivir con él:
- se usa el Python oficial instalado en el equipo;
- uv tiene prohibido descargar otro;
- todos los comandos ejecutan código Python con `python -m …`.

| Ejecutable | Firma | Función |
|---|---|---|
| `uv.exe`, `uvx.exe`, `uvw.exe` | Firmados | Gestor de paquetes de Python (PyPI). |
| `.venv\Scripts\python.exe`, `pythonw.exe` | Python Software Foundation | Lanzador oficial del entorno virtual. |
| `.venv\Scripts\ruff.exe` | Firmado | Revisor de estilo del código. |
| Otros `.venv\Scripts\*.exe` | Sin firma | Lanzadores que uv crea al instalar paquetes. No se usan: bórralos con `scripts/remove_unused_launchers.py`. |

**Base de datos ocupada.** DuckDB admite un solo proceso escribiendo. El panel solo lee y abre
conexiones cortas. Si un comando avisa de que la base está en uso, espera unos segundos o cierra el
panel.

## Documentación

- [CLAUDE.md](CLAUDE.md): guía del proyecto (principios, arquitectura, convenciones, glosario).
- [docs/metricas.md](docs/metricas.md): diccionario de métricas.
- [docs/decisiones/](docs/decisiones/): una nota por cada decisión de diseño relevante.
- [docs/siguientes-pasos.md](docs/siguientes-pasos.md): ideas fuera del alcance actual.
- [docs/novedades.yaml](docs/novedades.yaml): novedades de la herramienta, que se ven en la web.
- [data/sample/README.md](data/sample/README.md): datos de ejemplo y sus casos límite.
