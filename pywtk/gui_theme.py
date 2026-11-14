# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""The light or dark look of the window (and its dialogues).

Both looks are drawn with Tk's "clam" theme in colours of their own, except
light mode on Windows and macOS, which keeps the system's theme (Linux has
none worth keeping: Tk's "default" is that of the nineties).  The choice is
kept for next time in the section [appearance] of the configuration file
(dark_mode = true or false; left out: light), and changes all the open
windows at once: the ttk widgets through their style, the others (texts,
lists, menus) through Tk's option database for those made later, and one
by one for those already there.  Then the event <<ThemeChanged>> is sent
to the main window, for what has colours of its own (the entry's text).

Some widgets use a style of their own, which follows the look:
Muted.TLabel (hints, in grey), Error.TLabel (problems), Link.TLabel,
Accent.TButton (the main button of a window, in the colour of the accent)
and Flat.Toolbutton (a button with no border).
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from . import config
from .settings import render as render_config

SECTION = "appearance"
OWN_THEME = "clam"

#  The colours of the two looks: the window is its panels; what is typed or
#  read (the entry, the fields, the contents) is on its "field"
DARK = {
    "background": "#242428", "foreground": "#e8e6e1",
    "field": "#1b1b1d", "select": "#3a5a8c", "select_fg": "#ffffff",
    "muted": "#9a9890", "error": "#ff8a80", "border": "#3a3a3e",
    "active": "#34343a", "disabled": "#6b6a66", "link": "#8fb8e0",
    "accent": "#8fb8e0", "accent_fg": "#1b1b1d", "accent_active": "#a8c8ea",
    "focus": "#a8c8ea",
}
LIGHT = {
    "background": "#f1efe9", "foreground": "#1d1d1b",
    "field": "#fbfaf7", "select": "#2f5d9a", "select_fg": "#ffffff",
    "muted": "#6b6a66", "error": "#b00020", "border": "#cfcbc2",
    "active": "#e4e1d9", "disabled": "#a3a19b", "link": "#1f5fbf",
    "accent": "#1f5fbf", "accent_fg": "#fbfaf7", "accent_active": "#2f6fcf",
    "focus": "#4f7fcf",
}


class Theme:
    """The look of one Tk application.  Use `Theme.of(widget)`, which makes
    it once (and applies the saved choice)."""

    @classmethod
    def of(cls, widget) -> "Theme":
        root = widget._root()
        theme = getattr(root, "_py_wtk_theme", None)
        if theme is None:
            theme = root._py_wtk_theme = cls(root)
        return theme

    def __init__(self, root):
        self.root = root
        self.style = ttk.Style(root)
        self.usual_theme = self.style.theme_use()
        #  (the systems with a theme of their own keep it in light mode)
        self.native = sys.platform in ("win32", "darwin") and \
            self.usual_theme not in ("default", "classic", "alt", "clam")
        self.usual = self._usual_colours()
        self.ticks = None               # (the images of the check boxes)
        self.dark = config.section(SECTION).get("dark_mode") is True
        self.apply()

    def _usual_colours(self) -> dict:
        """The colours of the Tk widgets, as the system gives them."""
        text = tk.Text(self.root)
        listbox = tk.Listbox(self.root)
        try:
            return {
                "background": self.root.cget("background"),
                "field": text.cget("background"),
                "foreground": text.cget("foreground"),
                "insert": text.cget("insertbackground"),
                "select": text.cget("selectbackground"),
                "select_fg": text.cget("selectforeground"),
                "list": listbox.cget("background"),
                "list_fg": listbox.cget("foreground"),
                "border": text.cget("highlightbackground"),
                "focus": text.cget("highlightcolor")}
        finally:
            text.destroy()
            listbox.destroy()

    # ---- choosing ------------------------------------------------------- #
    def set(self, dark: bool, save: bool = True):
        """Changes the look and (with SAVE) keeps the choice."""
        self.dark = bool(dark)
        self.apply()
        if save:
            try:
                config.update({SECTION: {"dark_mode": self.dark}}, render=render_config)
            except (OSError, config.ConfigError):
                pass                    # (then it lasts for this session)

    # ---- applying ------------------------------------------------------- #
    @property
    def palette(self) -> dict:
        return DARK if self.dark else LIGHT

    def apply(self):
        p = self.palette
        if self.dark or not self.native:
            self.style.theme_use(OWN_THEME)
            self._styles(p)
            colours = self._tk_colours(p)
        else:
            self.style.theme_use(self.usual_theme)
            colours = dict(self.usual)
        self.style.configure("Muted.TLabel", foreground=p["muted"])
        self.style.configure("Error.TLabel", foreground=p["error"])
        self.style.configure("Link.TLabel", foreground=p["link"])
        self.colours = colours
        self._options(colours)
        self._recolour(self.root, colours)
        #  (for what has colours of its own, such as the entry's text)
        self.root.event_generate("<<ThemeChanged>>", when="tail")

    def _styles(self, d: dict):
        """The ttk styles of clam, in the colours D."""
        s = self.style
        s.configure(".", background=d["background"], foreground=d["foreground"],
                    fieldbackground=d["field"], bordercolor=d["border"],
                    lightcolor=d["background"], darkcolor=d["background"],
                    troughcolor=d["field"], selectbackground=d["select"],
                    selectforeground=d["select_fg"], insertcolor=d["foreground"],
                    arrowcolor=d["foreground"], indicatorbackground=d["field"],
                    indicatorforeground=d["foreground"], focuscolor=d["focus"])
        s.map(".", foreground=[("disabled", d["disabled"])],
              background=[("active", d["active"])])
        s.configure("TButton", background=d["active"], padding=(10, 3),
                    lightcolor=d["active"], darkcolor=d["active"], anchor="center")
        s.map("TButton", background=[("pressed", d["border"]), ("active", d["border"])],
              lightcolor=[("pressed", d["border"]), ("active", d["border"])],
              darkcolor=[("pressed", d["border"]), ("active", d["border"])],
              bordercolor=[("focus", d["focus"])])
        #  the main button: filled with the accent
        s.configure("Accent.TButton", background=d["accent"], foreground=d["accent_fg"],
                    bordercolor=d["accent"], lightcolor=d["accent"], darkcolor=d["accent"])
        hover = [("disabled", d["active"]), ("pressed", d["accent_active"]),
                 ("active", d["accent_active"])]
        s.map("Accent.TButton", background=hover, lightcolor=hover, darkcolor=hover,
              bordercolor=[("disabled", d["border"]), ("focus", d["focus"])],
              foreground=[("disabled", d["disabled"])])
        #  a button with no border (like the dark mode one), only a shade under
        #  the mouse
        s.configure("Flat.Toolbutton", background=d["background"], relief="flat",
                    borderwidth=0)
        s.map("Flat.Toolbutton", relief=[("selected", "flat"), ("pressed", "flat")],
              background=[("pressed", d["border"]), ("active", d["active"]),
                          ("selected", d["background"])])
        for name in ("TEntry", "TCombobox", "TSpinbox"):
            s.configure(name, padding=(4, 2), lightcolor=d["field"], darkcolor=d["field"])
            s.map(name, fieldbackground=[("readonly", d["field"]),
                                         ("disabled", d["background"])],
                  foreground=[("disabled", d["disabled"])],
                  selectbackground=[("focus", d["select"])],
                  bordercolor=[("focus", d["focus"])],
                  lightcolor=[("focus", d["focus"])])
        #  (clam sets these widgets' own colours, which "." does not change;
        #  the boxes are sized from the text)
        size = max(10, int(tkfont.nametofont("TkDefaultFont").metrics("linespace") * 0.7))
        for name in ("TCheckbutton", "TRadiobutton"):
            s.configure(name, indicatorbackground=d["field"],
                        indicatorforeground=d["accent"], indicatorsize=size,
                        upperbordercolor=d["border"], lowerbordercolor=d["border"])
            s.map(name, indicatorbackground=[("disabled", d["background"]),
                                             ("pressed", d["active"])])
        self._ticks(d, size)
        for name in ("TCombobox", "TSpinbox", "TScrollbar"):
            s.configure(name, background=d["active"], arrowcolor=d["foreground"],
                        troughcolor=d["field"], bordercolor=d["border"],
                        lightcolor=d["active"], darkcolor=d["active"])
            s.map(name, background=[("active", d["border"]), ("pressed", d["border"]),
                                    ("readonly", d["active"])],
                  arrowcolor=[("disabled", d["disabled"])])
        s.configure("TScrollbar", troughcolor=d["background"], bordercolor=d["background"],
                    gripcount=0, arrowsize=12)
        s.configure("TNotebook", background=d["background"])
        s.configure("TNotebook.Tab", background=d["background"])
        s.map("TNotebook.Tab", background=[("selected", d["active"])])
        #  the contents (a tree on the "field", like the entry beside it)
        s.configure("Treeview", background=d["field"], fieldbackground=d["field"],
                    foreground=d["foreground"], bordercolor=d["border"],
                    lightcolor=d["field"], darkcolor=d["field"])
        s.map("Treeview", background=[("selected", d["select"])],
              foreground=[("selected", d["select_fg"])])
        s.configure("TPanedwindow", background=d["background"])
        s.configure("Sash", background=d["background"], lightcolor=d["border"],
                    darkcolor=d["border"], bordercolor=d["border"],
                    gripcount=0, sashthickness=6)

    def _ticks(self, d: dict, size: int):
        """Check boxes with a tick (clam draws a cross): images in the
        colours D, made once and drawn again when they change."""
        s = self.style
        if self.ticks is None:
            self.ticks = {state: tk.PhotoImage(master=self.root)
                          for state in ("off", "on", "off_disabled", "on_disabled")}
            t = self.ticks
            s.element_create("Tick.indicator", "image", t["off"],
                             ("selected", "disabled", t["on_disabled"]),
                             ("disabled", t["off_disabled"]),
                             ("selected", t["on"]), sticky="", padding=0)
            s.layout("TCheckbutton", [("Checkbutton.padding", {
                "sticky": "nswe", "children": [
                    ("Tick.indicator", {"side": "left", "sticky": ""}),
                    ("Checkbutton.focus", {
                        "side": "left", "sticky": "w", "children": [
                            ("Checkbutton.label", {"sticky": "nswe"})]})]})])
            s.configure("TCheckbutton", padding=2)
        for state, (fill, edge, mark) in {
                "off": (d["field"], d["border"], None),
                "on": (d["accent"], d["accent"], d["accent_fg"]),
                "off_disabled": (d["background"], d["border"], None),
                "on_disabled": (d["active"], d["border"], d["disabled"]),
                }.items():
            _draw_box(self.ticks[state], size, fill, edge, mark, d["background"])

    @staticmethod
    def _tk_colours(d: dict) -> dict:
        return {"background": d["background"], "field": d["field"],
                "foreground": d["foreground"], "insert": d["foreground"],
                "select": d["select"], "select_fg": d["select_fg"],
                "list": d["field"], "list_fg": d["foreground"],
                "border": d["border"], "focus": d["border"]}

    def _options(self, c: dict):
        """The colours of the Tk widgets made from now on (also the lists of
        the comboboxes)."""
        add = self.root.option_add
        for cls in ("Toplevel", "Tk", "Frame", "Canvas", self.root.winfo_class()):
            add(f"*{cls}.background", c["background"], "interactive")
        for cls, bg, fg in (("Text", c["field"], c["foreground"]),
                            ("Listbox", c["list"], c["list_fg"])):
            add(f"*{cls}.background", bg, "interactive")
            add(f"*{cls}.foreground", fg, "interactive")
            add(f"*{cls}.selectBackground", c["select"], "interactive")
            add(f"*{cls}.selectForeground", c["select_fg"], "interactive")
        add("*Text.insertBackground", c["insert"], "interactive")
        add("*Text.highlightBackground", c["border"], "interactive")
        add("*Text.highlightColor", c["focus"], "interactive")
        add("*Label.background", c["background"], "interactive")
        add("*Label.foreground", c["foreground"], "interactive")
        add("*TCombobox*Listbox.background", c["list"], "interactive")
        add("*TCombobox*Listbox.foreground", c["list_fg"], "interactive")
        #  (the menu bar, its menus and the menu of a right click)
        for option, value in self._menu_colours(c).items():
            add(f"*Menu.{option}", value, "interactive")

    def _menu_colours(self, c: dict) -> dict:
        """The colours of the menus: those of the window, and of a selection
        for the item pointed at."""
        colours = {"background": c["background"], "foreground": c["foreground"],
                   "activeBackground": c["select"], "activeForeground": c["select_fg"]}
        if self.dark or not self.native:
            colours["disabledForeground"] = self.palette["disabled"]
            colours["selectColor"] = c["foreground"]  # (the ticks of check items)
        return colours

    def _recolour(self, widget, c: dict):
        """The colours of the Tk widgets already there."""
        cls = widget.winfo_class()
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            cls = "Toplevel"            # (whatever its class, as py-wtk)
        try:
            if cls in ("Toplevel", "Frame", "Canvas"):
                widget.configure(background=c["background"])
                if cls == "Canvas":
                    widget.configure(highlightbackground=c["background"])
            elif cls == "Text":
                widget.configure(background=c["field"], foreground=c["foreground"],
                                 insertbackground=c["insert"],
                                 selectbackground=c["select"],
                                 selectforeground=c["select_fg"],
                                 inactiveselectbackground=c["select"],
                                 highlightbackground=c["border"],
                                 highlightcolor=c["focus"])
            elif cls == "Listbox":
                widget.configure(background=c["list"], foreground=c["list_fg"],
                                 selectbackground=c["select"],
                                 selectforeground=c["select_fg"])
            elif cls == "Label":
                widget.configure(background=c["background"], foreground=c["foreground"])
            elif cls == "Menu":
                widget.configure(**{option.lower(): value for option, value
                                    in self._menu_colours(c).items()})
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._recolour(child, c)


def _draw_box(image: tk.PhotoImage, size: int, fill: str, edge: str,
              mark: str | None, around: str):
    """A check box of SIZE pixels in IMAGE: filled with FILL, its edge EDGE
    (its corners in AROUND, a little round), and a tick in MARK; on its
    right, a space before the label."""
    image.blank()
    image.config(width=size + max(4, size // 3), height=size)
    image.put(edge, to=(0, 0, size, size))
    image.put(fill, to=(1, 1, size - 1, size - 1))
    for x, y in ((0, 0), (size - 1, 0), (0, size - 1), (size - 1, size - 1)):
        image.put(around, to=(x, y, x + 1, y + 1))
    if mark is None:
        return
    #  the tick: two strokes, from the left down to the bottom, and up to the right
    pen = max(2, round(size / 7))
    points = [(0.22, 0.52), (0.42, 0.72), (0.80, 0.30)]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        steps = size * 2
        for i in range(steps + 1):
            x = round((x1 + (x2 - x1) * i / steps) * size - pen / 2)
            y = round((y1 + (y2 - y1) * i / steps) * size - pen / 2)
            image.put(mark, to=(x, y, x + pen, y + pen))
