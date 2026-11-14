# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Copying to the system clipboard, for the terminal interface (tui.py):
curses cannot reach it, so the text goes through each system's clipboard
program, or else through the terminal itself (OSC 52)."""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys


def _programs() -> list[list[str]]:
    """The commands that write the clipboard here, in the order they are
    tried."""
    if sys.platform == "darwin":
        return [["pbcopy"]]
    if sys.platform == "win32":
        return [["clip"]]
    found = []
    if os.environ.get("WAYLAND_DISPLAY"):
        found.append(["wl-copy"])
    if os.environ.get("DISPLAY"):
        found += [["xclip", "-selection", "clipboard"],
                  ["xsel", "--clipboard", "--input"]]
    return found


def copy(text: str) -> bool:
    """Puts TEXT in the clipboard; returns whether a clipboard program took it
    (if not, the terminal is asked to, which many do)."""
    for command in _programs():
        if shutil.which(command[0]) is None:
            continue
        try:
            subprocess.run(command, input=text.encode(), timeout=5, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    _osc52(text)
    return False


def _osc52(text: str):
    """Asks the terminal to put TEXT in the clipboard (inside tmux too, which
    passes it on when set to)."""
    code = base64.b64encode(text.encode()).decode()
    sequence = f"\x1b]52;c;{code}\x07"
    if os.environ.get("TMUX"):
        sequence = "\x1bPtmux;" + sequence.replace("\x1b", "\x1b\x1b") + "\x1b\\"
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(sequence)
    except OSError:
        sys.stdout.write(sequence)
        sys.stdout.flush()
