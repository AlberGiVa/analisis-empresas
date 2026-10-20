"""Credit metrics: the company seen by a creditor (leverage, debt service, bond spreads)."""

from collections import defaultdict
from collections.abc import Sequence
from statistics import median

from company_analysis.config import MetricsConfig
from company_analysis.figures import Status
from company_analysis.metrics.base import (
    CompanyMetric,
    MetricCategory,
    MetricResult,
    Unit,
    UniverseMetric,
    UniverseOutput,
    divide,
    first_unavailable,
    inputs_of,
)
from company_analysis.metrics.equity import FINANCIALS_EXCLUDED
from company_analysis.metrics.registry import register
from company_analysis.models import FINANCIAL_INSTITUTIONS
from company_analysis.models import FinancialItem as Item
from company_analysis.normalization import BondSnapshot, CompanySnapshot


def _net_debt_to_ebitda(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    debt, cash, ebitda = s.stock(Item.TOTAL_DEBT), s.stock(Item.CASH), s.flow(Item.EBITDA)
    if problem := first_unavailable(debt, cash, ebitda):
        return problem
    inputs = inputs_of(debt, cash, ebitda)
    return divide(debt.number() - cash.number(), ebitda, inputs, unit=f"M {s.currency}")


def _interest_coverage(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    ebitda, interest = s.flow(Item.EBITDA), s.flow(Item.INTEREST_EXPENSE)
    if problem := first_unavailable(ebitda, interest):
        return problem
    return divide(ebitda.number(), interest, inputs_of(ebitda, interest), unit=f"M {s.currency}")


def _debt_to_equity(s: CompanySnapshot, _config: MetricsConfig) -> MetricResult:
    debt, equity = s.stock(Item.TOTAL_DEBT), s.stock(Item.TOTAL_EQUITY)
    if problem := first_unavailable(debt, equity):
        return problem
    return divide(debt.number(), equity, inputs_of(debt, equity), unit=f"M {s.currency}")


def _bond_excess_spreads(
    snapshots: Sequence[CompanySnapshot], config: MetricsConfig
) -> dict[str, tuple[str, MetricResult]]:
    """Each bond's spread minus the median of its rating bucket (same spread type)."""
    results: dict[str, tuple[str, MetricResult]] = {}
    buckets: dict[tuple[str, str], list[tuple[str, BondSnapshot]]] = defaultdict(list)
    for snapshot in snapshots:
        for bond in snapshot.bonds:
            isin = bond.bond.isin
            if bond.rating is None:
                results[isin] = (
                    snapshot.issuer_id,
                    MetricResult.unavailable(Status.MISSING, "el bono no tiene rating"),
                )
            elif not bond.spread.ok or bond.quote is None:
                results[isin] = (snapshot.issuer_id, MetricResult.from_figure(bond.spread))
            else:
                bucket = config.bucket_for(bond.rating.rating).name
                buckets[(bucket, bond.quote.spread_type.value)].append((snapshot.issuer_id, bond))
    minimum = config.min_bonds_per_rating_bucket
    for (bucket, _spread_type), members in buckets.items():
        if len(members) < minimum:
            detail = f"solo {len(members)} bono(s) en el tramo {bucket} (mínimo {minimum})"
            for issuer_id, bond in members:
                results[bond.bond.isin] = (
                    issuer_id,
                    MetricResult.unavailable(Status.INSUFFICIENT_PEERS, detail),
                )
            continue
        bucket_median = median(bond.spread.number() for _, bond in members)
        for issuer_id, bond in members:
            assert bond.rating is not None
            inputs = {
                "Diferencial del bono (pb)": bond.spread.number(),
                f"Mediana del tramo {bucket} (pb)": bucket_median,
                "Bonos en el tramo": float(len(members)),
            }
            detail = f"rating {bond.rating.rating} ({bond.rating.agency}), tramo {bucket}"
            results[bond.bond.isin] = (
                issuer_id,
                MetricResult.computed(bond.spread.number() - bucket_median, inputs, detail),
            )
    return results


def _spread_vs_rating_bucket(
    snapshots: Sequence[CompanySnapshot], config: MetricsConfig
) -> UniverseOutput:
    bonds = _bond_excess_spreads(snapshots, config)
    issuers: dict[str, MetricResult] = {}
    for snapshot in snapshots:
        own = [(bond.bond.isin, bonds[bond.bond.isin][1]) for bond in snapshot.bonds]
        available = {isin: result.value for isin, result in own if result.value is not None}
        if not own:
            issuers[snapshot.issuer_id] = MetricResult.unavailable(
                Status.NOT_APPLICABLE, "la empresa no tiene bonos vivos"
            )
        elif available:
            issuers[snapshot.issuer_id] = MetricResult.computed(
                median(available.values()),
                available,
                f"mediana de {len(available)} de {len(own)} bonos",
            )
        else:
            statuses = {result.status for _, result in own}
            status = statuses.pop() if len(statuses) == 1 else Status.MISSING
            detail = "; ".join(f"{isin}: {result.detail}" for isin, result in own)
            issuers[snapshot.issuer_id] = MetricResult.unavailable(status, detail)
    return UniverseOutput(issuers=issuers, bonds=bonds)


NET_DEBT_TO_EBITDA = register(
    CompanyMetric(
        metric_id="net_debt_to_ebitda",
        name="Deuda neta/EBITDA",
        category=MetricCategory.CREDIT,
        unit=Unit.MULTIPLE,
        higher_is_better=False,
        description="Años de EBITDA necesarios para pagar la deuda neta.",
        formula="(Deuda financiera − Caja) / EBITDA LTM",
        interpretation=(
            "Cuanto más bajo, menor endeudamiento. Un valor negativo indica caja neta (más caja "
            "que deuda)."
        ),
        edge_cases=(
            "EBITDA negativo: no significativo (si además hay deuda neta positiva, salta la "
            "alerta de apalancamiento).",
            "EBITDA cero: división por cero.",
            "Caja neta: valor negativo válido.",
            "Bancos y aseguradoras: no aplica.",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_net_debt_to_ebitda,
    )
)

INTEREST_COVERAGE = register(
    CompanyMetric(
        metric_id="interest_coverage",
        name="Cobertura de intereses",
        category=MetricCategory.CREDIT,
        unit=Unit.MULTIPLE,
        higher_is_better=True,
        description="Veces que el EBITDA cubre los gastos financieros.",
        formula="EBITDA LTM / Gastos financieros LTM",
        interpretation="Cuanto más alta, más holgura para pagar los intereses.",
        edge_cases=(
            "Sin gastos financieros (por ejemplo, sin deuda): división por cero.",
            "EBITDA negativo: valor válido (cobertura negativa).",
            "Bancos y aseguradoras: no aplica.",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=FINANCIALS_EXCLUDED,
        compute=_interest_coverage,
    )
)

DEBT_TO_EQUITY = register(
    CompanyMetric(
        metric_id="debt_to_equity",
        name="Deuda/capital",
        category=MetricCategory.CREDIT,
        unit=Unit.MULTIPLE,
        higher_is_better=False,
        description="Deuda financiera en relación con el patrimonio neto total.",
        formula="Deuda financiera / Patrimonio neto total",
        interpretation="Cuanto más baja, menos apalancada está la empresa en términos de balance.",
        edge_cases=(
            "Patrimonio negativo: no significativo.",
            "Patrimonio cero: división por cero.",
            "Sin deuda: valor cero, válido.",
            "Bancos y aseguradoras: no aplica (su deuda incluye la financiación de su actividad).",
        ),
        excluded_industries=FINANCIAL_INSTITUTIONS,
        exclusion_reason=(
            "No aplica a bancos y aseguradoras: su deuda incluye depósitos y la financiación de "
            "su actividad, y su solvencia se mide con ratios de capital."
        ),
        compute=_debt_to_equity,
    )
)

SPREAD_VS_RATING_BUCKET = register(
    UniverseMetric(
        metric_id="spread_vs_rating_bucket",
        name="Diferencial frente a su tramo de rating",
        category=MetricCategory.CREDIT,
        unit=Unit.BASIS_POINTS,
        higher_is_better=True,
        description=(
            "Diferencia entre el diferencial de cada bono y la mediana de los bonos de su mismo "
            "tramo de rating. Para la empresa, la mediana de sus bonos."
        ),
        formula=(
            "Por bono: Diferencial del bono − Mediana del diferencial de los bonos del mismo "
            "tramo de rating y tipo de diferencial. Por empresa: mediana de sus bonos."
        ),
        interpretation=(
            "Positivo: el bono paga más que sus comparables de rating (más compensación por el "
            "mismo rating). Negativo: paga menos. En la puntuación de crédito, más alto puntúa "
            "mejor; el deterioro se vigila con las alertas y los factores de apalancamiento."
        ),
        edge_cases=(
            "Bono sin rating: sin dato.",
            "Tramo con menos bonos del mínimo (3 por defecto): sin comparables suficientes.",
            "Cotización con más antigüedad de la permitida: dato desactualizado.",
            "Empresa sin bonos vivos: no aplica.",
            "Bono con ratings de varias agencias: se usa el peor.",
        ),
        compute=_spread_vs_rating_bucket,
    )
)
