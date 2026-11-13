# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""The settings of py-wtk, shared by the three programs.

They are kept in the configuration file (see config.py), one section per
part of the program:

    [general]      what is shown, searching, the disk cache (all programs)
    [cli]          py-wtk
    [tui]          py-wtk-tui
    [gui]          py-wtk-gui
    [fonts]        the fonts of the window
    [appearance]   dark_mode

Every setting is described once in SCHEMA; the settings screens of the
three programs are made from it.  A setting the file leaves out has its
usual value.  Saving writes only the settings that were changed, onto the
file as it is then, so that two programs open at once do not undo each
other's changes; restoring a setting's usual value removes it from the
file.  Values that are not valid are reported (Settings.problems) and the
usual ones used instead.

The settings of earlier versions are moved here once, if there is no
config.toml yet: the settings.ini of earlier versions, and the folder of the
versions named py-wkt (~/.config/py-wkt ...); the old file is renamed *.old.
"""

from __future__ import annotations

import configparser
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config
from .api import Client
from .entry import Options, norm_title

TRUE = {"1", "true", "yes", "on"}
FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Setting:
    section: str           # general, cli, tui, gui, fonts or appearance
    key: str
    kind: str              # "bool", "int", "str", "choice" or "list"
    default: Any
    label: str             # short, for settings screens
    help: str              # one or two sentences, also the comment in the file
    choices: tuple = ()
    min: int | None = None
    max: int | None = None
    hidden: bool = False   # kept by the program (e.g. the window size): not in the screens

    @property
    def name(self) -> str:
        return f"{self.section}.{self.key}"

    def parse(self, raw: Any) -> Any:
        """RAW (from the file, a typed value, or text typed by the user) in
        this setting's type; raises ValueError with a readable message."""
        if self.kind == "bool":
            if isinstance(raw, bool):
                return raw
            s = str(raw).strip().lower()
            if s in TRUE:
                return True
            if s in FALSE:
                return False
            raise ValueError(f"{self.name}: must be true or false, not {raw!r}")
        if self.kind == "int":
            if isinstance(raw, bool):
                raise ValueError(f"{self.name}: must be a whole number, not {raw!r}")
            try:
                v = int(str(raw).strip())
            except ValueError:
                raise ValueError(f"{self.name}: must be a whole number, not {raw!r}") from None
            if (self.min is not None and v < self.min) or (self.max is not None and v > self.max):
                raise ValueError(f"{self.name}: must be between {self.min} and {self.max}")
            return v
        if self.kind == "choice":
            s = str(raw).strip().lower()
            if s not in self.choices:
                raise ValueError(f"{self.name}: must be one of {', '.join(self.choices)}")
            return s
        if self.kind == "list":
            items = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
            return [str(x).strip() for x in items if str(x).strip()]
        if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
            raise ValueError(f"{self.name}: must be text, not {raw!r}")
        return str(raw).strip()

    def format(self, value: Any) -> str:
        """The value as shown in text interfaces."""
        if self.kind == "bool":
            return "true" if value else "false"
        if self.kind == "list":
            return ", ".join(value)
        return str(value)

    def describe_range(self) -> str:
        if self.kind == "bool":
            return "true / false"
        if self.kind == "choice":
            return " / ".join(self.choices)
        if self.kind == "int":
            return f"{self.min}–{self.max}"
        if self.kind == "list":
            return "a list"
        return "text"


SECTION_TITLES = {
    "general": "General (all programs)",
    "cli": "Command line (py-wtk)",
    "tui": "Terminal interface (py-wtk-tui)",
    "gui": "Window (py-wtk-gui)",
    "fonts": "Fonts (py-wtk-gui)",
    "appearance": "Appearance (py-wtk-gui)",
}

SECTION_INTRO = {
    "general": "What all three programs show, and how they search and keep pages.",
    "cli": "The command-line program, py-wtk.",
    "tui": "The terminal interface, py-wtk-tui.",
    "gui": "The window, py-wtk-gui.",
    "fonts": "The fonts of the window (also changed with Ctrl and + or -, and Ctrl and 0 "
             "for the usual ones). Sizes are in points.",
    "appearance": "The look of the window: dark_mode = true for dark, false for light "
                  "(left out: light). Also changed with the moon (or sun) at the bottom "
                  "right of the window, and View → Dark mode.",
}

