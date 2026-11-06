# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""py-wtk — look up words in the English Wiktionary from the command line.

Shows the full entry: etymology, pronunciation, definitions, usage examples,
quotations, inflection tables, synonyms, derived/related terms, descendants,
translations, references, and so on.

Examples:
    py-wtk house                 # full entry for "house" (all languages)
    py-wtk rosa -l la            # Latin entry only (code or name: -l Latin)
    py-wtk rosa -l en            # English only
    py-wtk rosa -b               # brief: definitions only
    py-wtk house -o etymology,pronunciation
    py-wtk house -x translations,quotations
    py-wtk -s recieve            # search for matching page titles
    py-wtk -i                    # ask for one word after another
    py-wtk house --json          # structured JSON output
    py-wtk --settings            # list the settings
    py-wtk --configure           # change the settings interactively
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

from .api import Client, NetworkError, NotFound, page_url, search, suggestions
from .common import add_lookup_args, cache_summary, clear_cache, network_message
from .dom import Node
from .entry import Options, available_languages, language_sections, select_languages
from .render import Style, entry_to_json, render_entry
from .settings import SECTION_TITLES, Settings, cache_dir
from .settings import lookup as find_setting
from .version import NAME, VERSION, describe, title

PROG = "py-wtk"


def term_width(max_width: int) -> int:
    return min(shutil.get_terminal_size((80, 24)).columns - 1, max_width)


#  An OSC 8 hyperlink marker (Style.link), ended by ST or BEL
OSC8_RE = re.compile(r"\033\]8;[^\033\a]*(?:\033\\|\a)")


def pager_shows_links(pager: str) -> bool:
    """Whether PAGER passes OSC 8 hyperlinks through: only less does (with
    -R); others, such as most and more, show them as stray characters."""
    try:
        words = shlex.split(pager)
    except ValueError:
        return False
    return bool(words) and os.path.basename(words[0]) == "less"


def page_output(text: str, mode: str, command: str = ""):
    """mode: 'auto' (page if it does not fit), 'always' or 'never'."""
    rows = shutil.get_terminal_size((80, 24)).lines
    if mode == "always" or (mode == "auto" and text.count("\n") + 1 > rows - 1):
        pager = command or os.environ.get("PAGER") or "less"
        if not pager_shows_links(pager):
            text = OSC8_RE.sub("", text)
        env = dict(os.environ)
        env.setdefault("LESS", "FRX")
        try:
            proc = subprocess.Popen(pager, shell=True, stdin=subprocess.PIPE, env=env)
            try:
                proc.communicate(text.encode("utf-8"))
            except BrokenPipeError:
                pass
            return
        except OSError:
            pass
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        pass


