# py-wtk: a description of the project

*[Leer en español](DESCRIPCIÓN_es.md)*

## What it is

py-wtk is a small, free program for reading the
[English Wiktionary](https://en.wiktionary.org) without a web browser. You give it a word
or an expression in any language, and it shows the whole Wiktionary entry, cleanly
formatted, in the terminal or in a desktop window.

It is meant for people who look up words often: students and teachers of languages
(Latin, Greek, Spanish, English…), translators, philologists, and anyone who wants
Wiktionary's information without the clutter and the slowness of the web page.

Nicolas Vaughan (<nivaca@fastmail.com>, <n.vaughan@uniandes.edu.co>) made it in 2026.
Nicolas Vaughan is Associate Professor of Literature at the School of Arts and Humanities of the
Universidad de los Andes, Bogotá, Colombia.

## Three programs, one core

py-wtk comes in three forms, which share the same code underneath and the same settings:

| Program      | Kind                        | Good for                                       |
|--------------|-----------------------------|------------------------------------------------|
| `py-wtk`     | command line                | a quick look-up, scripts, JSON output for other programs |
| `py-wtk-tui` | full-screen terminal (curses) | reading long entries and browsing from word to word in the terminal |
| `py-wtk-gui` | desktop window (Tkinter)    | everyday use with the mouse, in light or dark mode |

Because the three programs turn an entry into text with the same code, an entry looks the
same, and contains the same things, in all of them.

## What it shows

Not only the definitions, but the full entry: etymology, pronunciation, definitions with
examples and dated quotations, usage notes, inflection tables (declensions and
conjugations, kept aligned), synonyms, derived and related terms, descendants,
translations, references and further reading.

A Wiktionary page usually has many languages. py-wtk shows all of them by default, but you
can choose only the ones you care about (`-l la`, or `-l la,es,it`), put some first, show
only some sections (`-o etymology`), hide others, or ask for a brief view with only the
definitions.

## Main features

- **Links that work.** A link to another entry opens it in the program, at the right
  language; other links (Wikipedia, appendices, other dictionaries) open in the browser.
  In the command line they are terminal hyperlinks.
- **Search and suggestions.** Search page titles; if a word does not exist, similar words
  are proposed. The window suggests words while you type.
- **Navigation.** A table of contents by language and section, find in the page, history
  with back and forward, double-click on any word to look it up (in the window).
- **Shared settings.** One `config.toml` file for the three programs, which can be edited
  from the command line, from a settings screen in the terminal interface, from a
  settings window in the GUI, or by hand.
- **Disk cache.** Downloaded pages are kept compressed for a day (configurable), so looking
  up the same word again is instant and does not load Wiktionary's servers.
- **Polite with Wiktionary.** When Wiktionary answers "Too Many Requests", the program
  waits and tries again by itself.
- **Machine-readable output.** `py-wtk --json` gives the entry as structured JSON.

## How it is built

- **Python 3.11 or later, and nothing else.** Only the standard library is used
  (`urllib`, `html.parser`, `textwrap`, `curses`, `tkinter`, `tomllib`): no packages to
  install with pip. The window needs Tkinter, which some Linux distributions ship
  separately.
- **Data source.** Pages are downloaded as HTML from the Wiktionary REST API and converted
  to text by the program itself. For big entries whose translations live in a separate
  page (such as *house/translations*), that page is downloaded too and the translations
  are put back in their place.
- **Organisation.** The package `pywtk/` is split into layers: downloading and cache
  (`api.py`), HTML parsing (`dom.py`), text and colours (`text.py`), languages and sections
  (`entry.py`), rendering an entry to text or JSON (`render.py`), settings (`config.py`,
  `settings.py`), what the three programs share (`common.py`), and one module for each
  interface (`cli.py`, `tui.py`, `gui.py`, with `gui_theme.py` and `gui_fonts.py`). In
  total, about 5,000 lines of Python.
- **Cross-platform.** It runs on Linux, macOS and Windows, and uses the usual settings and
  cache folders of each system.

## Distribution

- An **AppImage** for Linux, which carries its own Python: download, make it executable,
  run.
- A **zip** (or a clone of the repository) for any system with Python 3.11+, with three
  small launchers to link into the `PATH`.
- `py-wtk-install.py` adds the programs, with their icon, to the applications menu on
  Linux, the Start menu on Windows or `~/Applications` on macOS, without administrator
  rights.

The scripts in `tools/` make the zip and the AppImage, publish releases on GitHub and
Codeberg, take the screenshots of the README, and regenerate all the icons from one SVG.

## Status

The current version is **1.4** (see [NOTES.md](NOTES.md) for the changes of each version).
The interfaces of the programs are in English; the documentation is in English and Spanish.
Earlier versions of the project were called *py-wkt*; their settings are carried over
automatically.

## Licence and credits

py-wtk is free software under the [GNU General Public License](LICENSE), version 3 or
later. Copyright © 2026 Nicolas Vaughan.

The content of the entries comes from Wiktionary and its contributors, under the
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) licence; py-wtk only
displays it. py-wtk is not an official project of Wiktionary or of the Wikimedia
Foundation.

For installation and full usage instructions, see the [README](README.md).
