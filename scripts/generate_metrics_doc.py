"""Regenerate docs/metricas.md from the metric registry.

Usage: uv run python scripts/generate_metrics_doc.py
"""

from company_analysis.metrics.documentation import render_metrics_markdown
from company_analysis.settings import PROJECT_ROOT


def main() -> None:
    path = PROJECT_ROOT / "docs" / "metricas.md"
    path.write_text(render_metrics_markdown(), encoding="utf-8", newline="\n")
    print(f"Escrito: {path}")


if __name__ == "__main__":
    main()