SCHEMA: list[Setting] = [
    # ---- general ------------------------------------------------------------
    Setting("general", "languages", "str", "all", "Languages",
            "Languages to show by default: codes or English names separated by commas, "
            "or 'all'."),
    Setting("general", "preferred_languages", "list", [], "Preferred languages first",
            "These languages are shown first, in this order (e.g. en, la); the rest follow."),
    Setting("general", "show_quotations", "bool", True, "Show quotations",
            "Show dated quotations under the definitions (they can be long)."),
    Setting("general", "show_tables", "bool", True, "Show tables",
            "Show tables such as declensions and conjugations."),
    Setting("general", "show_translations", "bool", True, "Show translations",
            "Show translation sections; for big entries this downloads an extra page."),
    Setting("general", "hidden_sections", "list", [], "Hidden sections",
            "Sections never shown, e.g. anagrams, further reading, references."),
    Setting("general", "search_results", "int", 10, "Search results",
            "How many results and suggestions to show when searching.", min=1, max=50),
    Setting("general", "max_width", "int", 110, "Maximum text width",
            "Text is wrapped at most at this many characters.", min=40, max=300),
    Setting("general", "cache_days", "int", 1, "Keep pages on disk (days)",
            "Downloaded pages are kept on disk this many days; 0: not at all.",
            min=0, max=365),
    # ---- cli ----------------------------------------------------------------
    Setting("cli", "color", "choice", "auto", "Colours",
            "Use colours: auto (only in a terminal), always or never.",
            choices=("auto", "always", "never")),
    Setting("cli", "pager", "choice", "auto", "Pager",
            "Use a pager for long entries: auto (when they do not fit), always or never.",
            choices=("auto", "always", "never")),
    Setting("cli", "pager_command", "str", "", "Pager command",
            "Pager to use; empty: $PAGER, or less if $PAGER is not set."),
    Setting("cli", "links", "bool", True, "Links",
            "Make the links of an entry clickable, in the terminals that can (OSC 8 "
            "hyperlinks, only with colours). Turn it off if they show up as stray "
            "characters."),
    Setting("cli", "brief", "bool", False, "Brief by default",
            "Show only definitions unless asked otherwise (as if -b were always given; "
            "-F then gives the full entry)."),
    # ---- tui ----------------------------------------------------------------
    Setting("tui", "show_contents", "bool", True, "Show contents pane",
            "Show the table of contents at the left."),
    Setting("tui", "contents_width", "int", 30, "Contents pane width",
            "Width of the contents pane, in columns.", min=16, max=60),
    Setting("tui", "colors", "bool", True, "Colours",
            "Use colours (false: bold and dim only)."),
    Setting("tui", "mouse", "bool", True, "Mouse",
            "Use the mouse (wheel to scroll, click in the contents). Turn it off to "
            "select text with the mouse as usual in your terminal."),
    Setting("tui", "wheel_lines", "int", 3, "Mouse wheel lines",
            "Lines scrolled by one step of the mouse wheel.", min=1, max=20),
    # ---- gui ----------------------------------------------------------------
    Setting("gui", "show_contents", "bool", True, "Show contents pane",
            "Show the table of contents at the left."),
    Setting("gui", "contents_width", "int", 250, "Contents pane width",
            "Width of the contents pane, in pixels at 96 DPI (more on a scaled display).",
            min=120, max=700),
    Setting("gui", "double_click_lookup", "bool", True, "Double-click looks up",
            "Double-clicking a word in the entry looks it up."),
    Setting("gui", "links", "bool", True, "Clickable links",
            "The words linked in an entry can be clicked: other entries open in the "
            "window, the rest of the links in the web browser."),
    Setting("gui", "live_suggestions", "bool", True, "Suggestions while typing",
            "Show matching page titles under the search box while typing."),
    Setting("gui", "remember_window", "bool", True, "Remember window size",
            "Open the window with the size it had when it was closed."),
    Setting("gui", "window_geometry", "str", "", "Window size",
            "The size of the window when it was last closed (kept by the program).",
            hidden=True),
    # ---- fonts --------------------------------------------------------------
    Setting("fonts", "text_family", "str", "", "Entry font",
            "The font of the entries; it should be fixed-width, as tables are laid out "
            "in columns. Empty: the usual one."),
    Setting("fonts", "text_size", "int", 11, "Entry font size",
            "The size of the entries' font.", min=6, max=40),
    Setting("fonts", "ui_family", "str", "", "Interface font",
            "The font of the rest of the window (menus, buttons, contents). "
            "Empty: the system's."),
    Setting("fonts", "ui_size", "int", 0, "Interface font size",
            "The size of the interface font; 0: the system's.", min=0, max=40),
    # ---- appearance ---------------------------------------------------------
    Setting("appearance", "dark_mode", "bool", False, "Dark mode",
            "Dark colours for the window."),
]

