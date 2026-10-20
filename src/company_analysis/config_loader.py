"""Loading of the methodology configuration from YAML, with its fingerprint for traceability."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from company_analysis.config import AnalysisConfig
from company_analysis.metrics import all_metrics


class ConfigError(Exception):
    """The configuration file is missing, is not valid YAML or does not pass validation."""


@dataclass(frozen=True)
class LoadedConfig:
    config: AnalysisConfig
    text: str  # the file as written (with its comments), stored with every run
    content_hash: str  # SHA-256 of the validated content: comments and spacing do not change it

    @property
    def version(self) -> str:
        return self.config.version


def config_hash(config: AnalysisConfig) -> str:
    return hashlib.sha256(config.model_dump_json().encode("utf-8")).hexdigest()


def parse_config(text: str, source: str = "configuración") -> LoadedConfig:
    """Validate a YAML text and check that every metric it mentions exists."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(f"{source} no es un YAML válido: {error}") from error
    try:
        config = AnalysisConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigError(f"{source} no es válida:\n{error}") from error
    metrics = {metric.metric_id: metric for metric in all_metrics()}
    unknown = sorted(config.referenced_metrics() - metrics.keys())
    if unknown:
        raise ConfigError(
            f"{source} usa métricas que no existen: {', '.join(unknown)}. "
            f"Disponibles: {', '.join(sorted(metrics))}"
        )
    factors = [
        f.metric for model in (config.scoring.equity, config.scoring.credit) for f in model.factors
    ]
    informative = sorted({m for m in factors if metrics[m].higher_is_better is None})
    if informative:
        raise ConfigError(
            f"{source}: {', '.join(informative)} son magnitudes informativas y no pueden ser "
            "factores de una puntuación"
        )
    return LoadedConfig(config=config, text=text, content_hash=config_hash(config))


def load_config(path: Path) -> LoadedConfig:
    if not path.is_file():
        raise ConfigError(f"No se encuentra el fichero de configuración {path}")
    return parse_config(path.read_text(encoding="utf-8"), source=str(path))
