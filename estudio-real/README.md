# Estudio con datos reales

Una prueba de la herramienta con empresas y cifras reales, a día de hoy, separada del resto: tiene
su propia base de datos, su propia metodología y su propia carpeta de resultados. Nada de lo que
descarga o calcula se mezcla con la base principal ni se sube al repositorio.

## Qué analiza

Diez empresas de consumo básico de EE. UU. con acciones y bonos en el mercado (alimentación y
bebidas; productos de hogar e higiene). Son comparables entre sí y publican sus cuentas en la SEC
con la fecha exacta de cada informe. El porqué de cada empresa, sus identificadores verificados y
cómo se construye su deuda están en [universo.yaml](universo.yaml).

## Cómo se usa

Desde la carpeta del proyecto, en PowerShell:

```powershell
estudio-real\estudio todo          # descarga, carga, analiza a dos fechas y genera el informe
```

El informe queda en `estudio-real\salida\<ejecución>\estudio.html`, junto al ranking y las fichas de
la herramienta. Otros comandos:

| Comando | Qué hace |
|---|---|
| `estudio-real\estudio descargar` | Descarga los datos públicos en una carpeta nueva con fecha. Nunca modifica una descarga anterior. |
| `estudio-real\estudio cargar` | Valida la última descarga y la carga en la base del estudio (solo inserción). Muestra los avisos de calidad. |
| `estudio-real\estudio ejecutar` | Analiza a fin del semestre anterior y a hoy. Con `--fecha AAAA-MM-DD` (repetible), a las fechas que se indiquen. |
| `estudio-real\estudio informe` | Genera el informe del estudio, el ranking y las fichas de la última ejecución. |
| `estudio-real\estudio panel` | Abre el panel con los datos del estudio (solo en este equipo). |
| `estudio-real\estudio ejecuciones` | Lista las ejecuciones del estudio. |

## De dónde salen los datos

| Fuente | Qué aporta | Condiciones |
|---|---|---|
| SEC EDGAR (`data.sec.gov`) | Estados financieros con la fecha de presentación de cada informe, y el registro de informes | Datos públicos. Pide identificarse: configura `ANALYSIS_HTTP_USER_AGENT` en `.env` con un nombre y un correo de contacto. |
| Nasdaq | Cotizaciones de cierre diarias | Servicio web sin licencia de datos: válido para esta prueba interna, no para un uso habitual. |
| Yahoo Finance | Segunda fuente de cotizaciones, para contrastarlas, y mercado de cotización | Igual que Nasdaq. |
| Banco Central Europeo | Tipos de cambio diarios frente al euro | Reutilización libre citando la fuente. |

Cada descarga guarda un `manifest.json` con la dirección, la hora y la huella (SHA-256) de cada
fichero, así que cualquier cifra del informe se puede rastrear hasta el fichero del que salió.

## Cómo está pensado

- **Lectura a fecha.** Cada cifra lleva la fecha en que la SEC recibió el informe. Una ejecución
  solo ve lo presentado hasta su fecha, y las cifras corregidas después se guardan como una
  publicación nueva (sin sobrescribir la anterior).
- **Cifras tal como se publican.** Normas contables de EE. UU., sin los ajustes que las empresas
  presentan como «ajustados». Por eso un deterioro o la venta de un negocio entran enteros en el
  EBITDA de los doce meses. El informe detecta estos trimestres atípicos y los señala, y el gráfico
  deja fuera a las empresas afectadas.
- **Deuda revisada a mano.** Cada empresa presenta su deuda en líneas distintas. Para cada una se
  han elegido las líneas de su balance y se ha comprobado que suman sin duplicar y que la serie es
  continua.
- **Calidad visible.** Cada empresa tiene una sección con el último informe registrado, el periodo
  que se usa, la etiqueta de la SEC de la que sale cada partida, las correcciones posteriores, el
  desglose de la deuda y el contraste de cotizaciones con una segunda fuente.

## Límites

- **Sin diferenciales de bonos ni ratings.** No hay una fuente gratuita y fiable, así que la vista
  de acreedor solo usa fundamentales (ver [metodologia.yaml](metodologia.yaml)).
- **Retraso de la SEC.** A veces un informe ya presentado tarda en aparecer en los datos
  estructurados. El informe lo avisa y se usan las cifras anteriores.
- **Diez empresas.** Con un grupo tan pequeño, un cambio en una empresa mueve los percentiles de
  las demás.
- **No es una recomendación de inversión:** describe y compara.

## Qué se versiona y qué no

Se versionan este README, el universo, la metodología y el lanzador `estudio.cmd`. Las carpetas
`datos/` (descargas y base de datos) y `salida/` (informes) contienen datos reales y git las ignora.