BY_NAME = {s.name: s for s in SCHEMA}

#  Names of earlier versions (settings.ini) that changed
RENAMED = {
    "gui.font_family": "fonts.text_family",
    "gui.font_size": "fonts.text_size",
}


def lookup(name: str) -> Setting:
    """A setting by 'section.key', or by its key alone if no other has it."""
    if name in BY_NAME:
        return BY_NAME[name]
    matches = [s for s in SCHEMA if s.key == name]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise KeyError(f"'{name}' is ambiguous: " + ", ".join(s.name for s in matches))
    raise KeyError(f"unknown setting '{name}' (see --settings for the list)")


def cache_dir() -> Path:
    return Path(config.cache_dir())


# ---------------------------------------------------------------------------
#  The file

HEADER = ("The settings of py-wtk. Each setting can be left out (or the whole file "
          "deleted) to use its usual value; those left out are shown commented, with "
          "their usual value. The programs rewrite this file when settings are saved: "
          "the values are kept, but not comments of your own.")


def render(data: dict[str, dict]) -> str:
    """The text of config.toml for DATA, with every setting described."""
    out = config.comment(HEADER) + [""]
    names = list(SECTION_TITLES) + [n for n in data if n not in SECTION_TITLES]
    for name in names:
        values = data.get(name, {})
        settings = [s for s in SCHEMA if s.section == name]
        if not settings and not values:
            continue
        out.append(f"[{config.toml_key(name)}]")
        if name in SECTION_INTRO:
            out += config.comment(SECTION_INTRO[name])
        for s in settings:
            if s.hidden and s.key not in values:
                continue
            out.append("")
            out += config.comment(f"{s.help} ({s.describe_range()})")
            if s.key in values:
                out.append(f"{s.key} = {config.toml_value(values[s.key])}")
            else:
                out.append(f"# {s.key} = {config.toml_value(s.default)}")
        unknown = [k for k in values if f"{name}.{k}" not in BY_NAME]
        if unknown:
            out.append("")
            out.append("# Not settings of this version of py-wtk (ignored):")
            out += [f"{config.toml_key(k)} = {config.toml_value(values[k])}" for k in unknown]
        out.append("")
    return "\n".join(out)


REMOVE = object()  # (a change that removes a setting from the file)


