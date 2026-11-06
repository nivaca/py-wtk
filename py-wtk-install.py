#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Add py-wtk to the applications menu: python3 py-wtk-install.py
[--only-gui | --uninstall]

Adds three entries that start the program from this folder, with the
program's icon: the window (py-wtk-gui), the full-screen terminal version
(py-wtk-tui, in a terminal) and the command line (py-wtk -i, in a terminal:
it asks for one word after another).  With --only-gui, only the window's
(and the other two are removed, if an earlier run added them).

* Linux and other freedesktop systems: .desktop files and the icons in the
  user's data folder ($XDG_DATA_HOME, usually ~/.local/share);
* Windows: shortcuts in the user's Start menu (made with PowerShell);
* macOS: three small applications in ~/Applications.

Everything goes in the user's own folders, so no administrator rights are
needed.  Run it again after moving this folder; --uninstall removes the
entries and icons it added, and nothing else.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pywtk.version import check_python  # noqa: E402

check_python()          # (before the modules that need it)

import argparse  # noqa: E402
import plistlib  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from typing import NamedTuple  # noqa: E402

from pywtk.version import NAME, VERSION  # noqa: E402

APP_ID = "py-wtk"                       # the names of the entries and icons
BUNDLE_ID = "io.github.nivaca.py-wtk"
COMMENT = "Look up words in the English Wiktionary"
HERE = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(HERE, "icons")
PROG = "py-wtk-install.py"


def display_name(kind):
    """The name shown for the entry of KIND (GUI, TUI or CLI)."""
    return f"{NAME} ({kind})"


#  (kind, launcher, its arguments, whether it runs in a terminal)
PROGRAMS = (("GUI", "py-wtk-gui", (), False),
            ("TUI", "py-wtk-tui", (), True),
            ("CLI", "py-wtk", ("-i",), True))
KINDS = tuple(kind for kind, _, _, _ in PROGRAMS)


def programs(kinds) -> list[tuple]:
    """The PROGRAMS of KINDS."""
    return [p for p in PROGRAMS if p[0] in kinds]


def remove(paths: list[str]) -> list[str]:
    for path in paths:
        os.remove(path)
    return paths


# ---------------------------------------------------------------------------
#  Linux and other freedesktop systems

HICOLOR = os.path.join(ICON_DIR, "linux", "hicolor")

ENTRY = """[Desktop Entry]
Type=Application
Version=1.0
Name={name}
Comment={comment}
Keywords=dictionary;Wiktionary;English;
Categories=Office;Dictionary;
Icon={app_id}
Exec={exec}
"""

#  The lines that differ, by kind (StartupWMClass is the className that
#  pywtk/gui.py gives the window)
ENTRY_REST = {
    "GUI": f"Terminal=false\nStartupNotify=true\nStartupWMClass={APP_ID}\n",
    "TUI": "Terminal=true\n",
    "CLI": "Terminal=true\n",
}

#  The file names of the entries, by kind
ENTRY_FILES = {"GUI": APP_ID + ".desktop", "TUI": APP_ID + ".tui.desktop",
               "CLI": APP_ID + ".cli.desktop"}


def data_home():
    return os.environ.get("XDG_DATA_HOME") or \
        os.path.join(os.path.expanduser("~"), ".local", "share")


def entry_path(kind):
    return os.path.join(data_home(), "applications", ENTRY_FILES[kind])


def exec_arg(arg):
    """ARG quoted for an Exec line, as the desktop entry specification
    requires when it has spaces or special characters."""
    if arg and not any(c in arg for c in " \t\n\"'\\><~|&;$*?#()`"):
        return arg
    for c in '\\"`$':
        arg = arg.replace(c, "\\" + c)
    return f'"{arg}"'


def icon_files():
    """(source, path relative to the hicolor theme) for each icon."""
    if not os.path.isdir(HICOLOR):
        return []
    found = []
    for size in sorted(os.listdir(HICOLOR)):
        apps = os.path.join(HICOLOR, size, "apps")
        for name in (APP_ID + ".png", APP_ID + ".svg"):
            if os.path.isfile(os.path.join(apps, name)):
                found.append((os.path.join(apps, name),
                              os.path.join(size, "apps", name)))
    return found


def refresh_linux():
    """Tells the desktop about the change (each tool only if present)."""
    for command in (["update-desktop-database",
                     os.path.join(data_home(), "applications")],
                    ["gtk-update-icon-cache", "-f", "-t", "-q",
                     os.path.join(data_home(), "icons", "hicolor")],
                    ["kbuildsycoca6"], ["kbuildsycoca5"]):
        if shutil.which(command[0]):
            subprocess.run(command, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=False)
            if command[0] == "kbuildsycoca6":
                break


