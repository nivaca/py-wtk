#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Makes an AppImage of the program, for Linux: python3 tools/bundle-appimage.py

The AppImage is dist/py-wtk-v.VERSION-x86_64.AppImage (the version of
pywtk/__init__.py; dist is made in the program's folder if need be, and
--output gives another folder).  It holds a Python of its own, with Tk and
curses (a relocatable Python of the python-appimage project,
https://github.com/niess/python-appimage), and the program as bundle-zip.py
puts it in the zip, so it runs on any Linux of the last ten years or so,
without installing anything.

It starts the window (py-wtk-gui); a first argument chooses another of the
programs:

    py-wtk.AppImage [gui|cli|tui] ...

and so does the name it is called by, if it is a link named py-wtk,
py-wtk-tui or py-wtk-gui.  "help" lists them.  The settings and the cache
are the user's usual ones (~/.config/py-wtk, ~/.cache/py-wtk), as with the
zip.

What it needs is downloaded the first time, and kept in the user's cache
folder (~/.cache/py-wtk-build): the Python and appimagetool
(https://github.com/AppImage/appimagetool).  --python and --appimagetool
give them instead.
"""

import os
import sys

#  (the program's folder, above tools/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pywtk.version import check_python  # noqa: E402

check_python()          # (before the modules that need it)

import argparse  # noqa: E402
import glob  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import urllib.request  # noqa: E402

from pywtk.version import COMMIT_FILE, NAME, VERSION  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # (above tools/)
#  Where the AppImage goes, unless --output says otherwise
DIST = os.path.join(HERE, "dist")
APP_ID = NAME                   # (also the window's class, gui.WM_CLASS)
ARCH = "x86_64"

#  The Python put in the AppImage (python-appimage has one release per
#  version, with an AppImage per manylinux; the older the manylinux, the
#  older the systems it runs on).  py-wtk needs 3.15 or later.
PYTHON = "3.15"
PYTHON_RELEASES = "https://api.github.com/repos/niess/python-appimage/" \
    "releases/tags/python{version}"
MANYLINUX = ("manylinux2014", "manylinux_2_28")
APPIMAGETOOL = "https://github.com/AppImage/appimagetool/releases/" \
    f"download/continuous/appimagetool-{ARCH}.AppImage"

#  The icons, as the user made them: the hicolor theme, and the one for the
#  AppImage itself (appimagetool wants a PNG for .DirIcon, as file managers do)
HICOLOR = os.path.join(HERE, "icons", "linux", "hicolor")
ICON = os.path.join(HICOLOR, "256x256", "apps", APP_ID + ".png")

#  The terminals whose descriptions go in the AppImage.  Its Python has the
#  ncurses 5 of manylinux, which cannot read the descriptions that newer
#  systems (Fedora, Debian 12...) compile in the format of ncurses 6.1 for
#  every terminal with 256 colours, and then curses does not start.  So the
#  AppImage carries them in the old format, made from those of the system
#  that builds it (those it does not know are left out).
TERMINALS = (
    "xterm", "xterm-color", "xterm-256color", "xterm-direct", "xterm-kitty",
    "screen", "screen-256color", "tmux", "tmux-256color", "linux", "vt100", "vt220",
    "rxvt", "rxvt-unicode", "rxvt-unicode-256color", "konsole", "konsole-256color",
    "gnome", "gnome-256color", "vte", "vte-256color", "putty", "putty-256color",
    "alacritty", "foot", "foot-direct", "wezterm", "st", "st-256color", "dumb",
    "ansi", "cygwin", "ms-terminal", "contour", "ghostty",
)
#  (the biggest number the old format holds)
SHORT_MAX = 32767

#  The programs: (command, launcher)
COMMANDS = (("gui", "py-wtk-gui"),
            ("cli", "py-wtk"),
            ("tui", "py-wtk-tui"))

DESKTOP = f"""[Desktop Entry]
Type=Application
Name={NAME}
GenericName=Dictionary
Comment=The English Wiktionary on your desktop
Comment[es]=El Wiktionary en inglés en tu escritorio
Keywords=dictionary;Wiktionary;etymology;translation;
Categories=Office;Dictionary;Education;
Icon={APP_ID}
Exec={APP_ID} %U
Terminal=false
StartupNotify=true
StartupWMClass={APP_ID}
"""

#  %(python)s: the interpreter, relative to the AppDir
APPRUN = r"""#!/bin/bash
#  Starts py-wtk in the AppImage (made by bundle-appimage.py).
HERE="$(dirname "$(readlink -f -- "$0")")"
export APPDIR="${APPDIR:-$HERE}"
PROGRAM="$APPDIR/opt/py-wtk"
SELF="${ARGV0:-$0}"

#  The Tcl/Tk, terminal descriptions and certificates of the Python of the
#  AppImage
for d in "$APPDIR"/usr/share/tcltk/tcl8* "$APPDIR"/usr/share/tcltk/tcl9*; do
    [ -d "$d" ] && export TCL_LIBRARY="$d"
done
for d in "$APPDIR"/usr/share/tcltk/tk8* "$APPDIR"/usr/share/tcltk/tk9*; do
    [ -d "$d" ] && export TK_LIBRARY="$d" TKPATH="$d"
done
[ -d "$APPDIR/usr/share/terminfo" ] && \
    export TERMINFO_DIRS="${TERMINFO_DIRS:+$TERMINFO_DIRS:}$APPDIR/usr/share/terminfo:/usr/share/terminfo:/lib/terminfo:/etc/terminfo"
for f in "$APPDIR"/opt/python*/lib/python*/site-packages/certifi/cacert.pem; do
    [ -f "$f" ] && export SSL_CERT_FILE="${SSL_CERT_FILE:-$f}"
done
#  (the AppImage cannot be written to)
export PYTHONDONTWRITEBYTECODE=1

usage() {
    echo "Usage: ${SELF##*/} [COMMAND] [ARGUMENTS ...]"
    echo
    echo "Commands (gui if none is given):"
%(usage)s
    echo
    echo "\"${SELF##*/} COMMAND --help\" tells what each one takes."
}

program() {
    case "$1" in
%(cases)s
        *) return 1 ;;
    esac
}

#  A link named after a program runs it; otherwise the first argument says
#  which, or the window
name="$(basename -- "$SELF")"
if script="$(program "$name")"; then
    :
elif [ "$1" = help ] || [ "$1" = --help ] || [ "$1" = -h ]; then
    usage
    exit 0
elif script="$(program "$1")"; then
    shift
else
    script=py-wtk-gui
fi
exec "$APPDIR/%(python)s" "$PROGRAM/$script" "$@"
"""


def name() -> str:
    """The name of the AppImage: py-wtk-v.1.0-x86_64.AppImage."""
    return f"{NAME}-v.{VERSION}-{ARCH}.AppImage"


def bundle_zip():
    """The module bundle-zip.py, whose list of files is used."""
    spec = importlib.util.spec_from_file_location(
        "bundle_zip", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bundle-zip.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files() -> list[str]:
    """The files of the program in the AppImage, relative to its folder:
    those of the zip, without the icons of other systems."""
    return [f for f in bundle_zip().files()
            if not f.startswith(os.path.join("icons", "")) or
            f.startswith(os.path.join("icons", "linux", ""))]


def cache_dir() -> str:
    """Where the downloads are kept."""
    base = os.environ.get("XDG_CACHE_HOME") or \
        os.path.join(os.path.expanduser("~"), ".cache")
    path = os.path.join(base, f"{NAME}-build")
    os.makedirs(path, exist_ok=True)
    return path


def download(url: str, path: str) -> str:
    """Downloads URL into PATH (unless it is there already); returns PATH."""
    if not os.path.isfile(path):
        print(f"Downloading {url} ...", file=sys.stderr)
        tmp = path + ".tmp"
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, path)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


def python_url(version: str) -> str:
    """The URL of the Python AppImage of VERSION (3.15 ...), for the oldest
    manylinux there is one for."""
    url = PYTHON_RELEASES.format(version=version)
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=60) as r:
        assets = json.load(r)["assets"]
    tag = "cp" + version.replace(".", "")
    for manylinux in MANYLINUX:
        #  (not those of the Python without the GIL, cp313t)
        end = f"-{tag}-{tag}-{manylinux}_{ARCH}.AppImage"
        found = [a["browser_download_url"] for a in assets if a["name"].endswith(end)]
        if found:
            return found[0]
    raise OSError(f"there is no Python {version} AppImage at {url}")


def python_appimage(version: str) -> str:
    """The Python AppImage of VERSION, downloaded if need be."""
    url = python_url(version)
    return download(url, os.path.join(cache_dir(), url.rsplit("/", 1)[1]))


def extract(appimage: str, folder: str) -> str:
    """Extracts APPIMAGE into FOLDER; returns its AppDir."""
    subprocess.run([os.path.abspath(appimage), "--appimage-extract"],
                   cwd=folder, check=True, stdout=subprocess.DEVNULL)
    return os.path.join(folder, "squashfs-root")


def make_appdir(appdir: str, commit: str | None):
    """Turns the AppDir of the Python into that of py-wtk."""
    pythons = sorted(glob.glob(os.path.join(appdir, "opt", "python3*", "bin", "python3.*")))
    pythons = [p for p in pythons if not p.endswith("-config")]
    if not pythons:
        raise OSError(f"there is no Python in {appdir}")
    python = os.path.relpath(pythons[0], appdir)
    #  Out with what makes it the Python's AppImage
    for pattern in ("AppRun", "*.desktop", "*.png", "*.svg", ".DirIcon",
                    "usr/share/applications", "usr/share/metainfo"):
        for path in glob.glob(os.path.join(appdir, pattern)):
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    #  The program
    program = os.path.join(appdir, "opt", APP_ID)
    for f in files():
        target = os.path.join(program, f)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(HERE, f), target)
    if commit:
        with open(os.path.join(program, COMMIT_FILE), "w", encoding="ascii") as f:
            f.write(commit + "\n")
    #  How to start it, its menu entry and its icons
    width = max(len(c) for c, _ in COMMANDS)
    usage = "\n".join(f'    echo "  {c.ljust(width)}  {p}"' for c, p in COMMANDS)
    cases = "\n".join(f"        {c}|{p}) echo {p} ;;" for c, p in COMMANDS)
    apprun = os.path.join(appdir, "AppRun")
    with open(apprun, "w", encoding="utf-8", newline="\n") as f:
        f.write(APPRUN % {"usage": usage, "cases": cases, "python": python})
    os.chmod(apprun, 0o755)
    with open(os.path.join(appdir, APP_ID + ".desktop"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(DESKTOP)
    shutil.copy2(ICON, os.path.join(appdir, APP_ID + ".png"))
    os.symlink(APP_ID + ".png", os.path.join(appdir, ".DirIcon"))
    shutil.copytree(HICOLOR, os.path.join(appdir, "usr", "share", "icons", "hicolor"),
                    dirs_exist_ok=True)
    terminfo(os.path.join(appdir, "usr", "share", "terminfo"))


def short_numbers(source: str) -> str:
    """SOURCE (a description, as infocmp gives it) with its numbers above
    SHORT_MAX made SHORT_MAX (pairs#0x10000 of 256 colours, say), so that tic
    writes it in the old format."""
    def cap(m):
        number = m.group(2)
        value = int(number, 16) if number[:2].lower() == "0x" else int(number)
        return m.group(1) + (str(SHORT_MAX) if value > SHORT_MAX else number)
    return re.sub(r"(\b[\w.]+#)(0x[0-9a-fA-F]+|\d+)\b", cap, source)


def terminfo(folder: str):
    """Writes into FOLDER the descriptions of TERMINALS, in the format of
    ncurses 5, as the AppRun looks for them there first."""
    if not (shutil.which("infocmp") and shutil.which("tic")):
        print("Warning: without infocmp and tic (ncurses), the AppImage has no "
              "terminal descriptions, and py-wtk-tui may not start in it",
              file=sys.stderr)
        return
    os.makedirs(folder, exist_ok=True)
    done = []
    for term in TERMINALS:
        source = subprocess.run(["infocmp", "-x", "-1", term], capture_output=True,
                                text=True)
        if source.returncode != 0:
            continue
        made = subprocess.run(["tic", "-x", "-o", folder, "-"],
                              input=short_numbers(source.stdout),
                              capture_output=True, text=True)
        if made.returncode == 0:
            done.append(term)
        else:
            print(f"Warning: tic {term}: {made.stderr.strip()}", file=sys.stderr)
    print(f"Terminal descriptions: {len(done)} of {len(TERMINALS)}", file=sys.stderr)


def open_to_all(appdir: str):
    """Lets everyone read the AppDir: folders 0755, files 0644, or 0755 if
    they can be run.  (Folders of the Python come out 0700, and whoever runs
    the AppImage could not read them.)"""
    def fix(path, mode):
        if not os.path.islink(path):
            os.chmod(path, mode)
    fix(appdir, 0o755)
    for folder, dirs, names in os.walk(appdir):
        for d in dirs:
            fix(os.path.join(folder, d), 0o755)
        for n in names:
            path = os.path.join(folder, n)
            if not os.path.islink(path):
                runs = os.stat(path).st_mode & stat.S_IXUSR
                fix(path, 0o755 if runs else 0o644)


def bundle(output: str, python: str | None = None, appimagetool: str | None = None,
           version: str = PYTHON) -> str:
    """Writes the AppImage into OUTPUT; returns its path."""
    if not os.path.isfile(ICON):
        raise OSError(f"there is no icon {ICON}")
    python = python or python_appimage(version)
    appimagetool = appimagetool or download(
        APPIMAGETOOL, os.path.join(cache_dir(), os.path.basename(APPIMAGETOOL)))
    path = os.path.join(output, name())
    with tempfile.TemporaryDirectory() as tmp:
        appdir = extract(python, tmp)
        make_appdir(appdir, bundle_zip().built_from())
        open_to_all(appdir)
        #  (without FUSE, as in a container, the tool runs extracted)
        env = dict(os.environ, ARCH=ARCH, APPIMAGE_EXTRACT_AND_RUN="1")
        subprocess.run([os.path.abspath(appimagetool), "--no-appstream",
                        appdir, path + ".tmp"], check=True, env=env)
    os.replace(path + ".tmp", path)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tools/bundle-appimage.py",
        description=f"Make an AppImage of the program, for Linux: {name()}, "
                    "with a Python of its own.")
    parser.add_argument("-o", "--output", metavar="FOLDER", default=None,
                        help="the folder to write it in (default: dist, in the "
                             "program's folder)")
    parser.add_argument("--python", metavar="APPIMAGE",
                        help="the Python AppImage to use (default: one of "
                             "python-appimage, downloaded)")
    parser.add_argument("--python-version", metavar="VERSION", default=PYTHON,
                        help=f"the version of Python to download (default: {PYTHON})")
    parser.add_argument("--appimagetool", metavar="APPIMAGE",
                        help="the appimagetool to use (default: downloaded)")
    args = parser.parse_args(argv)
    if not sys.platform.startswith("linux"):
        sys.exit("bundle-appimage.py: AppImages are made on Linux")
    if args.output is None:
        args.output = DIST
        os.makedirs(DIST, exist_ok=True)
    elif not os.path.isdir(args.output):
        sys.exit(f"bundle-appimage.py: there is no folder {args.output}")
    try:
        path = bundle(args.output, args.python, args.appimagetool, args.python_version)
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as e:
        sys.exit(f"bundle-appimage.py: {e}")
    print(f"Wrote {path} ({os.path.getsize(path) / 1e6:.1f} MB).")


if __name__ == "__main__":
    main()