def warn(message: str) -> None:
    print(f"{PROG}: {message}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Settings commands
# --------------------------------------------------------------------------- #
def print_settings(st: Settings, style: Style):
    print(style.title(f"{NAME} {VERSION}: settings"))
    print(style.dim(f"# {st.path}" + ("" if st.path.exists() else " (not created yet: all defaults)")))
    for section, title in SECTION_TITLES.items():
        print()
        print(style.lang(title))
        for s in st.visible(section):
            value = s.format(st[s.name]) or '""'
            mark = "" if st.is_default(s.name) else style.h3("  (changed)")
            print(f"  {style.headword(s.name)} = {value}{mark}")
            print(style.dim(f"      {s.help} [{s.describe_range()}]"))
    print()
    print(style.dim(f"# Disk cache: {cache_dir()} — {cache_summary()}"))


def configure(st: Settings, style: Style) -> int:
    """Interactive settings editor on the terminal."""
    items = st.visible()
    print(style.title(f"{NAME} {VERSION}: settings"))
    print("Choose a number to change a setting. For a new value, press Enter to keep the\n"
          "current one, or type '-' to restore the default. Empty answer to the number: finish.")
    changed = False
    while True:
        print()
        section = None
        for i, s in enumerate(items, 1):
            if s.section != section:
                section = s.section
                print(style.lang(SECTION_TITLES[section]))
            value = s.format(st[s.name]) or '""'
            mark = "" if st.is_default(s.name) else " *"
            print(f"  {i:2}. {s.label}: {style.headword(value)}{mark}")
        try:
            ans = input("\nNumber (Enter to finish): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not ans:
            break
        if not ans.isdigit() or not 1 <= int(ans) <= len(items):
            print(f"Please type a number between 1 and {len(items)}.")
            continue
        s = items[int(ans) - 1]
        print(f"\n{style.headword(s.label)} ({s.name})\n  {s.help}\n"
              f"  Allowed: {s.describe_range()}. Default: {s.format(s.default) or '(empty)'}")
        if s.kind == "bool":
            st.set(s.name, not st[s.name])
            print(f"  → now {s.format(st[s.name])}")
            changed = True
            continue
        try:
            new = input(f"  New value [{s.format(st[s.name])}]: ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not new.strip():
            continue
        try:
            if new.strip() == "-":
                st.reset(s.name)
            else:
                st.set(s.name, new)
            changed = True
            print(f"  → now {s.format(st[s.name]) or '(empty)'}")
        except ValueError as e:
            print(f"  Not changed: {e}")
    if changed:
        st.save()
        print(f"Saved in {st.path}")
    else:
        print("Nothing changed.")
    return 0


def edit_settings(st: Settings) -> int:
    if not st.path.exists():
        st.write_all()  # write the documented file first
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    try:
        return subprocess.call(shlex.split(editor) + [str(st.path)])
    except OSError as e:
        print(f"Cannot start the editor '{editor}': {e}. The file is {st.path}", file=sys.stderr)
        return 1


def change_settings(st: Settings, sets: list[str], unsets: list[str]) -> int:
    try:
        for item in sets:
            if "=" not in item:
                raise ValueError(f"--set needs NAME=VALUE, got {item!r}")
            name, value = item.split("=", 1)
            s = find_setting(name.strip())
            st.set(s.name, value)
            print(f"{s.name} = {s.format(st[s.name])}")
        for name in unsets:
            s = find_setting(name.strip())
            st.reset(s.name)
            print(f"{s.name} = {s.format(st[s.name])} (default)")
    except (KeyError, ValueError) as e:
        warn(e.args[0] if e.args else str(e))
        return 2
    try:
        st.save()
    except OSError as e:
        warn(f"cannot save the settings: {e}")
        return 1
    return 0


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=PROG,
        description=f"{title()}, from the command line (full entries).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Languages may be given by Wiktionary code (en, la, es, grc) or name\n"
            "(Latin, 'Ancient Greek'). Section names for -o/-x are matched\n"
            "case-insensitively, ignoring numbers: etymology, pronunciation, noun,\n"
            "verb, synonyms, derived terms, translations, declension, conjugation,\n"
            "references, ...  The pseudo-section 'quotations' hides quotations,\n"
            "and 'tables' hides tables (e.g. inflection tables).\n\n"
            "Defaults for most options come from the settings file; see --settings."
        ),
    )
    add_lookup_args(ap, "word or phrase to look up")
    ap.add_argument("-o", "--only", metavar="SECTIONS",
                    help="show only these sections (comma-separated)")
    ap.add_argument("-x", "--exclude", metavar="SECTIONS",
                    help="hide these sections (comma-separated)")
    ap.add_argument("-b", "--brief", action="store_true",
                    help="definitions only (no etymology, quotations, tables, etc.)")
    ap.add_argument("-F", "--full", action="store_true",
                    help="full entry, even if the setting cli.brief is on")
    ap.add_argument("-s", "--search", action="store_true",
                    help="search for page titles instead of showing an entry")
    ap.add_argument("-n", "--limit", type=int, metavar="N",
                    help="number of search results (default: setting general.search_results)")
    ap.add_argument("-i", "--interactive", action="store_true",
                    help="then ask for more words, one per line, each with options if "
                         "need be (e.g. 'rosa -l la'); Ctrl-D or Ctrl-C ends")
    ap.add_argument("--json", action="store_true", help="print structured JSON")
    ap.add_argument("--no-color", action="store_true", help="disable colored output")
    ap.add_argument("--no-pager", action="store_true", help="do not use a pager")
    ap.add_argument("--refresh", action="store_true",
                    help="download the page again instead of using the disk cache")

    g = ap.add_argument_group("settings")
    g.add_argument("--settings", action="store_true",
                   help="list all settings with their values and exit")
    g.add_argument("--configure", action="store_true",
                   help="change the settings interactively")
    g.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                   help="change a setting, e.g. --set general.languages=la,en (repeatable)")
    g.add_argument("--unset", action="append", default=[], metavar="NAME",
                   help="restore a setting to its default (repeatable)")
    g.add_argument("--edit-settings", action="store_true",
                   help="open the settings file in $VISUAL / $EDITOR")
    g.add_argument("--clear-cache", action="store_true",
                   help="delete the pages kept in the disk cache")
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {describe()}")
    return ap


