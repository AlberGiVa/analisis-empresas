from datetime import date

from company_analysis.config import ScoreType
from company_analysis.figures import Figure, Status
from company_analysis.metrics import EntityLevel, MetricResult, MetricRow, MetricTable
from company_analysis.models import FinancialItem as Item
from company_analysis.normalization import BondSnapshot, CompanySnapshot
from company_analysis.scoring import Score, ScoreComponent
from company_analysis.screening import AlertRule, PreviousScores
from company_analysis.screening.alerts import high_leverage, rating_downgrades, score_changes
from tests import factories
from tests.snapshots import snapshot

AS_OF = date(2026, 6, 30)
BOND = factories.bond(issued=date(2020, 1, 15), maturity=date(2032, 1, 15))


def company_with_bond() -> CompanySnapshot:
    spread = Figure("Diferencial (pb)", 250.0)
    return snapshot(bonds=(BondSnapshot(BOND, None, spread, None),))


def test_downgrade_within_the_lookback_window() -> None:
    ratings = [
        factories.rating(BOND.isin, "BBB-", date(2020, 1, 15)),
        factories.rating(BOND.isin, "BB+", date(2026, 3, 12)),
    ]
    (alert,) = rating_downgrades([company_with_bond()], ratings, AS_OF, lookback_days=182)
    assert alert.rule is AlertRule.RATING_DOWNGRADE
    assert alert.entity_id == BOND.isin
    assert "de BBB- a BB+" in alert.message
    assert "pasa de grado de inversión a high yield" in alert.message


def test_old_downgrades_and_upgrades_do_not_alert() -> None:
    old = [
        factories.rating(BOND.isin, "BBB", date(2020, 1, 15)),
        factories.rating(BOND.isin, "BBB-", date(2025, 1, 10)),
    ]
    upgrade = [
        factories.rating(BOND.isin, "BBB", date(2020, 1, 15)),
        factories.rating(BOND.isin, "BBB+", date(2026, 5, 1)),
    ]
    company = [company_with_bond()]
    assert rating_downgrades(company, old, AS_OF, lookback_days=182) == []
    assert rating_downgrades(company, upgrade, AS_OF, lookback_days=182) == []


def leverage_table(result: MetricResult) -> MetricTable:
    return MetricTable(
        [MetricRow("net_debt_to_ebitda", "TEST", EntityLevel.ISSUER, "TEST", result)]
    )


def test_leverage_above_the_threshold() -> None:
    (alert,) = high_leverage([snapshot()], leverage_table(MetricResult.computed(4.1, {})), 3.5)
    assert alert.rule is AlertRule.LEVERAGE
    assert alert.message == "Deuda neta/EBITDA de 4,1x, por encima del umbral de 3,5x"
    assert high_leverage([snapshot()], leverage_table(MetricResult.computed(3.0, {})), 3.5) == []


def test_negative_ebitda_with_net_debt_is_always_an_alert() -> None:
    company = snapshot(
        stocks={Item.TOTAL_DEBT: 500.0, Item.CASH: 100.0}, flows={Item.EBITDA: -10.0}
    )
    not_meaningful = MetricResult.unavailable(Status.NOT_MEANINGFUL, "EBITDA LTM es negativo")
    (alert,) = high_leverage([company], leverage_table(not_meaningful), 3.5)
    assert alert.message.startswith("EBITDA negativo (-10,0 M EUR) con deuda neta positiva")
    net_cash = snapshot(stocks={Item.TOTAL_DEBT: 0.0, Item.CASH: 100.0}, flows={Item.EBITDA: -10.0})
    assert high_leverage([net_cash], leverage_table(not_meaningful), 3.5) == []


def test_not_applicable_leverage_does_not_alert() -> None:
    result = MetricResult.unavailable(Status.NOT_APPLICABLE, "banco")
    assert high_leverage([snapshot()], leverage_table(result), 3.5) == []


def score(issuer_id: str, value: float | None, pe: float = 0.0) -> Score:
    component = ScoreComponent("pe_ratio", 1.0, Status.OK, percentile=pe, contribution=pe)
    return Score(
        issuer_id,
        ScoreType.EQUITY,
        value,
        1.0,
        1,
        displayed=value is not None,
        reason=None if value is not None else "oculta",
        components=(component,),
    )


def previous(config_hash: str = "hash") -> PreviousScores:
    before = [score("CAE", 60.0, pe=60.0), score("ESTABLE", 55.0), score("OCULTA", 70.0)]
    return PreviousScores(
        "R-anterior",
        date(2025, 12, 31),
        config_hash,
        {(s.issuer_id, s.score_type): s for s in before},
    )


def test_large_score_changes_are_explained() -> None:
    now = [score("CAE", 40.0, pe=40.0), score("ESTABLE", 50.0), score("OCULTA", None)]
    (alert,) = score_changes(now, previous(), min_change=15, config_hash="hash")
    assert alert.issuer_id == "CAE"
    assert alert.message == (
        "Puntuación de renta variable: de 60 a 40 (-20 puntos) desde la ejecución a "
        "31/12/2025. Factores que más lo explican: PER (-20,0 puntos)"
    )


def test_score_change_warns_when_the_configuration_changed() -> None:
    now = [score("CAE", 40.0, pe=40.0)]
    (alert,) = score_changes(now, previous(config_hash="otro"), min_change=15, config_hash="hash")
    assert alert.message.endswith("la configuración ha cambiado entre ambas ejecuciones")
