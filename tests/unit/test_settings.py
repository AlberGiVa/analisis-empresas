from pathlib import Path

import pytest

from company_analysis.settings import PROJECT_ROOT, Settings, find_project_root


def test_project_root_is_the_folder_with_pyproject() -> None:
    assert (PROJECT_ROOT / "pyproject.toml").is_file()


def test_find_project_root_falls_back_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert find_project_root(tmp_path / "nested" / "file.py") == Path.cwd()


def test_default_paths_are_resolved_against_project_root() -> None:
    settings = Settings(_env_file=None)
    assert settings.db_path == PROJECT_ROOT / "data" / "analysis.duckdb"
    assert settings.output_dir == PROJECT_ROOT / "output"
    assert settings.config_path == PROJECT_ROOT / "config" / "analysis.yaml"
    assert settings.sample_data_dir == PROJECT_ROOT / "data" / "sample"


def test_environment_variables_override_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANALYSIS_DB_PATH", str(tmp_path / "custom.duckdb"))
    monkeypatch.setenv("ANALYSIS_OUTPUT_DIR", "relative/output")
    settings = Settings(_env_file=None)
    assert settings.db_path == tmp_path / "custom.duckdb"
    assert settings.output_dir == PROJECT_ROOT / "relative" / "output"


def test_relative_paths_follow_a_custom_project_root(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, project_root=tmp_path)
    assert settings.db_path == tmp_path / "data" / "analysis.duckdb"