def interactive(argv: list[str], words: list[str]) -> int:
    """Look up WORDS (if any), then one line after another, each read like a
    command line; the options of ARGV apply to all of them."""
    try:
        import readline  # noqa: F401  (line editing and history in input())
    except ImportError:
        pass
    base = [a for a in argv if a not in ("-i", "--interactive")]
    for w in words:                     # (the options without the words)
        i = len(base) - 1 - base[::-1].index(w)
        del base[i]
    if words:
        lookup_line(base + words)
    else:
        print(f"{title()}\nType a word (options too, e.g. 'rosa -l la'); "
              "Ctrl-D or Ctrl-C to quit.")
    while True:
        try:
            line = input(f"{PROG}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as e:
            warn(str(e))
            continue
        lookup_line(base + [t for t in tokens if t not in ("-i", "--interactive")])


def lookup_line(argv: list[str]):
    """main(ARGV) for interactive: its errors (and --help) don't end it."""
    try:
        main(argv)
    except SystemExit:
        pass
    except KeyboardInterrupt:
        print()


def main(argv=None) -> int:
    ap = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    args = ap.parse_args(argv)
    if args.interactive:
        return interactive(argv, args.word)
    st = Settings()
    for p in st.problems:
        warn(f"warning: {p}")
    for m in st.messages:
        warn(m)

    tty = sys.stdout.isatty()
    style = make_style(st, args, tty)

    status = settings_command(st, args, style, tty)
    if status is not None:
        return status

    word = " ".join(args.word).strip()
    if not word:
        ap.error("a word to look up is required (or a settings option such as --settings)")
    limit = args.limit or st["general.search_results"]
    if args.search:
        return show_search(word, limit, args.json)
    client = st.client()
    try:
        if args.refresh:
            client.forget(word)
        root = client.page(word)
    except NotFound:
        print(f"No Wiktionary entry for '{word}'.", file=sys.stderr)
        sugg = suggestions(word, limit=limit)
        if sugg:
            print("Did you mean: " + ", ".join(sugg), file=sys.stderr)
        return 1
    except NetworkError as e:
        print(network_message(e), file=sys.stderr)
        return 2
    return show_entry(st, args, style, tty, word, root, client)


def make_style(st: Settings, args, tty: bool) -> Style:
    """Colours (and links) as the settings, the options and the terminal say."""
    color = {"always": True, "never": False}.get(st["cli.color"], tty)
    color = color and not args.no_color and "NO_COLOR" not in os.environ
    return Style(color, links=color and st["cli.links"])


def settings_command(st: Settings, args, style: Style, tty: bool) -> int | None:
    """Runs the settings option given, if any: its exit status, or None to
    go on looking up the word."""
    if args.set or args.unset:
        return change_settings(st, args.set, args.unset)
    if args.settings:
        print_settings(st, style)
        return 0
    if args.configure:
        return configure(st, Style(tty and not args.no_color))
    if args.edit_settings:
        return edit_settings(st)
    if args.clear_cache:
        print(clear_cache())
        if not args.word:
            return 0
    return None


def show_search(word: str, limit: int, as_json: bool) -> int:
    try:
        results = search(word, limit=limit)
    except NetworkError as e:
        print(network_message(e), file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif results:
        print("\n".join(results))
    else:
        print(f"No results for '{word}'.", file=sys.stderr)
        return 1
    return 0


def show_entry(st: Settings, args, style: Style, tty: bool, word: str, root: Node,
               client: Client) -> int:
    lang = args.lang or st["general.languages"]
    languages = language_sections(root)
    chosen = select_languages(languages, lang, st["general.preferred_languages"])
    if not chosen:
        print(f"'{word}' has no entry in the requested language(s) ({lang}).", file=sys.stderr)
        print("Available: " + available_languages(languages), file=sys.stderr)
        print("Use -l CODE, -l NAME or -l all.", file=sys.stderr)
        return 1

    brief = args.brief or (st["cli.brief"] and not args.full)
    opts = Options.build(args.only, args.exclude, brief, base=st.options())

    if args.json:
        print(json.dumps({"word": word, "url": page_url(word),
                          "entries": entry_to_json(chosen, opts, client.subpage)},
                         ensure_ascii=False, indent=2))
        return 0

    rendered = render_entry(word, chosen, style, term_width(st["general.max_width"]),
                            opts, client.subpage)
    text = rendered.text() + "\n" + style.dim(page_url(word))
    mode = "never" if (args.no_pager or not tty) else st["cli.pager"]
    page_output(text, mode, st["cli.pager_command"])
    return 0


def run():
    """Console-script entry point."""
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    run()
