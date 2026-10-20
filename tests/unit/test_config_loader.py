from pathlib import Path

import pytest

from company_analysis.config_loader import ConfigError, load_config, parse_config
from company_analysis.settings import PROJECT_ROOT

PROJECT_CONFIG = PROJECT_ROOT / "config" / "analysis.yaml"

MINIMAL = """
version: prueba
scoring:
  min_peers: 2
  equity:
    name: Acciones
    min_coverage: 0.5
    min_factors: 1
    factors: [{metric: pe_ratio, weight: 1}]
  credit:
    name: Crédito
    min_coverage: 0.5
    min_factors: 1
    factors: [{metric: net_debt_to_ebitda, weight: 1}]
"""


def test_the_project_configuration_is_valid() -> None:
    loaded = load_config(PROJECT_CONFIG)
    equity = {factor.metric for factor in loaded.config.scoring.equity.factors}
    assert equity == {
        "pe_ratio",
        "ev_to_ebitda",
        "fcf_yield",
        "roe",
        "roic",
        "ebitda_margin",
        "revenue_growth",
    }
    assert len(loaded.content_hash) == 64
    assert loaded.text == PROJECT_CONFIG.read_text(encoding="utf-8")


def test_comments_and_spacing_do_not_change_the_hash_but_values_do() -> None:
    base = parse_config(MINIMAL)
    reformatted = parse_config("# comentario\n" + MINIMAL.replace("min_peers: 2", "min_peers:   2"))
    changed = parse_config(MINIMAL.replace("min_peers: 2", "min_peers: 3"))
    assert reformatted.content_hash == base.content_hash
    assert changed.content_hash != base.content_hash


def test_defaults_fill_the_optional_sections() -> None:
    config = parse_config(MINIMAL).config
    assert config.normalization.max_price_age_days == 10
    assert config.alerts.leverage.max_net_debt_to_ebitda == 3.5
    assert config.screens == ()


def test_unknown_metrics_are_rejected() -> None:
    with pytest.raises(ConfigError, match="no existen: per_inventado"):
        parse_config(MINIMAL.replace("pe_ratio", "per_inventado"))


def test_informative_magnitudes_cannot_be_score_factors() -> None:
    with pytest.raises(ConfigError, match="magnitudes informativas"):
        parse_config(MINIMAL.replace("pe_ratio", "market_cap_eur"))


def test_invalid_values_are_reported() -> None:
    with pytest.raises(ConfigError, match="no es válida"):
        parse_config(MINIMAL.replace("min_coverage: 0.5", "min_coverage: 1.5", 1))
    with pytest.raises(ConfigError, match="repetidos"):
        parse_config(
            MINIMAL.replace(
                "[{metric: pe_ratio, weight: 1}]",
                "[{metric: pe_ratio, weight: 1}, {metric: pe_ratio, weight: 2}]",
            )
        )


def test_invalid_yaml_and_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="YAML"):
        parse_config("version: [sin cerrar")
    with pytest.raises(ConfigError, match="No se encuentra"):
        load_config(tmp_path / "no-existe.yaml")
