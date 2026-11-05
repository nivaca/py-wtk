# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Page structure: language sections, section names, filters and options."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .dom import Node, heading_of
from .text import clean_inline

PARTS_OF_SPEECH = {
    "adjective", "adverb", "affix", "ambiposition", "article", "circumfix",
    "circumposition", "classifier", "clitic", "combining form", "conjunction",
    "contraction", "counter", "determiner", "diacritical mark", "gerund",
    "han character", "hanzi", "idiom", "infix", "interfix", "interjection",
    "kanji", "letter", "noun", "number", "numeral", "participle", "particle",
    "phrase", "postposition", "prefix", "preposition", "prepositional phrase",
    "pronoun", "proper noun", "proverb", "punctuation mark", "romanization",
    "root", "suffix", "symbol", "syllable", "verb", "abbreviation", "acronym",
    "initialism", "adnominal", "predicative", "relative", "converb",
}

# Sections hidden in brief mode.
BRIEF_EXCLUDE = {
    "translations", "usage notes", "synonyms", "antonyms", "derived terms",
    "related terms", "descendants", "coordinate terms", "hyponyms", "hypernyms",
    "meronyms", "holonyms", "see also", "conjugation", "declension", "inflection",
    "collocations", "alternative forms", "anagrams", "references", "further reading",
}


@dataclass
class Language:
    name: str      # "Latin"
    code: str      # "la" (may be empty if the page gives none)
    section: Node  # the <section> under the language's h2

    def label(self) -> str:
        return f"{self.name} ({self.code})" if self.code else self.name


def norm_title(s: str) -> str:
    """'Etymology 2' -> 'etymology', 'Derived terms' -> 'derived terms'."""
    return re.sub(r"\s+\d+$", "", s.strip().lower())


def language_sections(root: Node) -> list[Language]:
    """One Language per h2 section of the page, in page order."""
    out = []
    for sec in root.iter():
        if sec.tag != "section":
            continue
        h = heading_of(sec)
        if h is None or h.tag != "h2":
            continue
        hw = sec.find(lambda n: "headword" in n.classes and n.attrs.get("lang"))
        out.append(Language(clean_inline(h.text()), hw.attrs["lang"] if hw else "", sec))
    return out


def parse_lang_spec(spec: str) -> list[str] | None:
    """'la, Spanish' -> ['la', 'spanish']; 'all' -> None (no filter)."""
    if spec.strip().lower() == "all":
        return None
    return [x.strip().lower() for x in spec.split(",") if x.strip()]


def _matches(lang: Language, wanted: str) -> bool:
    return lang.name.lower() == wanted or bool(lang.code) and lang.code.lower() == wanted


def select_languages(langs: list[Language], spec: str,
                     preferred: list[str] | tuple = ()) -> list[Language]:
    """Languages matching a spec of codes and/or names, or 'all'. Languages
    named in `preferred` (codes or names) come first, in that order."""
    wanted = parse_lang_spec(spec)
    chosen = list(langs) if wanted is None else \
        [l for l in langs if any(_matches(l, w) for w in wanted)]
    if preferred:
        pref = [p.strip().lower() for p in preferred if p.strip()]

        def rank(l: Language) -> int:
            return next((i for i, p in enumerate(pref) if _matches(l, p)), len(pref))
        chosen.sort(key=rank)  # stable: page order within the same rank
    return chosen


def available_languages(langs: list[Language]) -> str:
    return ", ".join(l.label() for l in langs)


def parse_section_list(s: str | None) -> set[str] | None:
    if not s:
        return None
    return {norm_title(x) for x in s.split(",") if x.strip()}


@dataclass
class Options:
    """What to show of an entry."""
    include: set[str] | None = None   # only these sections (None = all)
    exclude: set[str] = field(default_factory=set)
    show_quotes: bool = True
    show_tables: bool = True

    @classmethod
    def build(cls, only: str | None = None, exclude: str | None = None,
              brief: bool = False, base: "Options | None" = None) -> "Options":
        """From comma-separated section lists, as given on the command line,
        on top of `base` (e.g. the user's settings).
        'quotations'/'quotes' and 'tables' in `exclude` are pseudo-sections."""
        base = base or cls()
        inc = parse_section_list(only)
        exc = parse_section_list(exclude) or set()
        opts = cls(inc, exc | base.exclude,
                   show_quotes=base.show_quotes and not ({"quotations", "quotes"} & exc),
                   show_tables=base.show_tables and "tables" not in exc)
        if brief:
            opts.show_quotes = opts.show_tables = False
            opts.include = (opts.include or set()) | PARTS_OF_SPEECH
            opts.exclude |= BRIEF_EXCLUDE
        return opts

    @property
    def load_subpages(self) -> bool:
        """Whether to fetch 'WORD/translations' subpages."""
        return "translations" not in self.exclude
