"""Streamlit panel: ranking with filters and the detail of each company. It only reads.

Each query opens a short read-only connection, so the command line can keep writing to the
database (DuckDB allows a single writer). Texts are in Spanish (user interface).
"""

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from company_analysis.config import ScoreType
from company_analysis.formatting import format_date
from company_analysis.reports import CompanyView, ReportError, RunView, ScoreView, build_run_view
from company_analysis.screening import ScreenOutcome
from company_analysis.settings import Settings
from company_analysis.storage import open_database
from company_analysis.storage.runs import RunRecord, RunStatus, list_runs


@st.cache_data(show_spinner=False)
def completed_runs(db_path: str, modified: float) -> list[RunRecord]:
    """Completed runs, most recent analysis first (``modified`` refreshes the cache)."""
    with open_database(Path(db_path), read_only=True) as conn:
        runs = [run for run in list_runs(conn) if run.status is RunStatus.COMPLETED]
    return sorted(runs, key=lambda run: (run.as_of_date, run.started_at), reverse=True)


@st.cache_data(show_spinner="Leyendo la ejecución…")
def run_view(db_path: str, run_id: str, modified: float) -> RunView:
    with open_database(Path(db_path), read_only=True) as conn:
        return build_run_view(conn, run_id)


def score_of(company: CompanyView, score_type: ScoreType) -> ScoreView:
    return company.equity if score_type is ScoreType.EQUITY else company.credit


def ranking_table(companies: list[CompanyView]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Empresa": company.name,
                "Id.": company.issuer_id,
                "Sector": company.sector_label,
                "País": company.country,
                "Renta variable": company.equity.value,
                "Cobertura RV (%)": company.equity.coverage * 100,
                "Crédito": company.credit.value,
                "Cobertura crédito (%)": company.credit.coverage * 100,
                "Alertas": len(company.alerts),
            }
            for company in companies
        ]
    )


def show_ranking(view: RunView) -> None:
    st.sidebar.header("Filtros")
    sectors = sorted({c.sector_label for c in view.companies})
    countries = sorted({c.country for c in view.companies})
    chosen_sectors = st.sidebar.multiselect("Sector", sectors, default=sectors)
    chosen_countries = st.sidebar.multiselect("País", countries, default=countries)
    screen_names = [screen.name for screen in view.config.screens]
    required = st.sidebar.multiselect("Cumplen los filtros", screen_names)
    only_alerts = st.sidebar.checkbox("Solo empresas con alertas")
    order = st.sidebar.radio("Ordenar por", ["Renta variable", "Crédito"])
    score_type = ScoreType.EQUITY if order == "Renta variable" else ScoreType.CREDIT

    def visible(company: CompanyView) -> bool:
        passed = {s.name for s in company.screens if s.outcome is ScreenOutcome.PASS}
        return (
            company.sector_label in chosen_sectors
            and company.country in chosen_countries
            and set(required) <= passed
            and (bool(company.alerts) or not only_alerts)
        )

    companies = [c for c in view.ranking(score_type) if visible(c)]
    st.caption(
        f"{len(companies)} de {len(view.companies)} empresas. Las empresas sin puntuación "
        "aparecen al final; su motivo está en el detalle."
    )
    st.dataframe(
        ranking_table(companies),
        hide_index=True,
        width="stretch",
        column_config={
            "Renta variable": st.column_config.NumberColumn(format="%.0f"),
            "Crédito": st.column_config.NumberColumn(format="%.0f"),
            "Cobertura RV (%)": st.column_config.NumberColumn(format="%.0f"),
            "Cobertura crédito (%)": st.column_config.NumberColumn(format="%.0f"),
        },
    )
    alerts = [(c, a) for c in companies for a in c.alerts]
    if alerts:
        st.subheader(f"Alertas ({len(alerts)})")
        for company, alert in alerts:
            st.markdown(f"- **{company.name}** · {alert.rule_label}: {alert.message}")


def factors_table(score: ScoreView) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Factor": f.metric.name,
                "Valor": f.metric.value_text,
                "Estado": f.metric.status_label or "",
                "Comparado con": f.reference_text or "—",
                "Percentil": f.percentile_text or "—",
                "Peso": f.weight_text,
                "Aporta": f.contribution_text or "—",
                "Detalle": (f.metric.detail or "") if f.metric.status_label else "",
            }
            for f in score.factors
        ]
    )