def install_linux(chosen: list[tuple]) -> list[str]:
    theme = os.path.join(data_home(), "icons", "hicolor")
    for source, rel in icon_files():
        dest = os.path.join(theme, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.lexists(dest):
            os.remove(dest)             # (it may be read-only)
        shutil.copyfile(source, dest)
    paths = []
    for kind, program, args, _ in chosen:
        command = [sys.executable, os.path.join(HERE, program), *args]
        path = entry_path(kind)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(ENTRY.format(name=display_name(kind), comment=COMMENT,
                                 app_id=APP_ID, exec=" ".join(
                                     exec_arg(a) for a in command)))
            f.write(ENTRY_REST[kind])
        os.chmod(path, 0o755)
        paths.append(path)
    refresh_linux()
    return paths


def is_our_entry(path: str) -> bool:
    """Whether PATH is a .desktop file this script made (a regular file,
    not a link, with our icon)."""
    if not path.endswith(".desktop") or os.path.islink(path) \
            or not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    return bool(lines) and lines[0] == "[Desktop Entry]" \
        and f"Icon={APP_ID}" in lines


def uninstall_linux(chosen: list[tuple], icons: bool = True) -> list[str]:
    """Removes the .desktop files of CHOSEN and (with ICONS) the icons, and
    nothing else: only the files this script made."""
    paths = [path for path in (entry_path(kind) for kind, _, _, _ in chosen)
             if is_our_entry(path)]
    if icons:
        theme = os.path.join(data_home(), "icons", "hicolor")
        paths = [path for path in (os.path.join(theme, rel)
                                   for _, rel in icon_files())
                 if os.path.isfile(path) and not os.path.islink(path)] + paths
    removed = remove(paths)
    refresh_linux()
    return removed


# ---------------------------------------------------------------------------
#  Windows

ICO = os.path.join(ICON_DIR, "windows", APP_ID + ".ico")

#  Makes a shortcut with the Windows Script Host, from the values in the
#  environment (which spares quoting them in the script).
SHORTCUT_SCRIPT = (
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:PYW_LNK);"
    " $s.TargetPath = $env:PYW_TARGET;"
    " $s.Arguments = $env:PYW_ARGS;"
    " $s.WorkingDirectory = $env:PYW_DIR;"
    " $s.Description = $env:PYW_COMMENT;"
    " if ($env:PYW_ICON) { $s.IconLocation = $env:PYW_ICON };"
    " $s.Save()")


class Shortcut(NamedTuple):
    path: str               # the .lnk file
    target: str             # the Python that runs the program
    arguments: str
    folder: str             # where it runs
    icon: str               # "file,index", or ''


def start_menu():
    appdata = os.environ.get("APPDATA") or \
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs")


def windows_shortcuts(chosen: list[tuple]) -> list[Shortcut]:
    """The shortcuts: the window runs with pythonw.exe, which opens no
    console; the terminal version with python.exe, which opens one."""
    folder = os.path.dirname(sys.executable)
    pythonw = os.path.join(folder, "pythonw.exe")
    icon = ICO + ",0" if os.path.isfile(ICO) else ""
    shortcuts = []
    for kind, program, args, terminal in chosen:
        target = sys.executable if terminal or not os.path.isfile(pythonw) \
            else pythonw
        shortcuts.append(Shortcut(
            os.path.join(start_menu(), display_name(kind) + ".lnk"), target,
            subprocess.list2cmdline([os.path.join(HERE, program), *args]), HERE, icon))
    return shortcuts


def install_windows(chosen: list[tuple]) -> list[str]:
    paths = []
    for s in windows_shortcuts(chosen):
        os.makedirs(os.path.dirname(s.path), exist_ok=True)
        env = dict(os.environ, PYW_LNK=s.path, PYW_TARGET=s.target,
                   PYW_ARGS=s.arguments, PYW_DIR=s.folder, PYW_ICON=s.icon,
                   PYW_COMMENT=COMMENT)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             SHORTCUT_SCRIPT], env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False)
        if result.returncode != 0 or not os.path.isfile(s.path):
            output = result.stdout.decode(errors="replace").strip()
            raise OSError(f"could not make the shortcut {s.path}: {output}")
        paths.append(s.path)
    return paths


def uninstall_windows(chosen: list[tuple], icons: bool = True) -> list[str]:
    return remove([s.path for s in windows_shortcuts(chosen)
                   if os.path.isfile(s.path)])


# ---------------------------------------------------------------------------
#  macOS

ICNS = os.path.join(ICON_DIR, "mac", APP_ID + ".icns")


def applications_dir():
    return os.path.join(os.path.expanduser("~"), "Applications")


def app_path(kind):
    return os.path.join(applications_dir(), display_name(kind) + ".app")


def is_ours(app: str) -> bool:
    """Whether APP is an application this script made."""
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return False
    return str(info.get("CFBundleIdentifier", "")).startswith(BUNDLE_ID)


