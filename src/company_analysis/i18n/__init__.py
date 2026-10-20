"""English version of the generated website.

The pages are generated in Spanish. The English version translates every text node of the HTML
(and the ``title``, ``alt``, ``aria-label`` and ``placeholder`` attributes) with a catalog
(``en.yaml``): exact phrases, and patterns for the phrases that carry figures, dates or names.
Figures change to the English notation (``1.234,5`` → ``1,234.5``, ``45 pb`` → ``45 bp``); dates
keep the day/month/year order.

A text the catalog does not know stays in Spanish and is reported, so a new message never stops a
build; the tests check that everything the site shows today is in the catalog. Scripts, styles and
elements marked ``translate="no"`` are never touched.
"""

import html
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path

import yaml

CATALOG = "en.yaml"
TRANSLATED_ATTRIBUTES = frozenset({"title", "alt", "aria-label", "placeholder"})
UNTOUCHED_ELEMENTS = frozenset({"script", "style"})
VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
# Spanish notation: thousands with "." and decimals with ","; never part of a code or a date.
NUMBER = re.compile(r"(?<![\w.,/])(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+)(?!\d|[.,]\d|/)")
BASIS_POINTS = re.compile(r"(\d) pb\b")
SPANISH_WORD = re.compile(r"[a-záéíóúüñ]{2,}")
MAX_DEPTH = 40  # patterns inside patterns (a list of n items needs n levels)


class CatalogError(Exception):
    """The catalog file is not valid (the message says where)."""


@dataclass(frozen=True)
class Pattern:
    regex: re.Pattern[str]
    template: str  # str.format() with the named groups of the regex


@dataclass(frozen=True)
class Catalog:
    exact: dict[str, str]
    patterns: tuple[Pattern, ...]


def normalize(text: str) -> str:
    return " ".join(text.split())


def english_numbers(text: str) -> str:
    """``1.234,5`` → ``1,234.5`` and ``45 pb`` → ``45 bp``; everything else as it is."""
    swapped = NUMBER.sub(lambda m: m.group().translate(str.maketrans(".,", ",.")), text)
    return BASIS_POINTS.sub(r"\1 bp", swapped)


def load_catalog(path: Path | None = None) -> Catalog:
    """The catalog: ``exact`` (Spanish → English) and ``patterns`` (``es`` regex → ``en``)."""
    source = (
        path.read_text(encoding="utf-8")
        if path
        else (files(__package__) / CATALOG).read_text(encoding="utf-8")
    )
    name = path.name if path else CATALOG
    raw = yaml.safe_load(source) or {}
    if not isinstance(raw, dict):
        raise CatalogError(f"{name}: debe tener las claves 'exact' y 'patterns'.")
    exact_raw = raw.get("exact") or {}
    if not isinstance(exact_raw, dict):
        raise CatalogError(f"{name}: 'exact' debe ser un diccionario español → inglés.")
    exact: dict[str, str] = {}
    for spanish, english in exact_raw.items():
        if not isinstance(spanish, str) or not isinstance(english, str):
            raise CatalogError(f"{name}: entrada exacta no válida: {spanish!r}.")
        exact[normalize(spanish)] = english
    patterns = []
    for number, item in enumerate(raw.get("patterns") or [], start=1):
        if not isinstance(item, dict) or not isinstance(item.get("es"), str):
            raise CatalogError(f"{name}, patrón {number}: hacen falta 'es' y 'en'.")
        try:
            regex = re.compile(item["es"])
        except re.error as error:
            raise CatalogError(f"{name}, patrón {number}: expresión no válida: {error}.") from error
        template = item.get("en")
        if not isinstance(template, str):
            raise CatalogError(f"{name}, patrón {number}: falta 'en'.")
        fields = set(re.findall(r"{(\w+)}", template))
        if not fields <= set(regex.groupindex):
            missing = ", ".join(sorted(fields - set(regex.groupindex)))
            raise CatalogError(
                f"{name}, patrón {number}: el inglés usa grupos que no existen: {missing}."
            )
        patterns.append(Pattern(regex, template))
    return Catalog(exact, tuple(patterns))


