"""Daily share prices (Nasdaq, cross-checked with Yahoo Finance) and ECB exchange rates."""

import csv
import io
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

from company_analysis.models import EquityPrice, FxRate


def _amount(text: str) -> float:
    """ "$1,234.56" -> 1234.56."""
    return float(text.replace("$", "").replace(",", "").strip())


def nasdaq_prices(payload: Mapping[str, Any], *, isin: str, currency: str) -> list[EquityPrice]:
    """Closing prices from the Nasdaq historical quotes service."""
    data = payload.get("data") or {}
    rows = (data.get("tradesTable") or {}).get("rows") or []
    prices = []
    for row in rows:
        close = str(row.get("close", "")).strip()
        if not close or close in {"N/A", "--"}:
            continue
        day = datetime.strptime(row["date"], "%m/%d/%Y").date()  # noqa: DTZ007 (only the date)
        prices.append(
            EquityPrice(isin=isin, price_date=day, close=_amount(close), currency=currency)
        )
    return sorted(prices, key=lambda price: price.price_date)


def yahoo_closes(payload: Mapping[str, Any]) -> dict[date, float]:
    """Closing prices from Yahoo Finance, by trading day in the exchange's time zone."""
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return {}
    chart = result[0]
    offset = timedelta(seconds=int(chart.get("meta", {}).get("gmtoffset", 0)))
    closes = (chart.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    return {
        (datetime.fromtimestamp(stamp, UTC) + offset).date(): float(close)
        for stamp, close in zip(chart.get("timestamp") or [], closes, strict=False)
        if close is not None
    }


def yahoo_exchange(payload: Mapping[str, Any]) -> str | None:
    """Primary market as Yahoo names it (NYQ = NYSE, NMS = Nasdaq Global Select…)."""
    result = (payload.get("chart") or {}).get("result") or []
    return str(result[0].get("meta", {}).get("exchangeName")) if result else None


YAHOO_EXCHANGE_MIC = {"NYQ": "XNYS", "NMS": "XNAS", "NGM": "XNAS", "NCM": "XNAS", "ASE": "XASE"}


def ecb_rates(text: str) -> list[FxRate]:
    """Daily ECB reference rates (units of currency per euro) from the ECB data API in CSV."""
    rates = []
    for row in csv.DictReader(io.StringIO(text)):
        value = row.get("OBS_VALUE", "").strip()
        if not value:
            continue
        currency = row["KEY"].split(".")[2]  # EXR.D.USD.EUR.SP00.A
        rates.append(
            FxRate(
                currency=currency,
                rate_date=date.fromisoformat(row["TIME_PERIOD"]),
                units_per_eur=float(value),
            )
        )
    return sorted(rates, key=lambda rate: rate.rate_date)


def price_differences(
    prices: list[EquityPrice], reference: Mapping[date, float]
) -> tuple[int, float | None, date | None]:
    """Days compared and largest relative difference (and its date) against a second source."""
    compared, worst, worst_day = 0, None, None
    for price in prices:
        other = reference.get(price.price_date)
        if other is None or other <= 0:
            continue
        compared += 1
        difference = abs(price.close / other - 1)
        if worst is None or difference > worst:
            worst, worst_day = difference, price.price_date
    return compared, worst, worst_day
