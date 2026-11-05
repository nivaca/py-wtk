# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""What the three programs share above the engine: their common arguments,
their messages, the history of pages, the rendering of an entry with the
settings, following links and the disk cache."""

from __future__ import annotations

import argparse
import webbrowser
from typing import Generic, TypeVar

from .api import clear_disk_cache, disk_cache_usage, entry_target
from .entry import Language, Options, available_languages, select_languages
from .render import Loader, Rendered, Style, render_entry
from .settings import Settings, cache_dir


# --------------------------------------------------------------------------- #
# Arguments and messages
# --------------------------------------------------------------------------- #
def add_lookup_args(ap: argparse.ArgumentParser, word_help: str) -> None:
    """The arguments every program has: the word, and -l/--lang."""
    ap.add_argument("word", nargs="*", help=word_help)
    ap.add_argument("-l", "--lang",
                    help="comma-separated language codes/names, or 'all' "
                         "(default: setting general.languages)")


def plural(n: int, noun: str) -> str:
    """'1 page', '2 pages'."""
    return f"{n} {noun}{'' if n == 1 else 's'}"


def human_size(n: float) -> str:
    """'512 bytes', '3.4 KB', '1.2 MB'."""
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    raise AssertionError("unreachable")


def network_message(e: BaseException) -> str:
    return f"Network error: {getattr(e, 'reason', e)}"


def no_language_message(spec: str, languages: list[Language]) -> str:
    return f"No entry in “{spec}”. Available: {available_languages(languages)}."


def link_description(url: str) -> str:
    """Where a link leads, for status lines: '“rosa” (Latin)', or the URL
    of a link that opens in the browser."""
    target = entry_target(url)
    if target is None:
        return f"{url} (in the browser)"
    word, language = target
    return f"“{word}”" + (f" ({language})" if language else "")


def open_in_browser(url: str) -> str:
    """Opens URL in the web browser; returns what to tell the user."""
    try:
        webbrowser.open(url)
    except webbrowser.Error as e:
        return f"Could not open {url}: {e}"
    return f"Opened {url} in the browser."


# --------------------------------------------------------------------------- #
# The disk cache
# --------------------------------------------------------------------------- #
def cache_summary() -> str:
    """'12 pages, 3.4 MB'."""
    n, size = disk_cache_usage(cache_dir())
    return f"{plural(n, 'page')}, {human_size(size)}"


def clear_cache() -> str:
    """Empties the disk cache; returns what to tell the user."""
    n, size = clear_disk_cache(cache_dir())
    return f"Removed {plural(n, 'cached page')} ({human_size(size)})."


# --------------------------------------------------------------------------- #
# Rendering with the settings
# --------------------------------------------------------------------------- #
def render_languages(settings: Settings, word: str, languages: list[Language], spec: str,
                     width: int, options: Options, loader: Loader | None) -> Rendered:
    """The languages of SPEC of a page (the preferred ones first), rendered
    with colours for the TUI and the window."""
    chosen = select_languages(languages, spec, settings["general.preferred_languages"])
    return render_entry(word, chosen, Style(True), width, options, loader)


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
Place = TypeVar("Place")   # what a program remembers of a page: (word, position)


class History(Generic[Place]):
    """The pages visited before and after the one shown (Back and Forward)."""

    def __init__(self):
        self.past: list[Place] = []
        self.future: list[Place] = []

    def visit(self, here: Place) -> None:
        """Leaving HERE for a new page."""
        self.past.append(here)
        self.future.clear()

    def back(self, here: Place | None) -> Place | None:
        """The page before (None if there is none), leaving HERE."""
        return self._move(self.past, self.future, here)

    def forward(self, here: Place | None) -> Place | None:
        """The page after (None if there is none), leaving HERE."""
        return self._move(self.future, self.past, here)

    @staticmethod
    def _move(source: list, other: list, here) -> Place | None:
        if not source:
            return None
        if here is not None:
            other.append(here)
        return source.pop()
