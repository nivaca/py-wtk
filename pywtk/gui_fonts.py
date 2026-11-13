# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""The fonts of the window, which the user can change.

Ctrl and + or - make all the text larger or smaller, Ctrl and 0 brings back
the usual fonts (Command instead of Ctrl on macOS), and the Settings
dialogue chooses the fonts and their sizes.  The choice is kept for next
time in the section [fonts] of the configuration file: only what differs
from the usual fonts is written.

Every widget uses a named Tk font, so a change reaches all open windows at
once, and <<FontsChanged>> is sent for what derives fonts of its own (the
headings of the entry).  There are two kinds of text:

* the entries, in TEXT, which should be a fixed-width font, as tables are
  laid out in columns;
* the window's own text (labels, buttons, menus, the contents), in Tk's
  standard fonts (TkDefaultFont ...), whose family and size change together.
"""

from __future__ import annotations

import re
import subprocess
import sys
from tkinter import font

from .settings import BY_NAME

#  The usual fixed-width font: the first of these that is installed
MONOSPACE = ("DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono",
             "Menlo", "Consolas", "Courier New", "Courier")
MIN_SIZE, MAX_SIZE = 6, 40

#  Tk's standard fonts, which ttk widgets, lists and menus use
UI_FONTS = ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
            "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont")

KEYS = ("text_family", "text_size", "ui_family", "ui_size")


def _size(font_name: str) -> int:
    """The size in points of a named font (Tk gives pixels as negative
    numbers; they are close enough)."""
    return abs(font.nametofont(font_name).actual()["size"]) or 10


def _clamp(size: int) -> int:
    return max(MIN_SIZE, min(MAX_SIZE, size))


#  Tk's scaling (pixels per point) at 96 DPI, which the default sizes of
#  windows, in pixels, are made for
BASE_SCALING = 96 / 72


def _x_resources(root) -> str:
    """The X resources of ROOT's display (what xrdb -query shows), read with
    libX11 or else xrdb; empty if neither works."""
    try:
        import ctypes
        import ctypes.util
        x11 = ctypes.CDLL(ctypes.util.find_library("X11") or "libX11.so.6")
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XResourceManagerString.argtypes = [ctypes.c_void_p]
        x11.XResourceManagerString.restype = ctypes.c_char_p
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        display = x11.XOpenDisplay(root.winfo_screen().encode())
        if display:
            try:
                return (x11.XResourceManagerString(display) or b"").decode("latin-1")
            finally:
                x11.XCloseDisplay(display)
    except (OSError, AttributeError, ValueError):
        pass
    try:
        return subprocess.run(["xrdb", "-query"], capture_output=True, text=True,
                              timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def fit_scaling(root):
    """Makes Tk's points as large as the desktop asks.  On X11 (and XWayland)
    Tk 8.6 works its scaling out from the size the X server gives the screen,
    which ignores the desktop's own scaling: Plasma, GNOME and others say it
    in the resource Xft.dpi (192 at 200%), so on a hi-res display, with
    scaling, everything came out very small (the AppImage's Tk is 8.6; Tk 9
    reads Xft.dpi itself, and this changes nothing).  Done once for each Tk
    (ROOT may be any of its widgets)."""
    root = root._root()             # (one scaling for each Tk)
    if getattr(root, "_py_wtk_scaled", False):
        return
    root._py_wtk_scaled = True
    if root.tk.call("tk", "windowingsystem") != "x11":
        return
    m = re.search(r"^Xft\.dpi:\s*([0-9]+(?:\.[0-9]+)?)\s*$", _x_resources(root), re.M)
    if not (m and 48 <= float(m[1]) <= 960):
        return
    scaling = float(m[1]) / 72
    if abs(scaling - float(root.tk.call("tk", "scaling"))) < 0.01:
        return
    root.tk.call("tk", "scaling", scaling)
    #  Tk 8.6 gives its standard fonts in pixels (-12), which do not follow
    #  the scaling: they are given again in points, as at 96 DPI (9)
    for name in font.names(root):
        if name.startswith("Tk"):
            f = font.nametofont(name, root)
            if int(f.cget("size")) < 0:
                f.configure(size=max(1, round(-int(f.cget("size")) / BASE_SCALING)))


def scale_factor(root) -> float:
    """How many of ROOT's pixels make one pixel at 96 DPI (1 or more)."""
    fit_scaling(root)
    return max(1.0, float(root.tk.call("tk", "scaling")) / BASE_SCALING)


