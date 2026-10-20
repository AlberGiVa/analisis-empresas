"""Allow ``python -m company_analysis`` (equivalent to the ``analisis`` command)."""

from company_analysis.cli import app

app(prog_name="analisis")
