"""Smoke test of the Streamlit panel, run headless with Streamlit's testing tool (no browser)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from company_analysis.app import DASHBOARD
from tests.integration.conftest import DemoDatabase


def panel(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setenv("ANALYSIS_DB_PATH", str(db_path))
    app = AppTest.from_file(str(DASHBOARD), default_timeout=120)
    app.run()
    assert not app.exception, app.exception
    return app


def test_panel_shows_ranking_and_company_detail(
    demo_database: DemoDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = panel(demo_database.path, monkeypatch)
    ranking = app.dataframe[0].value
    assert len(ranking) == 20
    assert {"Empresa", "Renta variable", "Crédito", "Alertas"} <= set(ranking.columns)
    app.selectbox(key="empresa").set_value("ORBE").run()
    assert not app.exception
    assert any(header.value == "Orbelia Digital, S.A." for header in app.subheader)


def test_panel_filters_narrow_the_ranking(
    demo_database: DemoDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = panel(demo_database.path, monkeypatch)
    app.sidebar.checkbox[0].check().run()  # only companies with alerts
    assert not app.exception
    assert 0 < len(app.dataframe[0].value) < 20


def test_panel_without_database_explains_what_to_do(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = panel(tmp_path / "missing.duckdb", monkeypatch)
    assert any("analisis demo" in info.value for info in app.info)
