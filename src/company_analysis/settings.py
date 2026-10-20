"""Runtime settings (paths and secrets) read from environment variables and the ``.env`` file.

The analysis methodology (factors, weights, thresholds) does not live here but in the versioned
YAML configuration, so that every run can record exactly which methodology it used.
"""

from pathlib import Path

from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_project_root(start: Path | None = None) -> Path:
    """Return the closest directory at or above ``start`` that contains ``pyproject.toml``.

    Falls back to the current working directory when the package is not inside a project checkout.
    """
    origin = (start or Path(__file__)).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return Path.cwd()


PROJECT_ROOT = find_project_root()


class Settings(BaseSettings):
    """Paths used by the tool. Relative paths are resolved against ``project_root``."""

    model_config = SettingsConfigDict(
        env_prefix="ANALYSIS_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: Path = PROJECT_ROOT
    db_path: Path = Path("data/analysis.duckdb")
    output_dir: Path = Path("output")
    config_path: Path = Path("config/analysis.yaml")
    sample_data_dir: Path = Path("data/sample")

    @field_validator("db_path", "output_dir", "config_path", "sample_data_dir")
    @classmethod
    def _resolve_against_root(cls, value: Path, info: ValidationInfo) -> Path:
        if value.is_absolute():
            return value
        root = info.data.get("project_root", PROJECT_ROOT)
        return Path(root) / value