def show_score(score: ScoreView) -> None:
    st.metric(score.title, score.value_text, help=score.reason)
    st.caption(f"Cobertura {score.coverage_text}" + (f" · {score.reason}" if score.reason else ""))
    st.dataframe(factors_table(score), hide_index=True, width="stretch")


def show_company(view: RunView) -> None:
    names = {c.issuer_id: f"{c.name} ({c.issuer_id})" for c in view.companies}
    issuer_id = st.selectbox("Empresa", list(names), format_func=names.__getitem__, key="empresa")
    company = view.company(issuer_id)
    st.subheader(company.name)
    st.caption(
        f"{company.sector_label} · {company.industry_label} · {company.country} · divisa de "
        f"reporte {company.currency} · {company.listing_text}"
    )
    st.caption(f"Cotización: {company.price_text} · Referencia: {company.reference_text}")
    equity_column, credit_column = st.columns(2)
    with equity_column:
        st.markdown("#### Vista del accionista")
        show_score(company.equity)
        st.dataframe(
            pd.DataFrame(
                [{"Magnitud": m.name, "Valor": m.value_text, "Estado": m.status_label or ""}
                 for m in company.magnitudes]
            ),
            hide_index=True,
            width="stretch",
        )  # fmt: skip
    with credit_column:
        st.markdown("#### Vista del acreedor")
        show_score(company.credit)
        if company.bonds:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "ISIN": b.isin,
                            "Prelación": b.seniority,
                            "Vencimiento": b.maturity_text,
                            "Rating": b.rating_text,
                            "Diferencial": b.spread_text,
                            "Frente a su tramo": b.comparison_text,
                        }
                        for b in company.bonds
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("La empresa no tiene bonos vivos.")
    st.markdown("#### Alertas")
    for alert in company.alerts:
        st.warning(f"{alert.rule_label}: {alert.message}")
    if not company.alerts:
        st.caption("Sin alertas en esta ejecución.")
    st.markdown("#### Filtros")
    for screen in company.screens:
        conditions = "; ".join(f"{c.description}: {c.detail}" for c in screen.conditions)
        st.markdown(f"- **{screen.name}**: {screen.outcome_label}. {conditions}")
    st.markdown(f"#### Histórico anual (millones de {company.history.currency})")
    rows = company.history.rows
    history = pd.DataFrame(
        {year: [values[i] for _, values in rows] for i, year in enumerate(company.history.years)},
        index=[label for label, _ in rows],
    )
    st.dataframe(history, width="stretch")
    st.markdown("#### Diario del analista")
    for note in company.notes:
        st.markdown(f"**{note.date_text} · {note.author}** · {note.decision_label}")
        st.text(note.text)
    if not company.notes:
        st.caption(f'Sin notas. Añade una con: .\\analisis nota nueva {issuer_id} "texto"')


def main() -> None:
    st.set_page_config(page_title="Análisis de empresas", layout="wide")
    st.title("Análisis de empresas · Fondo multiactivos")
    settings = Settings()
    db_path = settings.db_path
    if not db_path.exists():
        st.info("Todavía no hay datos. En la carpeta del proyecto, ejecuta: .\\analisis demo")
        return
    modified = db_path.stat().st_mtime
    try:
        runs = completed_runs(str(db_path), modified)
        if not runs:
            st.info("Todavía no hay ejecuciones. Ejecuta: .\\analisis ejecutar")
            return
        labels = {run.run_id: f"{format_date(run.as_of_date)} · {run.run_id}" for run in runs}
        run_id = st.sidebar.selectbox(
            "Ejecución", list(labels), format_func=labels.__getitem__, key="ejecucion"
        )
        view = run_view(str(db_path), run_id, modified)
    except duckdb.IOException:
        st.error(
            "La base de datos está ocupada por otro proceso. Vuelve a intentarlo en unos segundos."
        )
        return
    except ReportError as error:
        st.error(str(error))
        return
    record = view.record
    st.caption(
        f"Análisis a {format_date(record.as_of_date)} · configuración {record.config_version} · "
        f"{len(view.companies)} empresas"
    )
    ranking_tab, detail_tab = st.tabs(["Ranking", "Empresa"])
    with ranking_tab:
        show_ranking(view)
    with detail_tab:
        show_company(view)
    st.info(view.disclaimer)


main()
