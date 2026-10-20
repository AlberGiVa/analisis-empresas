"""Generation of docs/metricas.md from the metric registry (the single source of truth)."""

from company_analysis.config import MetricsConfig, NormalizationConfig
from company_analysis.figures import Status
from company_analysis.formatting import format_number
from company_analysis.metrics.base import MetricCategory, MetricDefinition
from company_analysis.metrics.registry import all_metrics

_STATUS_MEANINGS = {
    Status.OK: "El valor se ha calculado; se guardan los datos de entrada utilizados.",
    Status.MISSING: "Falta algún dato de entrada; el detalle indica cuál.",
    Status.NOT_APPLICABLE: (
        "La métrica no tiene sentido para esa empresa (por ejemplo, EBITDA en un banco) o la "
        "empresa no tiene el instrumento (bonos)."
    ),
    Status.DIVISION_BY_ZERO: "El denominador es cero.",
    Status.NOT_MEANINGFUL: (
        "El cálculo es posible pero no tiene sentido económico (por ejemplo, un PER con pérdidas)."
    ),
    Status.STALE: "Algún dato de entrada es más antiguo de lo permitido en la fecha de análisis.",
    Status.INSUFFICIENT_PEERS: "No hay suficientes comparables (empresas o bonos).",
}


def _direction(definition: MetricDefinition) -> str:
    if definition.higher_is_better is None:
        return "Informativa (sin sentido preferido)"
    return "Más alto" if definition.higher_is_better else "Más bajo"


def _applies_to(definition: MetricDefinition) -> str:
    if not definition.excluded_industries:
        return "Todas las empresas"
    excluded = ", ".join(
        sorted(industry.label.lower() for industry in definition.excluded_industries)
    )
    return f"Todas salvo {excluded}"


def _metric_section(definition: MetricDefinition) -> list[str]:
    lines = [
        f"### {definition.name} (`{definition.metric_id}`)",
        "",
        definition.description,
        "",
        "| | |",
        "|---|---|",
        f"| Fórmula | {definition.formula} |",
        f"| Unidad | {definition.unit.symbol} |",
        f"| Mejor si es | {_direction(definition)} |",
        f"| Aplica a | {_applies_to(definition)} |",
        "",
        f"**Interpretación.** {definition.interpretation}",
        "",
        "**Casos límite.**",
        "",
        *(f"- {case}" for case in definition.edge_cases),
        "",
    ]
    if definition.exclusion_reason:
        lines += [f"**Por qué no aplica.** {definition.exclusion_reason}", ""]
    return lines


def render_metrics_markdown() -> str:
    """Full text of the metrics dictionary."""
    normalization, metrics = NormalizationConfig(), MetricsConfig()
    tax = format_number(metrics.notional_tax_rate * 100, 0)
    buckets = ", ".join(bucket.name for bucket in metrics.rating_buckets)
    lines = [
        "# Diccionario de métricas",
        "",
        "> Generado automáticamente a partir del registro de métricas "
        "(`src/company_analysis/metrics/`). No lo edites a mano: ejecuta "
        "`uv run python scripts/generate_metrics_doc.py`. Un test comprueba que está al día.",
        "",
        "## Convenciones",
        "",
        "- **Periodo de referencia.** Es el último periodo publicado a la fecha de análisis. "
        "Todas las magnitudes de una empresa se miden en él, para no mezclar periodos.",
        "- **LTM (últimos doce meses).** Con datos anuales es el último ejercicio. Con un periodo "
        "intermedio: último ejercicio + acumulado del año en curso − mismo acumulado del año "
        "anterior.",
        "- **Balance.** Saldo al cierre del periodo de referencia.",
        "- **Divisas.** Las ratios se calculan en la divisa de reporte. La capitalización se pasa "
        "a esa divisa al tipo de cambio de la fecha de la cotización. Las magnitudes en euros "
        "usan el tipo medio de los doce meses para los flujos, el tipo de cierre para el balance "
        "y el tipo de la fecha de la cotización para los valores de mercado.",
        "- **Ejercicios que no cierran en diciembre.** Se comparan con el año natural en el que "
        "cae la mayoría de sus meses (un ejercicio cerrado en marzo de 2026 se compara con 2025).",
        f"- **Antigüedad máxima.** Cotización de acciones "
        f"{normalization.max_price_age_days} días, cotización de bonos "
        f"{normalization.max_quote_age_days} días, tipo de cambio "
        f"{normalization.max_fx_age_days} días y estados financieros "
        f"{normalization.max_financials_age_days} días.",
        f"- **Parámetros.** Tipo impositivo teórico del ROIC: {tax} %. Tramos de rating: "
        f"{buckets}. Mínimo de bonos por tramo: {metrics.min_bonds_per_rating_bucket}.",
        "- **Unidades.** Importes en millones; los porcentajes se guardan como fracción "
        "(0,052 = 5,2 %).",
        "",
        "Los valores por defecto de la antigüedad máxima y de los parámetros se pueden cambiar en "
        "`config/analysis.yaml`; cada ejecución guarda la configuración que usó.",
        "",
        "## Estados de un dato",
        "",
        "Un dato que falta o no aplica nunca se inventa: se marca con uno de estos estados y un "
        "detalle que explica el motivo.",
        "",
        "| Estado | Significado |",
        "|---|---|",
        *(f"| {status.label} | {meaning} |" for status, meaning in _STATUS_MEANINGS.items()),
        "",
    ]
    for category in MetricCategory:
        definitions = [d for d in all_metrics() if d.category is category]
        lines += [f"## {category.label}", ""]
        for definition in definitions:
            lines += _metric_section(definition)
    return "\n".join(lines).rstrip() + "\n"
