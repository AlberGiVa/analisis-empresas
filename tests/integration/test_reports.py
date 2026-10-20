"""Fichas and ranking generated from a stored run."""

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from company_analysis.config import ScoreType
from company_analysis.reports import ReportError, RunView, build_run_view, write_reports
from company_analysis.reports.views import DISCLAIMER
from tests.integration.conftest import DemoDatabase


@pytest.fixture
def view(demo_conn: duckdb.DuckDBPyConnection, demo_database: DemoDatabase) -> RunView:
    return build_run_view(demo_conn, demo_database.run_ids[1])


def test_the_view_shows_both_angles_of_every_company(view: RunView) -> None:
    assert len(view.companies) == 20
    orbelia = view.company("ORBE")
    assert orbelia.equity.title == "Puntuación de renta variable"
    assert orbelia.credit.title == "Puntuación de crédito"
    pe = next(f for f in orbelia.equity.factors if f.metric.metric_id == "pe_ratio")
    assert pe.metric.status_label == "No significativo"
    assert pe.metric.detail is not None
    assert "es negativo" in pe.metric.detail
    assert any(alert.rule_label == "Apalancamiento elevado" for alert in orbelia.alerts)


def test_rankings_put_companies_without_score_last(view: RunView) -> None:
    ranking = view.ranking(ScoreType.EQUITY)
    values = [c.equity.value for c in ranking]
    shown = [v for v in values if v is not None]
    assert shown == sorted(shown, reverse=True)
    assert values[len(shown) :] == [None] * (len(values) - len(shown))
    assert ranking[-1].issuer_id == "SKRV"  # stale prices: coverage too low


def test_bonds_history_and_screens_are_described(view: RunView) -> None:
    gresham = view.company("GRSH")
    texts = {bond.rating_text: bond.comparison_text for bond in gresham.bonds}
    assert texts["Sin rating"].startswith("Sin dato")
    assert texts["AA- (SAMPLE)"].startswith("Sin comparables suficientes")
    pellingham = view.company("PELL")
    assert pellingham.history.years == ("2023", "2024", "2025")
    assert pellingham.history.periods[-1] == "FY 31/03/2026"
    assert {screen.name for screen in pellingham.screens} == {
        screen.name for screen in view.config.screens
    }


def test_reports_are_written_for_every_company(view: RunView, tmp_path: Path) -> None:
    files = write_reports(view, tmp_path)
    assert files.ranking_html.is_file()
    assert len(files.fichas) == 20
    ranking = pd.read_csv(files.ranking_csv, sep=";", decimal=",", encoding="utf-8-sig")
    assert len(ranking) == 20
    assert ranking["Puntuación renta variable"].dropna().between(0, 100).all()
    for path in (files.ranking_html, *files.fichas):
        html = path.read_text(encoding="utf-8")
        assert "None" not in html
        assert ">nan<" not in html
    ficha = (files.directory / "fichas" / "ORBE.html").read_text(encoding="utf-8")
    assert "Vista del accionista" in ficha
    assert "Vista del acreedor" in ficha
    assert DISCLAIMER in ficha


def test_unknown_runs_are_reported(demo_conn: duckdb.DuckDBPyConnection) -> None:
    with pytest.raises(ReportError, match="No existe"):
        build_run_view(demo_conn, "R-no-existe")
