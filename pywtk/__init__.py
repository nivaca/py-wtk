# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""pywtk — look up words in the English Wiktionary.

Shared engine for the `py-wtk` command-line tool, the `py-wtk-tui`
terminal interface and the `py-wtk-gui` Tkinter window. Standard library only.

Modules:
    api     fetching pages and searching (with a caching Client)
    dom     a minimal HTML DOM built on html.parser
    text    text cleanup and terminal display width
    entry   page structure: languages, sections, filters and options
    config    reading and writing config.toml
    settings  the settings and their values (shared by the three programs)
    render  turning an entry into wrapped, styled text lines (and JSON)
    common  what the three programs share: arguments, messages, history,
            following links, the disk cache
    cli     the `py-wtk` command
    tui     the `py-wtk-tui` curses interface
    gui     the `py-wtk-gui` Tkinter interface
    gui_theme the light and dark look of the window
    gui_fonts the fonts of the window
"""

__version__ = "1.9"
