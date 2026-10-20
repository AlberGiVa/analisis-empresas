"""Regenerate the synthetic sample data in ``data/sample`` (deterministic: same seed, same files).

Usage: uv run python scripts/generate_sample_data.py
"""

from company_analysis.providers.sample import write_bundle_csv
from company_analysis.providers.sample_generator import generate_sample_bundle
from company_analysis.settings import Settings


def main() -> None:
    directory = Settings().sample_data_dir
    bundle = generate_sample_bundle()
    for path in write_bundle_csv(bundle, directory):
        print(f"Escrito: {path}")
    counts = ", ".join(f"{name}={count}" for name, count in bundle.row_counts().items())
    print(f"Registros: {counts}")


if __name__ == "__main__":
    main()
