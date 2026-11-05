# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""The name and version of py-wtk, the commit it was made from, and the
Python it needs.

The launchers read this module before the rest of the program, so it must
stay readable by old versions of Python (to say that they are too old).
"""

import os
import re
import subprocess
import sys

from . import __version__

NAME = "py-wtk"
VERSION = __version__
MIN_PYTHON = (3, 11)            # (tomllib)

#  The program's folder (that of the launchers, above this package)
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#  The commit the program was made from, written into the zip and the
#  AppImage by the bundle scripts (a clone asks git instead)
COMMIT_FILE = "COMMIT"


def check_python():
    """Stops with a clear message if this Python is too old.  The launchers
    call this before importing anything that needs a recent Python."""
    if sys.version_info < MIN_PYTHON:
        need = ".".join(map(str, MIN_PYTHON))
        sys.exit("%s needs Python %s or later; this is Python %s."
                 % (NAME, need, sys.version.split()[0]))


def commit(folder=HERE):
    """The commit (its full hash) of the program in FOLDER: that of its
    COMMIT_FILE or, in a clone, git's; None if neither says."""
    try:
        with open(os.path.join(folder, COMMIT_FILE), encoding="ascii") as f:
            text = f.read().strip()
    except (OSError, ValueError):
        text = _git_commit(folder)
    return text if text and re.fullmatch("[0-9a-f]{40}", text) else None


def _git_commit(folder):
    """HEAD of the git repository whose top is FOLDER (not of one that only
    contains it), or None."""
    try:
        out = subprocess.run(
            ["git", "-C", folder, "rev-parse", "--show-toplevel", "HEAD"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    lines = out.stdout.split()
    if out.returncode != 0 or len(lines) != 2:
        return None
    if os.path.realpath(lines[0]) != os.path.realpath(folder):
        return None
    return lines[1]


#  What the program is, after its name and version in titles: "py-wtk 1.0:
#  the English Wiktionary"
TAGLINE = "the English Wiktionary"


def title():
    """'py-wtk 1.0: the English Wiktionary', for titles and headers."""
    return "%s %s: %s" % (NAME, VERSION, TAGLINE)


def describe():
    """'1.0', or '1.0 (abc1234)' when the commit is known."""
    hash_ = commit()
    return "%s (%s)" % (VERSION, hash_[:7]) if hash_ else VERSION