def write_script(path: str, text: str):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.chmod(path, 0o755)


def make_app(kind: str, program: str, args: tuple, terminal: bool) -> str:
    """APP.app/Contents/{Info.plist, MacOS/<launcher>, Resources/...}.  The
    launcher runs the program, or, for the terminal versions, opens it in
    Terminal (with a .command file)."""
    app = app_path(kind)
    if os.path.exists(app):
        if not is_ours(app):
            raise OSError(f"{app} exists and was not made by {PROG}; "
                          "move it away first")
        shutil.rmtree(app)
    contents = os.path.join(app, "Contents")
    macos = os.path.join(contents, "MacOS")
    resources = os.path.join(contents, "Resources")
    os.makedirs(macos)
    os.makedirs(resources)
    python = shlex.quote(sys.executable)
    command = " ".join(shlex.quote(a) for a in (os.path.join(HERE, program), *args))
    run = f"exec {python} {command}\n"
    launcher = os.path.join(macos, APP_ID)
    if terminal:
        write_script(os.path.join(resources, "run.command"),
                     f"#!/bin/sh\ncd {shlex.quote(HERE)}\nclear\n{run}")
        write_script(launcher, "#!/bin/sh\nexec open -a Terminal "
                               '"$(dirname "$0")/../Resources/run.command"\n')
    else:
        write_script(launcher, f"#!/bin/sh\ncd {shlex.quote(HERE)}\n{run}")
    info = {
        "CFBundleName": display_name(kind),
        "CFBundleDisplayName": display_name(kind),
        "CFBundleIdentifier": BUNDLE_ID + "." + kind.lower(),
        "CFBundleExecutable": APP_ID,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSApplicationCategoryType": "public.app-category.reference",
        "NSHighResolutionCapable": True,
    }
    if os.path.isfile(ICNS):
        shutil.copyfile(ICNS, os.path.join(resources, APP_ID + ".icns"))
        info["CFBundleIconFile"] = APP_ID
    with open(os.path.join(contents, "Info.plist"), "wb") as f:
        plistlib.dump(info, f)
    return app


def install_macos(chosen: list[tuple]) -> list[str]:
    os.makedirs(applications_dir(), exist_ok=True)
    apps = [make_app(kind, program, args, terminal)
            for kind, program, args, terminal in chosen]
    for app in apps:
        os.utime(app)                   # (so that Finder shows the icon)
    return apps


def uninstall_macos(chosen: list[tuple], icons: bool = True) -> list[str]:
    removed = []
    for kind, _, _, _ in chosen:
        app = app_path(kind)
        if os.path.isdir(app) and is_ours(app):
            shutil.rmtree(app)
            removed.append(app)
    return removed


# ---------------------------------------------------------------------------

def system(platform=None) -> str:
    platform = platform or sys.platform
    if platform == "win32":
        return "windows"
    if platform == "darwin":
        return "macos"
    return "linux"


INSTALL = {"linux": install_linux, "windows": install_windows, "macos": install_macos}
UNINSTALL = {"linux": uninstall_linux, "windows": uninstall_windows,
             "macos": uninstall_macos}


def install(kinds=KINDS) -> tuple[list[str], list[str]]:
    """Adds the entries of KINDS and removes those of the other kinds (left
    by an earlier run).  Returns (what was added, what was removed)."""
    added = INSTALL[system()](programs(kinds))
    others = [p for p in PROGRAMS if p[0] not in kinds]
    removed = UNINSTALL[system()](others, icons=False) if others else []
    return added, removed


def uninstall() -> list[str]:
    return UNINSTALL[system()](PROGRAMS)


WHERE = {"linux": "the applications menu",
         "windows": "the Start menu",
         "macos": "Applications (in your home folder)"}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=f"Add {NAME} to the applications menu, or remove it.")
    what = parser.add_mutually_exclusive_group()
    what.add_argument("--only-gui", action="store_true",
                      help="add only the window (py-wtk-gui), and remove the entries of the "
                           "terminal version and the command line if they are there")
    what.add_argument("--uninstall", action="store_true",
                      help="remove what was added")
    args = parser.parse_args(argv)
    where = WHERE[system()]
    try:
        if args.uninstall:
            removed = uninstall()
            print(f"Removed {NAME} from {where}." if removed
                  else "There was nothing to remove.")
            return
        paths, removed = install(("GUI",) if args.only_gui else KINDS)
    except OSError as e:
        sys.exit(f"{PROG}: {e}")
    print(f"Added {NAME} to {where}:")
    for path in paths:
        print("  " + path)
    if removed:
        print("Removed the entries no longer wanted:")
        for path in removed:
            print("  " + path)
    print("If you move this folder, run this again.")


if __name__ == "__main__":
    main()