def scaled(root, geometry: str) -> str:
    """GEOMETRY ("WIDTHxHEIGHT", in pixels at 96 DPI) for ROOT's scaling."""
    factor = scale_factor(root)
    w, h = (int(n) for n in geometry.split("x"))
    return f"{round(w * factor)}x{round(h * factor)}"


class Fonts:
    """The fonts of one Tk application.  Use `Fonts.of(widget, settings)`,
    which makes them once."""

    @classmethod
    def of(cls, widget, settings=None) -> "Fonts":
        root = widget._root()
        fonts = getattr(root, "_py_wtk_fonts", None)
        if fonts is None:
            fonts = root._py_wtk_fonts = cls(root, settings)
        return fonts

    def __init__(self, root, settings):
        fit_scaling(root)               # (before any font is measured)
        self.root = root
        self.settings = settings
        installed = set(font.families(root))
        ui_size = _size("TkDefaultFont")
        self.defaults = {
            "text_family": next((f for f in MONOSPACE if f in installed),
                                font.nametofont("TkFixedFont").actual()["family"]),
            "text_size": BY_NAME["fonts.text_size"].default,
            "ui_family": font.nametofont("TkDefaultFont").actual()["family"],
            "ui_size": ui_size,
        }
        #  how much larger or smaller than TkDefaultFont each standard font
        #  is, which is kept when the size changes
        self.ui_offsets = {name: _size(name) - ui_size for name in UI_FONTS}
        self.values = dict(self.defaults)
        self.values.update(self.load())
        self.text = font.Font(root, name="PyWtkText", exists=False)
        self._fixed_families: list[str] | None = None
        self.apply()
        mod = "Command" if sys.platform == "darwin" else "Control"
        for keys, step in ((("plus", "equal", "KP_Add"), 1),
                           (("minus", "KP_Subtract"), -1),
                           (("0", "KP_0"), 0)):
            for key in keys:
                root.bind_all(f"<{mod}-{key}>", lambda e, step=step: self.key(step))

    # ---- settings ------------------------------------------------------- #
    def load(self) -> dict:
        """The saved choices (empty family or size 0: the usual one)."""
        st = self.settings
        out = {}
        for key in KEYS:
            value = st[f"fonts.{key}"]
            if key.endswith("size") and value:
                out[key] = _clamp(value)
            elif key.endswith("family") and value:
                out[key] = value
        return out

    def save(self):
        """Keeps the choices that differ from the usual ones (the others are
        removed from the file)."""
        st = self.settings
        for key in KEYS:
            if self.values[key] != self.defaults[key]:
                st.set(f"fonts.{key}", self.values[key])
            else:
                st.reset(f"fonts.{key}")
        try:
            st.save()
        except OSError:
            pass                        # (then they last for this session)

    def apply(self):
        v = self.values
        self.text.configure(family=v["text_family"], size=v["text_size"])
        for name, offset in self.ui_offsets.items():
            font.nametofont(name).configure(family=v["ui_family"],
                                            size=_clamp(v["ui_size"] + offset))
        #  (for what derives fonts of its own, and windows that fit their text)
        self.root.event_generate("<<FontsChanged>>", when="tail")

    def reload(self):
        """The fonts as the settings now say (after the Settings dialogue)."""
        self.values = dict(self.defaults)
        self.values.update(self.load())
        self.apply()

    def set(self, **values):
        """Changes some of the fonts (the keys of KEYS), and keeps it."""
        for key, value in values.items():
            if key.endswith("size"):
                self.values[key] = _clamp(value) if value else self.defaults[key]
            else:
                self.values[key] = value or self.defaults[key]
        self.apply()
        self.save()

    def zoom(self, step: int):
        """All the text STEP points larger (or smaller)."""
        self.set(text_size=self.values["text_size"] + step,
                 ui_size=self.values["ui_size"] + step)

    def reset(self):
        self.set(**self.defaults)

    def key(self, step: int):
        if step:
            self.zoom(step)
        else:
            self.reset()
        return "break"

    # ---- choices -------------------------------------------------------- #
    def fixed_families(self) -> list[str]:
        """The installed fixed-width fonts (found once: it takes a moment).
        Left out: vertical-text variants, the X11 cursor font, icon fonts."""
        if self._fixed_families is None:
            found = set()
            for family in font.families(self.root):
                low = family.lower()
                if family.startswith("@") or low == "cursor" or "symbol" in low:
                    continue
                if font.Font(self.root, family=family, size=10).metrics("fixed"):
                    found.add(family)
            found.add(self.values["text_family"])
            self._fixed_families = sorted(found, key=str.casefold)
        return self._fixed_families

    def all_families(self) -> list[str]:
        return sorted({f for f in font.families(self.root) if not f.startswith("@")},
                      key=str.casefold)
