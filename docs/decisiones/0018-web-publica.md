# 0018. Web pública en GitHub Pages

- Fecha: 2026-10-20
- Estado: aceptada (petición del usuario: "abrirla desde cualquier sitio, con GitHub", "que sea
  abierta", sin usuarios ni contraseñas)

## Contexto
La herramienta solo se podía consultar en el equipo donde está instalada: el panel no escucha en la
red (decisión 0013) y los informes son ficheros locales. El usuario pidió abrirla desde cualquier
sitio, con GitHub, para cualquiera que tenga el enlace y sin usuarios ni contraseñas.

El encargo inicial decía "sin despliegue en esta fase", y CLAUDE.md lo recogía como principio. Este
cambio lo pide el usuario de forma expresa.

Publicar tiene un límite: no todos los datos se pueden republicar. Las cotizaciones del estudio
vienen de Nasdaq y Yahoo Finance, y sus condiciones no permiten publicarlas.

## Decisión
- **Web estática en GitHub Pages.** Solo páginas HTML y ficheros CSV: sin servidor, sin base de
  datos en línea y sin usuarios. Se mantiene "sin microservicios, Docker ni autenticación".
- **Repositorio público, web solo con enlace.** La cuenta gratuita de GitHub solo publica webs de
  repositorios públicos, así que el código y la documentación quedan a la vista; el usuario lo
  eligió así, incluida la página de muestra de Luceiro Capital (que no forma parte de la web). Cada
  página de la web pide a los buscadores que no la indexen (`noindex, nofollow`): llega quien tenga
  el enlace, aunque no es una protección. Con GitHub Pro el repositorio podría volver a ser
  privado sin perder la web.
- **Construcción** con `uv run python -m company_analysis.web construir` (módulo `web.py`). Todo se
  calcula en una carpeta temporal: nunca toca la base principal (`data/analysis.duckdb`) ni la del
  estudio (`estudio-real/datos/`). El resultado queda en `_site/`, que git ignora. Opciones:
  - `--salida CARPETA`: otra carpeta de destino;
  - `--descarga CARPETA`: usa una descarga ya hecha, sin cotizaciones, en lugar de descargar (para
    los tests o para trabajar sin conexión);
  - `--fecha AAAA-MM-DD` (repetible): por defecto, fin del semestre anterior y hoy;
  - `--abrir`: abre la página de inicio en el navegador.
- **Páginas**, todas con la misma barra de navegación y adaptadas al móvil y al modo oscuro:
  - Inicio: qué es la herramienta, resumen de las dos secciones, últimas alertas de las empresas
    reales y últimas novedades;
  - Empresas reales: el informe del estudio de las diez empresas, con ranking, CSV y fichas;
  - Ejemplo: las 20 empresas ficticias de `data/sample` con todas las funciones (cotizaciones,
    bonos y ratings), con ranking, CSV y fichas;
  - Cómo funciona: cómo se lee una puntuación, glosario, diccionario de métricas (generado desde
    el registro de métricas), fuentes y límites;
  - Novedades: se genera desde `docs/novedades.yaml`.
- **Empresas reales solo con datos republicables:**
  - SEC: datos públicos del Gobierno de EE. UU.;
  - BCE: reutilización libre citando la fuente.

  Sin cotizaciones no hay capitalización, valor de empresa (EV), PER, EV/EBITDA ni FCF yield.
- **Metodología propia de la web** (`estudio-real/metodologia-web.yaml`, versión
  `2026.10-web-1`): la del estudio sin nada que dependa del precio.
  - La puntuación de accionista pasa a ser "Puntuación de accionista sin valoración": ROE, ROIC,
    margen EBITDA y crecimiento de ventas.
  - Desaparecen los filtros que necesitan una cotización.
  - El gráfico pasa a ser "Rentabilidad frente a apalancamiento" (margen EBITDA frente a deuda
    neta/EBITDA).
- **El diario del analista nunca se publica.**
- **Actualización automática** con GitHub Actions (`.github/workflows/web.yml`):
  - cuándo: en cada cambio en la rama `main`, cada mañana de martes a sábado a las 05:30 UTC (tras
    el cierre de EE. UU. y la publicación de los tipos del BCE) y a mano desde la pestaña Actions;
  - qué hace: lint, tipos y tests; descarga los datos de la SEC y del BCE; construye la web y la
    publica en GitHub Pages;
  - si una descarga falla, no se publica nada y sigue en línea la versión anterior.
- **Identificación ante la SEC.** La SEC pide a los clientes automáticos un nombre y un correo de
  contacto. Se configura con el secreto opcional del repositorio `SEC_USER_AGENT` (lo mismo que
  `ANALYSIS_HTTP_USER_AGENT` en `.env`).

## Consecuencias
- Cualquiera con la dirección de la web puede verla. Contiene datos ficticios, datos públicos
  republicables y la documentación; nunca cotizaciones de las empresas reales ni el diario.
- Sigue valiendo que los datos reales de mercado nunca se suben al repositorio: el flujo descarga
  los datos públicos al construir la web y publica solo las páginas generadas. En git no entra
  ningún dato real.
- En la web, la vista de accionista de las empresas reales es más pobre que en el estudio, y así lo
  dice su nombre. El estudio local (`estudio-real\estudio todo`) no cambia: sigue usando
  cotizaciones, solo en este equipo.
- GitHub detiene los flujos programados de los repositorios públicos tras 60 días sin actividad. Se
  vuelven a activar desde la pestaña Actions.
- El principio de sencillez de CLAUDE.md queda así: sin microservicios, Docker ni autenticación; lo
  único publicado es una web estática con datos republicables.
