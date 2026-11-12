How py-wtk was made
===================

*[Leer en español](DESCRIPCIÓN_es.md)*

py-wtk is a small program for reading the English Wiktionary
(<https://en.wiktionary.org>) without a web browser.  You give it a word
or an expression in any language, and it shows the whole Wiktionary
entry, cleanly formatted, in the terminal or in a desktop window.
Nicolas Vaughan made it in 2026.  Earlier versions were called *py-wkt*;
the current version is 1.8.  Here I explain how it was made, in six
stages.

It is meant for people who look up words often: students and teachers
of languages (Latin, Greek, Spanish, English ...), translators,
philologists, and anyone who wants the information of Wiktionary without
the clutter and the slowness of the web page.  py-wtk is free software,
under the GNU General Public License, version 3 or later.  The content
of the entries comes from Wiktionary and its contributors, under the
CC BY-SA 4.0 licence; py-wtk only displays it, and it is not an official
project of Wiktionary or of the Wikimedia Foundation.

Nicolas Vaughan is Associate Professor of Literature at the School of Arts
and Humanities of the Universidad de los Andes, Bogotá, Colombia.

1. From HTML to text
--------------------

Wiktionary gives each page in HTML through its REST API
(`/api/rest_v1/page/html/...`).  py-wtk downloads that HTML and converts
it to text by itself, with the standard library only: `urllib` for the
download, `html.parser` for reading the page into a small tree
(`dom.py`), and `textwrap` for the lines.  The page is then cut into its
languages and their sections (`entry.py`): etymology, pronunciation,
definitions with examples and dated quotations, usage notes, inflection
tables, synonyms, derived and related terms, descendants, translations,
references and further reading.

The inflection tables (declensions and conjugations) are kept aligned,
with the width that each character really takes in the terminal
(`text.py`).  The big entries, like *house*, keep their translations in a
separate page (`house/translations`); py-wtk downloads that page too and
puts the translations back in their place.

A page of Wiktionary usually has many languages.  py-wtk shows all of
them by default, but the user can choose only some (`-l la`, or
`-l la,es,it`), put some first, show only some sections
(`-o etymology`), hide others, or ask for a brief view with only the
definitions.

2. Three programs, one renderer
-------------------------------

py-wtk comes in three forms: a command line (`py-wtk`), a full-screen
terminal interface (`py-wtk-tui`, with `curses`), and a desktop window
(`py-wtk-gui`, with Tk, from the standard library).  All three turn an
entry into text with the same code (`render.py`), so an entry looks the
same, and contains the same things, in all of them.  The command line
can give the entry also as structured JSON (`--json`), for other
programs, and it has an interactive mode (`-i`) that asks for one word
after another.

The two full-screen programs add what is needed for reading long
entries: a table of contents by language and section, find in the page,
a history with Back and Forward, and reload.  The window has a light and
a dark look (`gui_theme.py`), adjustable fonts (`gui_fonts.py`), and
suggestions while you type; a double click on any word looks it up.  If
a word does not exist, similar words are proposed, and the titles of the
pages can be searched.

3. Settings and cache
---------------------

The three programs share one settings file, `config.toml`, in the usual
settings folder of each system (`~/.config/py-wtk/` in Linux).  It can
be edited from the command line (`--set`, `--unset`), from a settings
screen in the terminal interface, from a settings window in the GUI, or
by hand.  `settings.py` says, in one place, what each setting is, its
type and its default value.  The programs write in the file only the
settings that you change, over the file as it is in that moment, so if
the window and the terminal interface are open at the same time, one
does not undo the changes of the other.

The versions called *py-wkt* kept their settings in another folder,
first in a `settings.ini` and then in a `config.toml`.  py-wtk reads
them one time, takes them to the new folder and renames the old file
`*.old`.

The downloaded pages are kept compressed in the cache folder of the
system for one day (`general.cache_days`), so looking up the same word
again is instant and does not load the servers of Wiktionary.  When
Wiktionary answers "Too Many Requests" (or is busy for a moment), the
program waits, as long as the answer asks if it says so, and tries again
by itself.

4. Links
--------

In 1.2 the links of an entry started to work in the three programs.  A
link to another entry opens it in the program; the other links
(Wikipedia, the appendices of Wiktionary, other dictionaries) open in
the web browser.  Links to pages that do not exist yet, footnotes and
edit links are not clickable.

In the window the links have the colour of links and get underlined
under the mouse, and dragging over one selects the text without opening
it.  In the terminal interface they are blue, a click opens them, and
the key `L` lists the links on the screen, for opening one with the
keyboard.  In the command line they are terminal hyperlinks (OSC 8),
which most modern terminals and `less` make clickable; they are written
only with colours, so `--json`, `--no-color` and the output to other
programs do not change.

Two corrections came later.  In 1.5, a link to another entry opens it
at the top, with all the languages of the filter: before, it jumped to
the language of the link, and it seemed that the filter had changed.
In 1.6, a long entry opened in a pager other than `less` (for example
`PAGER=most`) showed its links as stray characters such as `^[]8;;`.
Only `less` can show these links, so with any other pager the entry is
now shown without them, keeping its colours.

5. Distribution
---------------

py-wtk needs Python 3.11 or later (for `tomllib`) and nothing else, so
it can be used from a zip or a clone of the repository, with three small
launchers to link into the `PATH`.  For Linux there is also an AppImage,
which carries its own Python: download, make it executable, run.  Since
1.7 there is an RPM for Fedora as well, on Copr and, signed, with the
releases: it uses the Python and Tk of the system, and puts the three
programs in the `PATH` and the applications menu.  The AppImage's Tk is
older (8.6) and ignores the scaling that the desktop gives to X11
programs (`Xft.dpi`), so on a scaled hi-res display its window came out
very small; since 1.7 the window reads that scaling itself.  A
small module, `version.py`, is read before the rest of the program, and
it stays readable by old versions of Python, so a Python too old gets a
clear message instead of an error.

`py-wtk-install.py` adds the programs, with their icon, to the
applications menu in Linux, the Start menu in Windows or
`~/Applications` in macOS, writing only in the folders of the user, so
no administrator rights are needed.  `--only-gui` adds only the window,
and `--uninstall` removes the entries and the icons that the installer
made, and nothing else.

The scripts in `tools/` make the zip and the AppImage, publish the
releases on GitHub and Codeberg (with the RPM, which `packaging/`
builds, and which goes to Copr too), take the screenshots of the README, and
make all the icons again from one SVG (since 1.8 the bracketed `pW`,
drawn with shapes rather than a font, on a teal tile).  The zip and the AppImage carry
the commit they were made from, which `--version` and *About* show.

6. One place for what is shared
-------------------------------

At first each program had its own copy of several things: the history
of Back and Forward, the handling of the links, the messages, the disk
cache, the common options.  In 1.4 they went to one module,
`common.py`, so the three programs say the same thing in the same way
("2 pages, 192.7 KB" everywhere, the same message for a language that
the page does not have, the same message for a network error).  The
entries are shown exactly as before.

The package `pywtk/` has now 16 modules, organised in layers:
downloading and cache (`api.py`), HTML parsing (`dom.py`), text and
colours (`text.py`), languages and sections (`entry.py`), rendering to
text or JSON (`render.py`), settings (`config.py`, `settings.py`), what
the three programs share (`common.py`), and one module for each
interface (`cli.py`, `tui.py`, `gui.py`, with `gui_theme.py` and
`gui_fonts.py`).  In total, around 5,200 lines of Python.

Testing
-------

The program was tested with Python 3.11 (the oldest it supports) and
with Python 3.15, in Linux.  `tools/screenshots.py` runs the three
programs as a user does (the window in light and dark mode), with
settings and a cache of their own, and the screenshots of the README
come from it; they were checked by eye, and in 1.6 they were taken
again.  There are not yet automated tests.

For installation and full usage instructions, see the
[README](../README.md); the changes of each version are in
[NOTES.md](NOTES.md).
