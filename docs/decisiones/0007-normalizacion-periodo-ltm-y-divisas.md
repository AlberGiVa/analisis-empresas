# 0007. Normalización: periodo de referencia, LTM y divisas

- Fecha: 2026-10-20
- Estado: aceptada

## Contexto
Hay que comparar empresas con ejercicios fiscales y divisas distintos sin mezclar periodos, sin
usar datos que aún no se conocían y sin rellenar huecos.

## Decisión
- **Periodo de referencia.** Por empresa, el último periodo publicado a la fecha de análisis
  (anual o intermedio). Todas sus cifras se miden en él. Si falta una partida en ese periodo, no
  se toma de otro: se marca "sin dato".
- **LTM.**
  - Con datos anuales, el último ejercicio.
  - Con un periodo intermedio (acumulado del año): último ejercicio + acumulado actual − mismo
    acumulado del año anterior.
  - Se toleran cierres con hasta 7 días de diferencia (calendarios de 52/53 semanas).
- **Balance.** Saldo al cierre del periodo de referencia. ROE y ROIC usan el saldo de cierre, no
  la media: es una simplificación documentada.
- **Antigüedad máxima.** Cotización de acciones 10 días, de bonos 10 días, tipo de cambio 7 días
  y estados financieros 480 días. Pasado ese plazo, el dato se marca "desactualizado". Los valores
  son configurables.
- **Divisas.**
  - Las ratios se calculan en la divisa de reporte; el crecimiento también, para no mezclar el
    efecto de los tipos de cambio.
  - La capitalización se convierte de la divisa de cotización a la de reporte al tipo de la fecha
    de la cotización.
  - Las magnitudes en euros usan el tipo medio de los doce meses para los flujos, el tipo de
    cierre para el balance y el tipo de la fecha de la cotización para los valores de mercado
    (criterio análogo a la NIC 21).
- **Ejercicios que no cierran en diciembre.** Cada ejercicio se asigna al año natural en el que
  cae la mayoría de sus meses (de junio a diciembre, el mismo año; de enero a mayo, el anterior).
  Se usa para alinear las series anuales entre empresas.

## Consecuencias
- Dos empresas pueden tener periodos de referencia distintos (por ejemplo, ejercicio a diciembre
  y ejercicio a marzo). Es inherente al análisis a una fecha.
- Una empresa que publica tarde aparece con datos desactualizados en lugar de con cifras viejas
  presentadas como actuales.
