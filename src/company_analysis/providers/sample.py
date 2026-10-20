"""Sample data provider: reads the synthetic CSV files of ``data/sample``.

Each CSV file holds one collection of :class:`~company_analysis.models.DataBundle`, with one
column per model field. Empty cells mean "no value" and are read as ``None``.
"""

import csv
from pathlib import Path
from typing import ClassVar

from company_analysis.models import (
    Bond,
    BondQuote,
    DataBundle,
    Equity,
    EquityPrice,
    FinancialFact,
    FxRate,
    Issuer,
    RatingAction,
)
from company_analysis.models.base import DomainModel
from company_analysis.providers.base import DataProvider

# Bundle collection -> (CSV file name, model of each row).
SAMPLE_FILES: dict[str, tuple[str, type[DomainModel]]] = {
    "issuers": ("issuers.csv", Issuer),
    "equities": ("equities.csv", Equity),
    "bonds": ("bonds.csv", Bond),
    "financial_facts": ("financials.csv", FinancialFact),
    "equity_prices": ("equity_prices.csv", EquityPrice),
    "bond_quotes": ("bond_quotes.csv", BondQuote),
    "ratings": ("ratings.csv", RatingAction),
    "fx_rates": ("fx_rates.csv", FxRate),
}


def _cell(value: object) -> str:
    return "" if value is None else str(value)


def write_bundle_csv(bundle: DataBundle, directory: Path) -> list[Path]:
    """Write every collection of ``bundle`` as a CSV file in ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for collection, (file_name, model) in SAMPLE_FILES.items():
        path = directory / file_name
        columns = list(model.model_fields)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(columns)
            for record in getattr(bundle, collection):
                row = record.model_dump(mode="json")
                writer.writerow([_cell(row[column]) for column in columns])
        written.append(path)
    return written


def read_bundle_csv(directory: Path) -> DataBundle:
    """Read the CSV files written by :func:`write_bundle_csv` into a validated bundle."""
    collections: dict[str, list[dict[str, str | None]]] = {}
    for collection, (file_name, _model) in SAMPLE_FILES.items():
        with (directory / file_name).open(encoding="utf-8", newline="") as handle:
            collections[collection] = [
                {key: (value if value != "" else None) for key, value in row.items()}
                for row in csv.DictReader(handle)
            ]
    return DataBundle.model_validate(collections)


class SampleProvider(DataProvider):
    """Provider backed by the synthetic sample data committed to the repository."""

    name: ClassVar[str] = "sample"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def fetch(self) -> DataBundle:
        return read_bundle_csv(self.directory)
