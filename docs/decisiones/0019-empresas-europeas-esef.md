# 0019. Empresas europeas con sus informes anuales oficiales (ESEF)

- Fecha: 2026-10-21
- Estado: aceptada (petición del usuario: un apartado expreso de Europa en las empresas, más
  europeas en el Panel y lo máximo posible del sector de los equipos de protección individual)

## Contexto
Las empresas reales del estudio y de la web salían solo de la SEC, así que eran todas de EE. UU.
La SEC no tiene las cuentas de las cotizadas europeas, y la web solo puede publicar datos de uso
libre (decisión 0018): Bloomberg o FactSet no valen ahí.

Desde 2021, toda empresa cotizada en un mercado regulado de la UE publica su informe financiero
anual en XBRL (formato ESEF, normas NIIF); las británicas, igual. filings.xbrl.org, de XBRL
International, los recoge y ofrece cada uno en xBRL-JSON, con una API abierta, y dice que no hay
restricciones al uso de los datos. Cubre bien España (casi todo el IBEX 35), Francia, Italia,
Países Bajos, Bélgica, Austria, Dinamarca, Finlandia y Reino Unido; no Alemania, Portugal,
Suecia, Irlanda, Suiza ni Noruega (sin informes desde 2025).

## Decisión
- **Segunda fuente de cuentas: ESEF** (`providers/public/esef.py`). Cada empresa del universo dice
  de dónde salen sus cuentas: `source: sec` (CIK) o `source: esef` (LEI).
- **El mismo lector.** Los hechos consolidados de cada informe (sin dimensiones: ni segmentos ni
  desgloses) se convierten a la forma de los datos de la SEC, y los lee el mismo código a fecha
  (`sec.py`), con otra tabla de etiquetas (`IFRS_ITEM_SOURCES`). Así valen igual la lectura a
  fecha, las correcciones, las líneas de deuda, las etiquetas fijadas y la trazabilidad.
- **Fecha de publicación:** la que da la fuente del informe; si no la da, la de su llegada a
  filings.xbrl.org, que es posterior. Nunca se usa una cifra antes de que fuera pública.
- **Solo informes anuales.** Es lo único obligatorio en el formato: los doce últimos meses de una
  europea son su último ejercicio (las de EE. UU. tienen trimestres). Se descarga, por empresa, el
  último informe anual público en la primera fecha de análisis y los posteriores (unos 2-20 MB
  cada uno); los años anteriores salen de las cifras comparativas que repite cada informe.
- **Sin cotizaciones europeas:** no hay una fuente libre. En el estudio local sus métricas de
  mercado quedan sin dato, con su motivo.
- **Regiones en la web:** las empresas se presentan por región (Europa primero, EE. UU. después),
  cada una con sus medianas, aunque se puntúan juntas por sector. El Panel deja elegir Europa,
  EE. UU. o el sector EPI.
- **Sector EPI:** industria propia (`personal_protection`) y una página con las cotizadas del sector:
  las que tienen cuentas libres, analizadas como el resto; las demás (Dräger, Ansell, Delta Plus…),
  solo con los widgets de TradingView, que muestran sus datos sin republicarlos. La página no nombra
  a ninguna empresa en cartera.

## Consecuencias
- Cada empresa europea se revisa a mano como las de EE. UU. (`estudio-real/candidatas/`): no hay
  etiqueta NIIF de resultado operativo ni de EBITDA, y la deuda, las extensiones propias y la
  divisa de las cuentas cambian de una empresa a otra (Avon Technologies, británica, presenta en
  dólares).
- La comparación entre regiones mezcla doce meses trimestrales (EE. UU.) con el último ejercicio
  (Europa): la columna «Cifras» de cada empresa dice cuál usa.
- filings.xbrl.org puede cambiar o limitar su API. Si falla, la construcción de la web se detiene
  y sigue publicada la versión anterior.
