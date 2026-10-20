"""Allow ``python -m company_analysis`` (the command line interface)."""

import io
import sys

from company_analysis.cli import app

# When the output is redirected to a file or a pipe, Windows uses a legacy code page: replace
# the characters it cannot represent instead of failing.
for stream in (sys.stdout, sys.stderr):
    if isinstance(stream, io.TextIOWrapper):
        stream.reconfigure(errors="replace")

app(prog_name="analisis")
