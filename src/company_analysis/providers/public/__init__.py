"""Real data from free public sources: SEC EDGAR, daily share prices and ECB exchange rates.

Downloading (network, ``downloads``) is kept apart from reading (pure functions over the saved
files), so every load can be repeated from the same files and the tests never touch the network.
This provider is deliberately not offered by the main CLI: real data live in the isolated study
workspace (``company_analysis.study``), never in the main database.
"""

from company_analysis.providers.public.provider import PublicDataProvider, PublicDataResult

__all__ = ["PublicDataProvider", "PublicDataResult"]
