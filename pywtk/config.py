# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""The configuration file, config.toml, in the user's settings folder.

    Linux     $XDG_CONFIG_HOME/py-wtk/config.toml (usually ~/.config)
    macOS     ~/Library/Application Support/py-wtk/config.toml
    Windows   %APPDATA%\\py-wtk\\config.toml

($PY_WTK_CONFIG names another folder; $PY_WKT_CONFIG, of the versions
named py-wkt, is still read.)  Its sections:

    [general]      what is shown, searching, the disk cache (all programs)
    [cli]          the command line (py-wtk)
    [tui]          the terminal interface (py-wtk-tui)
    [gui]          the window (py-wtk-gui)
    [fonts]        the fonts of the window
    [appearance]   dark_mode: whether the window is dark

Every setting may be left out, and then has its usual value.  The program
writes the file when settings are saved, with comments that describe every
setting (those left out appear commented, with their usual value); comments
of one's own are not kept.  The file can also be edited by hand.

This module only reads and writes the file; settings.py knows what the
settings are.
"""

from __future__ import annotations

import os
import sys
import tomllib

CONFIG_FILE = "config.toml"
APP = "py-wtk"
#  The name of earlier versions, whose settings are moved here once (see
#  settings.Settings._move_old)
OLD_APP = "py-wkt"


class ConfigError(Exception):
    """config.toml cannot be read."""


#  The variables that name the settings folder (the second, of the versions
#  named py-wkt, is still read)
CONFIG_VARS = ("PY_WTK_CONFIG", "PY_WKT_CONFIG")


def _named_config_dir() -> str | None:
    """The folder named by $PY_WTK_CONFIG or $PY_WKT_CONFIG, if any."""
    for var in CONFIG_VARS:
        if os.environ.get(var):
            return os.path.expanduser(os.environ[var])
    return None


def config_dir() -> str:
    """Where the user's settings are kept: $PY_WTK_CONFIG (or $PY_WKT_CONFIG,
    of earlier versions), else the usual settings folder of the system."""
    return _named_config_dir() or system_config_dir(APP)


def old_config_dir() -> str | None:
    """The settings folder of the versions named py-wkt (None when a folder
    was named with the variables: then there is nothing to move)."""
    return None if _named_config_dir() else system_config_dir(OLD_APP)


def system_config_dir(app: str) -> str:
    """The usual settings folder of the system, for APP."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or \
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or \
            os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, app)


def config_path() -> str:
    return os.path.join(config_dir(), CONFIG_FILE)


def cache_dir() -> str:
    """Where downloaded pages are kept (see api.Client)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or \
            os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, APP, "cache")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Caches", APP)
    base = os.environ.get("XDG_CACHE_HOME") or \
        os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, APP)


def read() -> dict[str, dict]:
    """The sections of the configuration file ({} if there is none);
    raises ConfigError if it cannot be read or is not valid TOML."""
    try:
        with open(config_path(), "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise ConfigError(f"cannot read {config_path()}: {e.strerror}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{config_path()}: {e}") from None
    return {name: value for name, value in data.items() if isinstance(value, dict)}


def section(name: str) -> dict:
    """One section of the file, or {} (also if the file is unreadable)."""
    try:
        return read().get(name, {})
    except ConfigError:
        return {}


def update(changes: dict[str, dict], removals: dict[str, set] | None = None,
           render=None) -> str:
    """Sets the values CHANGES ({section: {key: value}}) and removes the keys
    REMOVALS ({section: {key, ...}}) in the file, keeping everything else as
    the file has it now (another program may have changed it since it was
    read).  Returns the path.  Raises OSError if it cannot be written, and
    ConfigError if the file there is unreadable (it is then left alone)."""
    data = read()
    for name, values in changes.items():
        data.setdefault(name, {}).update(values)
    for name, keys in (removals or {}).items():
        for key in keys:
            data.get(name, {}).pop(key, None)
    write(data, render)
    return config_path()


def write(data: dict[str, dict], render=None) -> None:
    """Writes DATA; RENDER(data) -> text makes the file (default: plain TOML)."""
    os.makedirs(config_dir(), exist_ok=True)
    path = config_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write((render or plain)(data))
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
#  Writing TOML: the values are only booleans, integers, strings and lists of
#  strings

def toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml_value(str(v)) for v in value) + "]"
    text = str(value)
    for old, new in (("\\", "\\\\"), ('"', '\\"'), ("\n", "\\n"), ("\t", "\\t")):
        text = text.replace(old, new)
    return f'"{text}"'


def toml_key(key: str) -> str:
    return key if key.replace("_", "").replace("-", "").isalnum() else toml_value(key)


def plain(data: dict[str, dict]) -> str:
    out = []
    for name, values in data.items():
        out.append(f"[{toml_key(name)}]")
        out += [f"{toml_key(k)} = {toml_value(v)}" for k, v in values.items()]
        out.append("")
    return "\n".join(out)


def comment(text: str, width: int = 76, prefix: str = "#") -> list[str]:
    """TEXT as comment lines."""
    lines, line = [], prefix
    for word in text.split():
        if len(line) + 1 + len(word) > width and line != prefix:
            lines.append(line)
            line = prefix
        line += " " + word
    lines.append(line)
    return lines
