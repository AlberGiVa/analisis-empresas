from company_analysis.config import ConditionConfig, ScreenConfig
from company_analysis.figures import Status
from company_analysis.metrics import EntityLevel, MetricResult, MetricRow, MetricTable
from company_analysis.models import Industry, Sector
from company_analysis.screening import ScreenOutcome, evaluate_screens
from tests import factories
from tests.snapshots import snapshot

LEVERAGE = ScreenConfig(
    id="apalancamiento",
    name="Apalancamiento moderado",
    conditions=(
        ConditionConfig(metric="net_debt_to_ebitda", operator="<=", value=2.5),
        ConditionConfig(metric="interest_coverage", operator=">=", value=5.0),
    ),
)


def table(values: dict[tuple[str, str], float | Status]) -> MetricTable:
    rows = [
        MetricRow(
            metric_id,
            issuer_id,
            EntityLevel.ISSUER,
            issuer_id,
            MetricResult.unavailable(value, "falta el dato")
            if isinstance(value, Status)
            else MetricResult.computed(value, {}),
        )
        for (issuer_id, metric_id), value in values.items()
    ]
    return MetricTable(rows)


def test_pass_fail_and_indeterminate() -> None:
    companies = [snapshot(issuer=factories.issuer(i)) for i in ("PASA", "FALLA", "DUDA")]
    metrics = table(
        {
            ("PASA", "net_debt_to_ebitda"): 2.0,
            ("PASA", "interest_coverage"): 6.0,
            ("FALLA", "net_debt_to_ebitda"): 3.0,
            ("FALLA", "interest_coverage"): 6.0,
            ("DUDA", "net_debt_to_ebitda"): 2.0,
            ("DUDA", "interest_coverage"): Status.MISSING,
        }
    )
    results = {r.issuer_id: r for r in evaluate_screens(companies, metrics, [LEVERAGE])}
    assert results["PASA"].outcome is ScreenOutcome.PASS
    assert results["FALLA"].outcome is ScreenOutcome.FAIL
    assert results["DUDA"].outcome is ScreenOutcome.INDETERMINATE
    first = results["PASA"].conditions[0]
    assert first.description == "Deuda neta/EBITDA ≤ 2,5x"
    assert first.detail == "valor: 2,0x"
    assert results["DUDA"].conditions[1].detail == "Sin dato: falta el dato"


def test_a_failed_condition_wins_over_a_missing_one() -> None:
    company = [snapshot(issuer=factories.issuer("MIXTA"))]
    metrics = table(
        {("MIXTA", "net_debt_to_ebitda"): 4.0, ("MIXTA", "interest_coverage"): Status.MISSING}
    )
    (result,) = evaluate_screens(company, metrics, [LEVERAGE])
    assert result.outcome is ScreenOutcome.FAIL


def test_sector_filter() -> None:
    screen = ScreenConfig(id="tecnologia", name="Solo tecnología", sectors=(Sector.TECHNOLOGY,))
    companies = [
        snapshot(issuer=factories.issuer("SOFT", industry=Industry.SOFTWARE)),
        snapshot(issuer=factories.issuer("INDU", industry=Industry.CAPITAL_GOODS)),
    ]
    results = {r.issuer_id: r for r in evaluate_screens(companies, table({}), [screen])}
    assert results["SOFT"].outcome is ScreenOutcome.PASS
    assert results["INDU"].outcome is ScreenOutcome.FAIL
    assert results["INDU"].conditions[0].description == "Sector: Tecnología"
