"""Translation of the generated pages into English (catalog, patterns, figures and HTML)."""

import re
from pathlib import Path

import pytest

from company_analysis.i18n import (
    Catalog,
    CatalogError,
    Pattern,
    Translator,
    english_numbers,
    load_catalog,
)


def translator(**exact: str) -> Translator:
    catalog = Catalog(
        exact={"Sin dato": "No data", "Apalancamiento elevado": "High leverage", **exact},
        patterns=(
            Pattern(
                re.compile(r"(?P<rule>.+): deuda neta/EBITDA de (?P<value>\S+)"),
                "{rule}: net debt/EBITDA of {value}",
            ),
        ),
    )
    return Translator(catalog, keep={"PepsiCo, Inc."})


@pytest.mark.parametrize(
    ("spanish", "english"),
    [
        ("37,7x", "37.7x"),
        ("16.091 M EUR", "16,091 M EUR"),
        ("1.234.567,25", "1,234,567.25"),
        ("−2.175,0 M USD", "−2,175.0 M USD"),
        ("5,2 %", "5.2 %"),
        ("+10 pb", "+10 bp"),
        ("20/10/2026", "20/10/2026"),  # dates keep their order
        ("2026.10-web-1", "2026.10-web-1"),  # codes are not figures
        ("US7134481081", "US7134481081"),
    ],
)
def test_figures_change_to_the_english_notation(spanish: str, english: str) -> None:
    assert english_numbers(spanish) == english


def test_exact_phrases_patterns_and_names() -> None:
    t = translator()
    assert t.phrase("  Sin   dato ") == "No data"
    assert t.phrase("Apalancamiento elevado: deuda neta/EBITDA de 3,8x") == (
        "High leverage: net debt/EBITDA of 3.8x"
    )
    assert t.phrase("PepsiCo, Inc.") == "PepsiCo, Inc."
    assert t.phrase("12,5 %") == "12.5 %"
    assert t.phrase("Una frase desconocida") is None
    assert t.missing == set()


def test_unknown_texts_stay_in_spanish_and_are_reported() -> None:
    t = translator()
    assert t.text("\n  Una frase desconocida  ") == "\n  Una frase desconocida  "
    assert t.phrase("Regla nueva: deuda neta/EBITDA de 4,0x") == (
        "Regla nueva: net debt/EBITDA of 4.0x"
    )
    assert t.missing == {"Una frase desconocida", "Regla nueva"}


def test_documents_keep_markup_scripts_and_untranslatable_parts() -> None:
    t = translator(**{"Hola": "Hello", "Ficha": "Sheet", "Ir": "Go"})
    source = (
        '<!doctype html><html lang="es"><head><title>Ficha</title>'
        '<script>var a = "Hola" < 3;</script></head><body>'
        '<p title="Sin dato">Hola <strong>Sin dato</strong> &amp; 3,5x</p>'
        '<a href="x.html" aria-label="Ir">Ir</a><span translate="no">Hola <b>Hola</b></span>'
        '<svg viewBox="0 0 10 10"><text>Hola</text><path d="M0 0"/></svg><br>Hola</body></html>'
    )
    result = t.document(source)
    assert result.startswith('<!doctype html><html lang="en"><head><title>Sheet</title>')
    assert '<script>var a = "Hola" < 3;</script>' in result
    assert '<p title="No data">Hello <strong>No data</strong> &amp; 3.5x</p>' in result
    assert '<a href="x.html" aria-label="Go">Go</a>' in result
    assert '<span translate="no">Hola <b>Hola</b></span>' in result
    assert '<svg viewBox="0 0 10 10"><text>Hello</text><path d="M0 0"/></svg><br>Hello' in result


def test_catalog_errors_say_what_is_wrong(tmp_path: Path) -> None:
    path = tmp_path / "en.yaml"
    path.write_text("exact: {}\npatterns:\n  - {es: '(?P<a>x)', en: '{b}'}\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="grupos que no existen: b"):
        load_catalog(path)
    path.write_text("exact: {}\npatterns:\n  - {es: '(', en: 'x'}\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="expresión no válida"):
        load_catalog(path)


def test_the_published_catalog_is_valid() -> None:
    catalog = load_catalog()
    assert catalog.exact
