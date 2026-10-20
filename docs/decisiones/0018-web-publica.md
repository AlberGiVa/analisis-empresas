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
  eligió así, con la marca y la página de muestra de Luceiro Capital. Cada
  página de la web pide a los buscadores que no la indexen (`noindex, nofollow`): llega quien tenga
  el enlace, aunque no es una protección. Con GitHub Pro el repositorio podría volver a ser
  privado sin perder la web.
- **Imagen de Luceiro Capital.** A petición del usuario, toda la web usa la identidad de la muestra
  (`docs/muestra-luceiro-capital.html`): logo sobre placa blanca, verde corporativo, Marcellus y
  Albert Sans, índice lateral y modo claro u oscuro (`web_estilo.html.j2`). El logo está en
  `reports/static/luceiro-logo.webp`. La muestra se publica tal cual como `presentacion.html`, con
  un enlace de vuelta a la web. Los informes locales mantienen su diseño sobrio.
- **Estilos y Configuración.** Además de Luceiro (el de serie), dos estilos: Terminal (inspirado
  en los terminales de datos financieros: fondo negro, ámbar y letra monoespaciada; siempre
  oscuro) y Prensa (papel salmón y tipografía de periódico). La página Configuración deja elegir
  estilo, modo claro u oscuro, densidad de las tablas y tamaño del texto. Son atributos de
  `<html>` guardados en el navegador de cada visitante (`localStorage`); nada se envía a ningún
  sitio.
- **Español e inglés.** La web se genera en español y se copia traducida en `en/`. El módulo
  `i18n` traduce cada texto del HTML con el catálogo `i18n/en.yaml`: frases exactas y patrones
  para las que llevan cifras, fechas o nombres, y pasa las cifras a notación inglesa. Así el
  núcleo sigue en español y no hay que traducir dos veces las plantillas. Un texto nuevo que el
  catálogo no conozca se queda en español y se lista (`--pendientes`); las pruebas exigen que
  todo lo que hoy muestra la web esté traducido. La presentación tiene su propia versión inglesa
  (`docs/muestra-luceiro-capital.en.html`).
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
    reales;
  - Empresas reales: el informe del estudio de las empresas reales, con ranking, CSV y fichas;
  - Casos de ejemplo: una empresa ficticia por caso (13 de las 20 de `data/sample`, que se
    siguen usando para comparar), con todas las funciones (cotizaciones,
    bonos y ratings), con ranking, CSV y fichas;
  - Cómo funciona: cómo se lee una puntuación, glosario, diccionario de métricas (generado desde
    el registro de métricas), fuentes y límites;
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
