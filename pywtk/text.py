# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Text cleanup and terminal display width."""

from __future__ import annotations

import re
import unicodedata

#  SGR codes and OSC 8 hyperlinks ("\033]8;;URL\033\\" opens one, an empty
#  URL closes it): group 1 is the SGR codes, group 2 the URL
ESC_RE = re.compile(r"\033\[([0-9;]*)m|\033\]8;[^;\033\a]*;([^\033\a]*)(?:\033\\|\a)")
_ZERO_WIDTH = "​‌‍‎‏"


def clean_inline(s: str) -> str:
    """Normalise whitespace and spacing around punctuation in extracted text."""
    s = s.replace(" ", " ").replace("‎", "").replace("‏", "")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\( +", "(", s)
    s = re.sub(r" +([),.;:!?])", r"\1", s)
    s = re.sub(r"\[ +", "[", s)
    s = re.sub(r" +\]", "]", s)
    return s.strip()


def strip_ansi(s: str) -> str:
    """S without its colour codes and hyperlinks."""
    return ESC_RE.sub("", s)


def char_width(ch: str) -> int:
    """Terminal columns taken by one character (0, 1 or 2)."""
    if unicodedata.combining(ch) or ch in _ZERO_WIDTH:
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(s: str) -> int:
    """Terminal columns taken by a string, ignoring ANSI colour codes."""
    return sum(char_width(c) for c in strip_ansi(s))


def styled_segments(line: str) -> list[tuple[str, tuple[int, ...], str | None]]:
    """Split a line with ANSI SGR codes and OSC 8 hyperlinks into (text,
    active codes, link URL or None) runs, e.g. '\\033[1;36mLatin\\033[0m x'
    -> [('Latin', (1, 36), None), (' x', (), None)].  Front ends map the
    codes to their own attributes (curses, Tk tags)."""
    out: list[tuple[str, tuple[int, ...], str | None]] = []
    active: list[int] = []
    url: str | None = None
    pos = 0
    for m in ESC_RE.finditer(line):
        if m.start() > pos:
            out.append((line[pos:m.start()], tuple(active), url))
        if m.group(1) is None:
            url = m.group(2) or None
        else:
            codes = [int(x) for x in m.group(1).split(";") if x] or [0]
            active = [] if codes == [0] else active + [c for c in codes if c not in active]
        pos = m.end()
    if pos < len(line):
        out.append((line[pos:], tuple(active), url))
    return out

