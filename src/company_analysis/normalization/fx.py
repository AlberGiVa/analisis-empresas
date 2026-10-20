"""Exchange rates (units of each currency per euro) with point-in-time lookups."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta
from statistics import fmean

from company_analysis.figures import Figure, Status
from company_analysis.formatting import format_date
from company_analysis.models import BASE_CURRENCY, FxRate


class FxTable:
    """Rates by currency and date. A rate is valid for up to ``max_age_days`` after its date."""

    def __init__(self, rates: Iterable[FxRate], *, max_age_days: int) -> None:
        series: dict[str, list[tuple[date, float]]] = defaultdict(list)
        for rate in rates:
            series[rate.currency].append((rate.rate_date, rate.units_per_eur))
        self._dates: dict[str, list[date]] = {}
        self._values: dict[str, list[float]] = {}
        for currency, points in series.items():
            points.sort()
            self._dates[currency] = [day for day, _ in points]
            self._values[currency] = [value for _, value in points]
        self._max_age = timedelta(days=max_age_days)

    def rate(self, currency: str, day: date) -> Figure:
        """Units of ``currency`` per euro on ``day`` (latest rate not older than the limit)."""
        label = f"Tipo de cambio {currency}/EUR"
        if currency == BASE_CURRENCY:
            return Figure(label, 1.0)
        dates = self._dates.get(currency, [])
        index = bisect_right(dates, day) - 1
        if index < 0 or day - dates[index] > self._max_age:
            return Figure.unavailable(
                label,
                Status.MISSING,
                f"sin tipo de cambio entre el {format_date(day - self._max_age)} "
                f"y el {format_date(day)}",
            )
        return Figure(
            label, self._values[currency][index], detail=f"del {format_date(dates[index])}"
        )

    def average(self, currency: str, start: date, end: date) -> Figure:
        """Mean of the daily rates of ``currency`` between ``start`` and ``end`` (inclusive)."""
        label = f"Tipo de cambio medio {currency}/EUR"
        if currency == BASE_CURRENCY:
            return Figure(label, 1.0)
        dates = self._dates.get(currency, [])
        values = self._values.get(currency, [])[
            bisect_left(dates, start) : bisect_right(dates, end)
        ]
        period = f"del {format_date(start)} al {format_date(end)}"
        if not values:
            return Figure.unavailable(label, Status.MISSING, f"sin tipos de cambio {period}")
        return Figure(label, fmean(values), detail=f"media de {len(values)} días {period}")

    def cross(self, source: str, target: str, day: date) -> Figure:
        """Units of ``target`` per unit of ``source`` on ``day``."""
        label = f"Tipo de cambio {target}/{source}"
        if source == target:
            return Figure(label, 1.0)
        source_rate, target_rate = self.rate(source, day), self.rate(target, day)
        for rate in (source_rate, target_rate):
            if not rate.ok:
                return Figure.unavailable(label, rate.status, rate.explanation())
        return Figure(label, target_rate.number() / source_rate.number())
