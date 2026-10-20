"""Last-twelve-months (LTM) flows and period-end balances from one issuer's reported facts."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from company_analysis.figures import Figure, Status
from company_analysis.formatting import format_date
from company_analysis.models import FinancialFact, FinancialItem, FiscalPeriod
from company_analysis.normalization.fiscal import PERIOD_TOLERANCE, add_months

# The full year before an interim period may close several weeks away from "interim end minus N
# months": some companies report quarters of 12 and 16 weeks (a 36-week "9M" period). Fiscal years
# close twelve months apart, so a one-month window cannot pick the wrong year.
PREVIOUS_YEAR_TOLERANCE = timedelta(days=31)


@dataclass(frozen=True)
class ReferencePeriod:
    """The most recent reported period: fundamentals are measured at its closing date."""

    fiscal_period: FiscalPeriod
    period_end: date
    published_at: date

    @property
    def label(self) -> str:
        return f"{self.fiscal_period.value} cerrado el {format_date(self.period_end)}"


def _describe(fiscal_period: FiscalPeriod, period_end: date) -> str:
    return f"{fiscal_period.value} {format_date(period_end)}"


class IssuerFacts:
    """Latest version of each reported fact of one issuer, with period arithmetic."""

    def __init__(self, facts: Iterable[FinancialFact]) -> None:
        self._facts: dict[tuple[FiscalPeriod, date, FinancialItem], FinancialFact] = {}
        for fact in facts:
            key = (fact.fiscal_period, fact.period_end, fact.item)
            current = self._facts.get(key)
            if current is None or fact.published_at > current.published_at:
                self._facts[key] = fact

    def reference_period(self) -> ReferencePeriod | None:
        """Latest reported period (a full year wins over an interim period ending the same day)."""
        if not self._facts:
            return None
        period, end, _ = max(self._facts, key=lambda key: (key[1], key[0] is FiscalPeriod.FY))
        published = max(
            fact.published_at
            for (fiscal_period, period_end, _), fact in self._facts.items()
            if (fiscal_period, period_end) == (period, end)
        )
        return ReferencePeriod(period, end, published)

    def find(
        self,
        item: FinancialItem,
        fiscal_period: FiscalPeriod,
        period_end: date,
        tolerance: timedelta = PERIOD_TOLERANCE,
    ) -> FinancialFact | None:
        """Fact for a period, tolerating closing dates a few days apart."""
        candidates = [
            fact
            for (period, end, fact_item), fact in self._facts.items()
            if period is fiscal_period and fact_item is item and abs(end - period_end) <= tolerance
        ]
        return min(candidates, key=lambda fact: abs(fact.period_end - period_end), default=None)

    def ltm(
        self,
        item: FinancialItem,
        fiscal_period: FiscalPeriod,
        period_end: date,
        *,
        label: str | None = None,
    ) -> Figure:
        """Flow over the twelve months ending at ``period_end``.

        For a full year it is the reported value. For an interim period (cumulative since the
        start of the fiscal year): previous full year + current interim - same interim a year ago.
        """
        label = label or f"{item.label} LTM"
        if fiscal_period is FiscalPeriod.FY:
            parts = [(FiscalPeriod.FY, period_end, 1.0, PERIOD_TOLERANCE)]
        else:
            parts = [
                (
                    FiscalPeriod.FY,
                    add_months(period_end, -fiscal_period.months),
                    1.0,
                    PREVIOUS_YEAR_TOLERANCE,
                ),
                (fiscal_period, period_end, 1.0, PERIOD_TOLERANCE),
                (fiscal_period, add_months(period_end, -12), -1.0, PERIOD_TOLERANCE),
            ]
        total, missing = 0.0, []
        for period, end, sign, tolerance in parts:
            fact = self.find(item, period, end, tolerance)
            if fact is None:
                missing.append(_describe(period, end))
            else:
                total += sign * fact.value
        if missing:
            return Figure.unavailable(
                label, Status.MISSING, f"falta «{item.label}» de {', '.join(missing)}"
            )
        return Figure(label, total, detail=_describe(fiscal_period, period_end))

    def balance(self, item: FinancialItem, fiscal_period: FiscalPeriod, period_end: date) -> Figure:
        """Stock (balance sheet value or share count) at the close of a period."""
        fact = self.find(item, fiscal_period, period_end)
        if fact is None:
            return Figure.unavailable(
                item.label,
                Status.MISSING,
                f"falta «{item.label}» de {_describe(fiscal_period, period_end)}",
            )
        return Figure(item.label, fact.value, detail=_describe(fiscal_period, period_end))