@dataclass
class Translator:
    """Spanish → English with a catalog; remembers what it could not translate."""

    catalog: Catalog
    keep: set[str] = field(default_factory=set)  # proper names shown as they are
    missing: set[str] = field(default_factory=set)

    def extend(self, pairs: Iterable[tuple[str, str]]) -> None:
        """More exact translations (for example, the news written in both languages)."""
        for spanish, english in pairs:
            self.catalog.exact[normalize(spanish)] = english

    def phrase(self, text: str, depth: int = 0) -> str | None:
        """Translation of a whole phrase, or None if the catalog does not know it."""
        core = normalize(text)
        if not core or core in self.keep:
            return core
        if core in self.catalog.exact:
            return self.catalog.exact[core]
        if depth < MAX_DEPTH:
            for pattern in self.catalog.patterns:
                match = pattern.regex.fullmatch(core)
                if match is None:
                    continue
                parts = {
                    key: self._part(value or "", depth + 1)
                    for key, value in match.groupdict().items()
                }
                return pattern.template.format(**parts)
        if not SPANISH_WORD.search(english_numbers(core)):
            return english_numbers(core)  # figures, codes and units only
        return None

    def _part(self, value: str, depth: int) -> str:
        translated = self.phrase(value, depth)
        if translated is not None:
            return translated
        self.missing.add(normalize(value))  # a piece of a known phrase, still in Spanish
        return english_numbers(value)

    def text(self, raw: str) -> str:
        """A text node: translated with its surrounding spaces, or as it was (and reported)."""
        core = normalize(raw)
        if not core:
            return raw
        translated = self.phrase(core)
        if translated is None:
            self.missing.add(core)
            return raw
        start = raw[: len(raw) - len(raw.lstrip())]
        end = raw[len(raw.rstrip()) :]
        return f"{start}{translated}{end}"

    def document(self, source: str) -> str:
        """An HTML page in English (``lang="en"``)."""
        rewriter = _Rewriter(self.text)
        rewriter.feed(source)
        rewriter.close()
        return "".join(rewriter.out)


class _Rewriter(HTMLParser):
    """Copies the document, translating text nodes and a few attributes."""

    def __init__(self, translate: Callable[[str], str]) -> None:
        super().__init__(convert_charrefs=True)
        self.translate = translate
        self.out: list[str] = []
        self.stack: list[tuple[str, bool]] = []  # open elements and whether to leave them alone

    @property
    def frozen(self) -> bool:
        return bool(self.stack) and self.stack[-1][1]

    def _tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        raw = self.get_starttag_text() or ""
        frozen = self.frozen or dict(attrs).get("translate") == "no"
        changes = tag == "html" or (
            not frozen and any(name in TRANSLATED_ATTRIBUTES and value for name, value in attrs)
        )
        if not changes:
            return raw
        rebuilt = []
        for name, value in attrs:
            if value is None:
                rebuilt.append(f" {name}")
                continue
            text = value
            if tag == "html" and name == "lang":
                text = "en"
            elif name in TRANSLATED_ATTRIBUTES and not frozen:
                text = self.translate(value)
            rebuilt.append(f' {name}="{html.escape(text, quote=True)}"')
        closing = "/>" if raw.rstrip().endswith("/>") else ">"
        return f"<{tag}{''.join(rebuilt)}{closing}"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.out.append(self._tag(tag, attrs))
        if tag not in VOID_ELEMENTS:
            frozen = (
                self.frozen or tag in UNTOUCHED_ELEMENTS or dict(attrs).get("translate") == "no"
            )
            self.stack.append((tag, frozen))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.out.append(self._tag(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        self.out.append(f"</{tag}>")
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1][0] in UNTOUCHED_ELEMENTS:
            self.out.append(data)  # script and style content is raw text
        elif self.frozen:
            self.out.append(html.escape(data, quote=False))
        else:
            self.out.append(html.escape(self.translate(data), quote=False))

    def handle_comment(self, data: str) -> None:
        self.out.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.out.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self.out.append(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self.out.append(f"<![{data}]>")


def untranslated_report(missing: Iterable[str]) -> str:
    """The texts left in Spanish, one per line (to complete the catalog)."""
    return "".join(f"{text}\n" for text in sorted(set(missing)))


__all__ = [
    "Catalog",
    "CatalogError",
    "Pattern",
    "Translator",
    "english_numbers",
    "load_catalog",
    "normalize",
    "untranslated_report",
]