class Settings:
    """The settings in use: the usual values, with what the configuration
    file says on top."""

    def __init__(self):
        self.values: dict[str, Any] = {s.name: s.default for s in SCHEMA}
        self.problems: list[str] = []   # what was wrong in the file
        self.messages: list[str] = []   # other things worth saying (e.g. migration)
        self._changes: dict[str, Any] = {}
        self.load()

    @property
    def path(self) -> Path:
        return Path(config.config_path())

    def load(self):
        self._move_old()
        try:
            data = config.read()
        except config.ConfigError as e:
            self.problems.append(f"{e}; its settings are not used")
            return
        for section, values in data.items():
            for key, raw in values.items():
                s = BY_NAME.get(f"{section}.{key}")
                if s is None:
                    self.problems.append(f"{self.path}: [{section}] {key}: unknown setting")
                    continue
                try:
                    self.values[s.name] = s.parse(raw)
                except ValueError as e:
                    self.problems.append(f"{self.path}: {e}; using the usual value")

    def _move_old(self):
        """The settings of earlier versions, into config.toml (once, when
        there is none yet): the settings.ini of earlier versions, here or in the
        folder of the versions named py-wkt, or the config.toml of that
        folder.  The old file is then renamed *.old."""
        if self.path.exists():
            return
        here = Path(config.config_dir())
        old = config.old_config_dir()
        old = Path(old) if old else None
        if (here / "settings.ini").is_file():
            self._import_ini(here / "settings.ini")
        elif old and (old / config.CONFIG_FILE).is_file():
            self._import_toml(old / config.CONFIG_FILE)
        elif old and (old / "settings.ini").is_file():
            self._import_ini(old / "settings.ini")

    def _import_toml(self, path: Path):
        try:
            with open(path, "rb") as f:
                data = {k: v for k, v in tomllib.load(f).items() if isinstance(v, dict)}
        except (OSError, tomllib.TOMLDecodeError):
            return                          # (left for the user to look at)
        self._write_moved(path, data)

    def _import_ini(self, ini: Path):
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read(ini, encoding="utf-8")
        except (configparser.Error, OSError):
            return
        data: dict[str, dict] = {}
        for section in cp.sections():
            for key, raw in cp.items(section):
                name = RENAMED.get(f"{section}.{key}", f"{section}.{key}")
                if name == "gui.theme":
                    name, raw = "appearance.dark_mode", str(raw.strip() == "dark")
                s = BY_NAME.get(name)
                if s is None:
                    continue
                try:
                    value = s.parse(raw)
                except ValueError:
                    continue
                if value != s.default:
                    data.setdefault(s.section, {})[s.key] = value
        self._write_moved(ini, data)

    def _write_moved(self, old: Path, data: dict):
        try:
            config.write(data, render)
            os.replace(old, old.with_name(old.name + ".old"))
            self.messages.append(f"Moved the settings of {old} to {self.path} "
                                 f"(the old file is now {old.name}.old)")
        except OSError:
            pass

    # ---- access ----------------------------------------------------------- #
    def __getitem__(self, name: str) -> Any:
        return self.values[lookup(name).name]

    def get(self, name: str) -> Any:
        return self[name]

    def set(self, name: str, value: Any) -> Any:
        """Changes a setting (for this session; save() keeps it)."""
        s = lookup(name)
        self.values[s.name] = s.parse(value)
        self._changes[s.name] = self.values[s.name]
        return self.values[s.name]

    def reset(self, name: str | None = None):
        """Back to the usual value (save() removes it from the file)."""
        for s in SCHEMA if name is None else [lookup(name)]:
            if s.hidden and name is None:
                continue
            self.values[s.name] = s.default
            self._changes[s.name] = REMOVE

    def is_default(self, name: str) -> bool:
        s = lookup(name)
        return self.values[s.name] == s.default

    def save(self) -> str | None:
        """Writes the settings changed since the last save onto the file as it
        is now.  Returns its path (None if nothing changed).  Raises OSError if
        it cannot be written, config.ConfigError if the file is unreadable."""
        if not self._changes:
            return None
        changes: dict[str, dict] = {}
        removals: dict[str, set] = {}
        for name, value in self._changes.items():
            s = BY_NAME[name]
            if value is REMOVE:
                removals.setdefault(s.section, set()).add(s.key)
            else:
                changes.setdefault(s.section, {})[s.key] = value
        path = config.update(changes, removals, render)
        self._changes.clear()
        return path

    def write_all(self) -> str:
        """Writes the file even if nothing changed (to create it, documented)."""
        return config.update({}, {}, render)

    def visible(self, section: str | None = None) -> list[Setting]:
        return [s for s in SCHEMA if not s.hidden and (section is None or s.section == section)]

    # ---- what the settings make ------------------------------------------- #
    def options(self, show_quotes: bool | None = None,
                show_tables: bool | None = None) -> Options:
        """entry.Options from the general settings."""
        exclude = {norm_title(x) for x in self["general.hidden_sections"]}
        if not self["general.show_translations"]:
            exclude.add("translations")
        return Options(
            exclude=exclude,
            show_quotes=self["general.show_quotations"] if show_quotes is None else show_quotes,
            show_tables=self["general.show_tables"] if show_tables is None else show_tables,
        )

    def client(self, **kw) -> Client:
        """api.Client with the disk cache configured from the settings."""
        days = self["general.cache_days"]
        return Client(cache_dir=cache_dir() if days else None, max_age_days=days, **kw)
