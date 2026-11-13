# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""py-wtk-gui — a Tkinter window for browsing the English Wiktionary.

    py-wtk-gui            # empty window, type a word in the search box
    py-wtk-gui rosa       # open "rosa" directly
    py-wtk-gui rosa -l la # Latin only

Double-click any word in an entry to look it up.
"""

from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from .api import NetworkError, NotFound, entry_target, page_url, search, suggestions
from .common import (History, add_lookup_args, cache_summary, clear_cache, link_description,
                     network_message, no_language_message, open_in_browser, plural,
                     render_languages)
from .entry import Language, Options, language_sections
from .gui_fonts import Fonts, scale_factor, scaled
from .gui_theme import DARK, LIGHT, Theme
from .render import Rendered
from .settings import BY_NAME, Setting, Settings
from .text import styled_segments
from .version import HERE, NAME, VERSION, describe, title

#  The colours of what is styled in an entry, in the light and dark looks
#  (the numbers are the ANSI colours render.Style gives: 32 examples,
#  33 sections, 34 and 35 subsections, 36 languages)
COLOURS = {
    False: {32: "#2e7d32", 33: "#9a6700", 34: "#1f5fbf", 35: "#8e24aa", 36: "#00796b",
            "dim": "#77756e", "match": "#ffe58a", "current": "#ffb347", "link": "#1f5fbf"},
    True: {32: "#7cc47f", 33: "#e0b050", 34: "#7aa7ff", 35: "#d48ae6", 36: "#4fd1c5",
           "dim": "#9a9890", "match": "#5c4d16", "current": "#8a5f10", "link": "#8fb8e0"},
}

#  The tags of the links of an entry (two, which side by side links take
#  turns with, so that they stay apart)
LINK_TAGS = ("href0", "href1")

#  The dark mode button: what a click does (no images, only letters that
#  the usual fonts have)
MOON = "\u263e"                 # ☾  (make it dark)
SUN = "\u2600"                  # ☀  (make it light)

KEYS_HELP = """\
Ctrl+L          Focus the search box (Down: suggestions)
Click a link    Open it (links out of Wiktionary: in the browser)
Double-click    Look up the clicked word
Ctrl+F  F3      Find in page / next match (Shift+F3: previous)
Ctrl+X C V      Cut / copy / paste (the Edit menu)
Alt+←  Alt+→    Back / forward
F5              Reload
Ctrl+ +  Ctrl+ − Larger / smaller text (Ctrl+0: the usual size)
Ctrl+,          Settings
Ctrl+Q          Quit

Click an item in the contents pane to jump to it."""


def selected(widget) -> bool:
    """Whether WIDGET (an entry or a text) has text selected."""
    try:
        if isinstance(widget, tk.Text):
            return bool(widget.tag_ranges("sel"))
        return isinstance(widget, (tk.Entry, ttk.Entry)) and widget.selection_present()
    except tk.TclError:
        return False


def editable(widget) -> bool:
    """Whether text can be typed in WIDGET (not in the entry, which is only
    read, nor in a list to choose from)."""
    if not isinstance(widget, (tk.Entry, ttk.Entry, tk.Text)):
        return False
    try:
        return str(widget.cget("state")) == "normal"
    except tk.TclError:
        return False


class App:
    def __init__(self, root: tk.Tk, word: str | None, lang: str | None,
                 dark: bool | None, size: int | None):
        self.root = root
        self.settings = st = Settings()
        self.client = st.client()
        self.word: str | None = None
        self.languages: list[Language] = []
        self.view: Rendered | None = None
        self.history: History[tuple[str, float]] = History()
        self.results: queue.Queue = queue.Queue()
        self.tickets: dict[str, int] = {}
        self.code_tags: dict[tuple[int, ...], str] = {}
        #  The links of the entry: their URLs by line (Tk's numbers), in order
        self.link_urls: dict[int, list[str]] = {}
        #  What the status line says of the link under the mouse, and what it
        #  said before (to put back)
        self.link_status: str | None = None
        self.status_before_link = ""
        self.tag_fonts: dict[tuple, tkfont.Font] = {}
        self.toc_items: dict[str, int] = {}
        self.toc_order: list[str] = []
        self.syncing = False
        self.render_chars = 0
        self.resize_job = None
        self.suggest_job = None
        self.matches: list[str] = []
        self.match_i = -1

        self.lang = tk.StringVar(value=lang or st["general.languages"])
        self.query = tk.StringVar(value=word or "")
        self.find_var = tk.StringVar()
        self.show_quotes = tk.BooleanVar(value=st["general.show_quotations"])
        self.show_tables = tk.BooleanVar(value=st["general.show_tables"])
        self.show_toc = tk.BooleanVar(value=st["gui.show_contents"])

        #  the look and the fonts, saved in [appearance] and [fonts]
        self.theme = Theme.of(root)
        if dark is not None:            # (--dark: only this time)
            self.theme.set(dark, save=False)
        self.dark = tk.BooleanVar(value=self.theme.dark)
        self.fonts = Fonts.of(root, st)
        if size:                        # (--size: only this time)
            self.fonts.values["text_size"] = size
            self.fonts.apply()
        self.font = self.fonts.text

        root.title(title())
        geometry = st["gui.window_geometry"] if st["gui.remember_window"] else ""
        try:
            root.geometry(geometry or scaled(root, "1150x780"))
        except tk.TclError:
            root.geometry(scaled(root, "1150x780"))
        root.minsize(*(int(n) for n in scaled(root, "600x400").split("x")))
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.build_menu()
        self.build_ui()
        self.restyle()
        self.bind_keys()
        root.bind("<<ThemeChanged>>", lambda e: self.restyle(), add="+")
        root.bind("<<FontsChanged>>", lambda e: (self.restyle(), self.on_resize()), add="+")
        root.after(50, self.poll)

        if word:
            root.after(100, lambda: self.open(word))
        else:
            self.welcome()
            self.search_entry.focus_set()
        if st.problems:
            root.after(300, lambda: messagebox.showwarning(
                "Settings", "Some settings were not valid and the usual values are used:\n\n"
                + "\n".join(st.problems), parent=root))
        elif st.messages:
            root.after(300, lambda: self.set_status(" ".join(st.messages)))

    # ------------------------------------------------------------ settings --
    def save_setting(self, name: str, value):
        self.settings.set(name, value)
        try:
            self.settings.save()
        except OSError as e:
            self.set_status(f"Could not save settings: {e}")

    def quit(self):
        if self.toc_shown():
            #  (kept in pixels at 96 DPI, as the window's other sizes)
            width = round(self.paned.sashpos(0) / scale_factor(self.root))
            if 120 <= width <= 700 and width != self.settings["gui.contents_width"]:
                self.save_setting("gui.contents_width", width)
        if self.settings["gui.remember_window"]:
            g = self.root.winfo_geometry()
            if self.root.state() == "normal" and g.split("+")[0] != "1x1":
                self.save_setting("gui.window_geometry", g.split("+")[0])
        self.root.destroy()

    def open_settings(self):
        SettingsDialog(self)

    def apply_settings(self, changed: set[str]):
        """Apply settings changed in the dialog (already saved)."""
        st = self.settings
        if "general.languages" in changed:
            self.lang.set(st["general.languages"])
        if "general.show_quotations" in changed:
            self.show_quotes.set(st["general.show_quotations"])
        if "general.show_tables" in changed:
            self.show_tables.set(st["general.show_tables"])
        if "appearance.dark_mode" in changed:
            self.dark.set(st["appearance.dark_mode"])
            self.theme.set(self.dark.get(), save=False)   # (already saved)
        if "gui.show_contents" in changed:
            self.show_toc.set(st["gui.show_contents"])
            self.toggle_toc(save=False)
        elif "gui.contents_width" in changed and self.show_toc.get():
            self.restore_sash()
        if "general.cache_days" in changed:
            self.client = st.client()
        if any(n.startswith("fonts.") for n in changed):
            self.fonts.reload()         # (sends <<FontsChanged>>: re-wraps the text)
        if changed & {"general.languages", "general.preferred_languages",
                      "general.show_quotations", "general.show_tables",
                      "general.show_translations", "general.hidden_sections",
                      "general.max_width", "gui.links"}:
            self.rerender(keep_position="general.languages" not in changed)

    # ------------------------------------------------------------------ UI --
    def build_menu(self):
        m = tk.Menu(self.root)
        f = tk.Menu(m, tearoff=False)
        f.add_command(label="Look up…", accelerator="Ctrl+L", command=self.focus_search)
        f.add_command(label="Open in browser", command=self.open_browser)
        f.add_separator()
        f.add_command(label="Settings…", accelerator="Ctrl+,", command=self.open_settings)
        f.add_separator()
        f.add_command(label="Quit", accelerator="Ctrl+Q", command=self.quit)
        m.add_cascade(label="File", menu=f)

        #  (the keys are Tk's own, in every box of text)
        e = tk.Menu(m, tearoff=False)
        e.config(postcommand=lambda: self.edit_states(e))
        for name, letter, event in (("Cut", "X", "<<Cut>>"), ("Copy", "C", "<<Copy>>"),
                                    ("Paste", "V", "<<Paste>>")):
            e.add_command(label=name, accelerator=f"Ctrl+{letter}",
                          command=lambda ev=event: self.edit_event(ev))
        m.add_cascade(label="Edit", menu=e)

        g = tk.Menu(m, tearoff=False)
        g.add_command(label="Back", accelerator="Alt+Left", command=self.back)
        g.add_command(label="Forward", accelerator="Alt+Right", command=self.forward)
        g.add_command(label="Reload", accelerator="F5", command=self.reload)
        g.add_separator()
        g.add_command(label="Find in page", accelerator="Ctrl+F", command=self.focus_find)
        m.add_cascade(label="Go", menu=g)

        v = tk.Menu(m, tearoff=False)
        v.add_checkbutton(label="Contents pane", variable=self.show_toc, command=self.toggle_toc)
        v.add_checkbutton(label="Quotations", variable=self.show_quotes, command=self.toggle_quotes)
        v.add_checkbutton(label="Tables", variable=self.show_tables, command=self.toggle_tables)
        v.add_separator()
        v.add_checkbutton(label="Dark mode", variable=self.dark, command=self.choose_dark)
        v.add_command(label="Larger text", accelerator="Ctrl++",
                      command=lambda: self.fonts.zoom(1))
        v.add_command(label="Smaller text", accelerator="Ctrl+-",
                      command=lambda: self.fonts.zoom(-1))
        v.add_command(label="Usual text size", accelerator="Ctrl+0", command=self.fonts.reset)
        m.add_cascade(label="View", menu=v)

        h = tk.Menu(m, tearoff=False)
        h.add_command(label="Keys", command=lambda: messagebox.showinfo("Keys", KEYS_HELP))
        h.add_command(label="About", command=lambda: messagebox.showinfo(
            "About py-wtk", f"{NAME} {describe()}\n\nThe English Wiktionary on your desktop.\n"
                            "Content from en.wiktionary.org (CC BY-SA).\n\n"
                            "By Nicolas Vaughan (nivaca@fastmail.com), Associate Professor\n"
                            "of Literature at the School of Arts and Humanities of the\n"
                            "Universidad de los Andes, Bogotá, Colombia."))
        m.add_cascade(label="Help", menu=h)
        self.root.config(menu=m)

    # The Edit menu acts on the box with the keyboard's focus (the search box,
    # the languages, or "Find in page"), or, for copying, on the entry, where
    # text is selected but not typed.
    def edit_widget(self, event: str):
        """The widget that EVENT (<<Cut>>, <<Copy>> or <<Paste>>) would act on,
        or None if it cannot now."""
        try:
            focus = self.root.focus_get()
        except (KeyError, tk.TclError):     # (in a combobox's list)
            focus = None
        if event == "<<Copy>>":
            for widget in (focus, self.text):
                if selected(widget):
                    return widget
            return None
        if not editable(focus):
            return None
        if event == "<<Cut>>":
            return focus if selected(focus) else None
        try:
            return focus if self.root.clipboard_get() else None
        except tk.TclError:                 # (the clipboard is empty)
            return None

    def edit_states(self, menu: tk.Menu):
        """Greys out what the Edit menu cannot do now."""
        for i, event in enumerate(("<<Cut>>", "<<Copy>>", "<<Paste>>")):
            menu.entryconfig(i, state="normal" if self.edit_widget(event) else "disabled")

    def edit_event(self, event: str):
        widget = self.edit_widget(event)
        if widget is None:
            return
        if widget is self.text and event == "<<Copy>>":
            self.copy()                     # (the entry is read-only: its own copy)
        else:
            widget.event_generate(event)

    def build_ui(self):
        root = self.root
        bar = ttk.Frame(root, padding=(6, 6, 6, 4))
        bar.pack(fill="x")
        # (the right-hand buttons first, so that they keep their room when the
        # window is narrow)
        ttk.Button(bar, text="⚙ Settings", command=self.open_settings).pack(side="right")
        ttk.Button(bar, text="Open in browser", command=self.open_browser).pack(side="right",
                                                                               padx=(0, 4))
        self.back_btn = ttk.Button(bar, text="◀", width=3, command=self.back)
        self.back_btn.pack(side="left")
        self.fwd_btn = ttk.Button(bar, text="▶", width=3, command=self.forward)
        self.fwd_btn.pack(side="left", padx=(2, 8))
        self.search_entry = ttk.Entry(bar, textvariable=self.query, width=28)
        self.search_entry.pack(side="left")
        ttk.Button(bar, text="Look up", style="Accent.TButton",
                   command=self.submit).pack(side="left", padx=(4, 12))
        ttk.Label(bar, text="Language:").pack(side="left")
        self.lang_box = ttk.Combobox(bar, textvariable=self.lang, width=16, values=["all"])
        self.lang_box.pack(side="left", padx=(4, 12))
        ttk.Checkbutton(bar, text="Quotations", variable=self.show_quotes,
                        command=self.toggle_quotes).pack(side="left")
        ttk.Checkbutton(bar, text="Tables", variable=self.show_tables,
                        command=self.toggle_tables).pack(side="left", padx=(6, 0))

        self.paned = ttk.PanedWindow(root, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        # contents
        self.toc_frame = ttk.Frame(self.paned)
        self.tree = ttk.Treeview(self.toc_frame, show="tree", selectmode="browse")
        tsb = ttk.Scrollbar(self.toc_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tsb.pack(side="right", fill="y")
        self.paned.add(self.toc_frame, weight=0)

        # entry text
        tf = ttk.Frame(self.paned)
        self.text = tk.Text(tf, wrap="none", undo=False, padx=14, pady=10,
                            borderwidth=0, highlightthickness=0, cursor="arrow",
                            font=self.font)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.text.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=lambda a, b: (vsb.set(a, b), self.on_scroll()),
                            xscrollcommand=hsb.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.paned.add(tf, weight=1)
        if not self.show_toc.get():
            self.paned.forget(self.toc_frame)
        self.root.after(10, self.restore_sash)

        # bottom: status, find, and the dark mode button (a moon to make the
        # window dark, a sun to make it light again; its name in the status
        # line while the mouse is over it)
        bottom = ttk.Frame(root, padding=(6, 3))
        bottom.pack(fill="x")
        self.dark_box = ttk.Checkbutton(bottom, variable=self.dark, style="Mode.Flat.Toolbutton",
                                        command=self.choose_dark)
        self.dark_box.pack(side="right", padx=(8, 0))
        self.dark.trace_add("write", lambda *a: self.show_dark())
        self.dark_box.bind("<Enter>", lambda e: self.name_dark(True))
        self.dark_box.bind("<Leave>", lambda e: self.name_dark(False))
        self.status = ttk.Label(bottom, text="", anchor="w")
        self.status.pack(side="left", fill="x", expand=True)
        ttk.Label(bottom, text="Find:").pack(side="left")
        self.find_entry = ttk.Entry(bottom, textvariable=self.find_var, width=22)
        self.find_entry.pack(side="left", padx=4)
        ttk.Button(bottom, text="▲", width=3, command=lambda: self.find_next(-1)).pack(side="left")
        ttk.Button(bottom, text="▼", width=3, command=lambda: self.find_next(1)).pack(side="left")
        self.find_count = ttk.Label(bottom, text="", width=12, anchor="e")
        self.find_count.pack(side="left")

        # suggestion dropdown (placed under the search box when needed)
        self.sugg = tk.Listbox(root, height=10, activestyle="dotbox", exportselection=False)

        # right-click menu
        self.ctx = tk.Menu(self.root, tearoff=False)

        self.update_nav_buttons()

    def bind_keys(self):
        r = self.root
        r.bind("<Control-l>", lambda e: self.focus_search())
        r.bind("<Control-f>", lambda e: self.focus_find())
        r.bind("<F3>", lambda e: self.find_next(1))
        r.bind("<Shift-F3>", lambda e: self.find_next(-1))
        r.bind("<Alt-Left>", lambda e: self.back())
        r.bind("<Alt-Right>", lambda e: self.forward())
        r.bind("<F5>", lambda e: self.reload())
        r.bind("<Control-q>", lambda e: self.quit())
        r.bind("<Control-comma>", lambda e: self.open_settings())
        # (Ctrl and + - 0 are bound by gui_fonts.Fonts, for all windows)

        e = self.search_entry
        e.bind("<Return>", lambda ev: self.submit())
        e.bind("<KeyRelease>", self.on_search_key)
        e.bind("<Down>", lambda ev: self.enter_suggestions())
        e.bind("<Escape>", lambda ev: self.hide_suggestions())
        e.bind("<FocusOut>", lambda ev: self.root.after(150, self.maybe_hide_suggestions))
        s = self.sugg
        s.bind("<Return>", lambda ev: self.pick_suggestion())
        s.bind("<ButtonRelease-1>", lambda ev: self.pick_suggestion())
        s.bind("<Escape>", lambda ev: (self.hide_suggestions(), self.search_entry.focus_set()))
        s.bind("<Up>", lambda ev: self.suggestion_up())

        self.lang_box.bind("<<ComboboxSelected>>", lambda ev: self.on_lang())
        self.lang_box.bind("<Return>", lambda ev: self.on_lang())
        self.find_entry.bind("<Return>", lambda ev: self.find_next(1))
        self.find_entry.bind("<Shift-Return>", lambda ev: self.find_next(-1))
        self.find_entry.bind("<Escape>", lambda ev: self.clear_find())
        self.find_var.trace_add("write", lambda *a: self.compute_matches())

        self.tree.bind("<<TreeviewSelect>>", self.on_toc_select)
        self.text.bind("<Configure>", self.on_resize)
        self.text.bind("<Double-Button-1>", self.on_double_click)
        for tag in LINK_TAGS:
            self.text.tag_bind(tag, "<Enter>", lambda e: self.link_hover(True))
            self.text.tag_bind(tag, "<Leave>", lambda e: self.link_hover(False))
            self.text.tag_bind(tag, "<ButtonRelease-1>", self.link_click)
        self.text.bind("<Button-3>", self.on_context)
        self.text.bind("<Control-c>", lambda e: self.copy())

    # -------------------------------------------------------------- the look --
    def colours(self) -> dict:
        return COLOURS[self.theme.dark]

    def restyle(self):
        """The entry's own colours and fonts, after a change of the look or of
        the fonts (the rest of the window follows the theme by itself)."""
        c = self.colours()
        for key in list(self.tag_fonts):
            self.font_for(*key)
        for codes, tag in self.code_tags.items():
            self.configure_tag(tag, codes)
        t = self.text
        t.tag_configure("match", background=c["match"])
        t.tag_configure("current", background=c["current"])
        t.tag_configure("link", foreground=c["link"], underline=True)
        for tag in LINK_TAGS:
            t.tag_configure(tag, foreground=c["link"])
        t.tag_configure("hover", underline=True)
        t.tag_configure("welcome", foreground=c["dim"])
        self.raise_tags()
        self.show_dark()
        #  The contents' rows, as tall as their text: ttk gives them a fixed
        #  number of pixels, which neither the size of the text nor the
        #  display's scaling (Tk 8.6) would change
        line = tkfont.nametofont("TkDefaultFont").metrics("linespace")
        ttk.Style(self.root).configure("Treeview", rowheight=line + max(2, line // 5))

    def raise_tags(self):
        """Puts the links over the styles of the text, and the matches and the
        selection over everything."""
        for tag in LINK_TAGS + ("hover", "match", "current", "sel"):
            self.text.tag_raise(tag)

    def choose_dark(self):
        self.theme.set(self.dark.get(), save=False)
        self.save_setting("appearance.dark_mode", self.dark.get())

    def show_dark(self):
        """The moon or the sun, larger than the text (each look has its own
        styles, so this is done again when it changes)."""
        size = tkfont.nametofont("TkDefaultFont").actual("size")
        ttk.Style().configure("Mode.Flat.Toolbutton", padding=(6, 0),
                              font=("TkDefaultFont", round(abs(size) * 1.5)))
        self.dark_box.config(text=SUN if self.dark.get() else MOON)

    def name_dark(self, shown: bool):
        """The name of the dark mode button, in the status line while the mouse
        is over it (and what was there, after)."""
        name = "Light mode" if self.dark.get() else "Dark mode"
        if shown:
            self._status_before = self.status.cget("text")
            self.status.config(text=name)
        elif self.status.cget("text") in ("Dark mode", "Light mode"):
            self.status.config(text=getattr(self, "_status_before", ""))

    def font_for(self, bold=False, italic=False, underline=False, bigger=0) -> tkfont.Font:
        """A font for the entry's headings, derived from the entry font."""
        key = (bold, italic, underline, bigger)
        f = self.tag_fonts.get(key)
        if f is None:
            f = self.tag_fonts[key] = tkfont.Font(self.root)
        base = self.font.actual()
        f.configure(family=base["family"], size=abs(base["size"]) + bigger,
                    weight="bold" if bold else "normal",
                    slant="italic" if italic else "roman", underline=underline)
        return f

    def configure_tag(self, tag: str, codes: tuple[int, ...]):
        p = self.colours()
        bold = 1 in codes
        bigger = 0
        if bold and 4 in codes:      # page title
            bigger = 6
        elif bold and 36 in codes:   # language heading
            bigger = 3
        elif bold and 33 in codes:   # Etymology / Noun / ...
            bigger = 1
        font = self.font_for(bold, 3 in codes, 4 in codes and not bigger, bigger)
        fg = next((p[c] for c in codes if c in p), None)
        if 2 in codes:
            fg = p["dim"]
        self.text.tag_configure(tag, font=font, foreground=fg or "")

    def tag_for(self, codes: tuple[int, ...]) -> str | None:
        if not codes:
            return None
        key = tuple(sorted(set(codes)))
        tag = self.code_tags.get(key)
        if tag is None:
            tag = "s" + "_".join(map(str, key))
            self.code_tags[key] = tag
            self.configure_tag(tag, key)
        return tag

    def toggle_quotes(self):
        self.save_setting("general.show_quotations", self.show_quotes.get())
        self.rerender()

    def toggle_tables(self):
        self.save_setting("general.show_tables", self.show_tables.get())
        self.rerender()

    # ------------------------------------------------------- async plumbing --
    def run_async(self, channel: str, work, done):
        """Run work() on a thread; call done(ok, value) on the Tk thread unless
        a newer job on the same channel has started in the meantime."""
        ticket = self.tickets.get(channel, 0) + 1
        self.tickets[channel] = ticket

        def worker():
            try:
                res = (True, work())
            except Exception as e:  # delivered to done()
                res = (False, e)
            self.results.put((channel, ticket, done, res))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                channel, ticket, done, (ok, value) = self.results.get_nowait()
                if self.tickets.get(channel) == ticket:
                    done(ok, value)
        except queue.Empty:
            pass
        self.root.after(40, self.poll)

    def busy(self, on: bool, message: str = ""):
        self.root.configure(cursor="watch" if on else "")
        self.text.configure(cursor="watch" if on else "arrow")
        if message or not on:
            self.set_status(message)

    def set_status(self, msg: str):
        self.status.configure(text=msg)

    # -------------------------------------------------------------- loading --
    def options(self) -> Options:
        return self.settings.options(self.show_quotes.get(), self.show_tables.get())

    def wrap_chars(self) -> int:
        w = self.text.winfo_width()
        if w <= 1:
            w = 820
        chars = (w - 2 * 14 - 6) // max(1, self.font.measure("0"))
        return max(40, min(chars, self.settings["general.max_width"]))

    def render_job(self, word: str):
        """A function (page) -> result that renders on a worker thread.  What
        it needs from Tk is read here, on the main thread: Tk must not be
        touched from the worker."""
        langs_spec, opts, width = self.lang.get(), self.options(), self.wrap_chars()

        settings = self.settings

        def work(root):
            langs = language_sections(root)
            view = render_languages(settings, word, langs, langs_spec, width, opts,
                                    self.client.subpage)
            return word, langs, view, width
        return work

    def open(self, word: str, push: bool = True, position: float | None = None,
             language: str | None = None):
        word = word.strip()
        if not word:
            return
        self.cancel_suggestions()
        self.query.set(word)
        self.busy(True, f"Loading “{word}”…")
        job = self.render_job(word)
        limit = self.settings["general.search_results"]

        def work():
            try:
                root = self.client.page(word)
            except NotFound:
                return ("missing", word, suggestions(word, limit=limit))
            return ("ok",) + job(root)

        def done(ok, value):
            self.busy(False)
            if not ok:
                self.set_status(network_message(value) if isinstance(value, NetworkError)
                                else f"Error: {getattr(value, 'reason', value)}")
                return
            if value[0] == "missing":
                self.show_missing(value[1], value[2])
                return
            _, w, langs, view, width = value
            if push and self.word and self.word != w:
                self.history.visit(self.here())
            self.word, self.languages = w, langs
            self.display(view, width)
            if position is not None:
                self.text.yview_moveto(position)
            elif language:
                self.goto_language(language)
            self.after_display()

        self.run_async("page", work, done)

    def rerender(self, keep_position: bool = True):
        if not self.word:
            return
        try:
            root = self.client.page(self.word)  # cached
        except (NotFound, *NetworkError):
            return
        anchor = self.anchor() if keep_position else None
        self.busy(True)
        job = self.render_job(self.word)

        def done(ok, value):
            self.busy(False)
            if not ok:
                self.set_status(f"Error: {value}")
                return
            _, langs, view, width = value
            self.languages = langs
            self.display(view, width)
            if anchor:
                self.restore(anchor)
            self.after_display()

        self.run_async("page", lambda: job(root), done)

    def reload(self):
        if self.word:
            self.client.forget(self.word)
            self.open(self.word, push=False, position=self.text.yview()[0])

    def after_display(self):
        self.root.title(f"{self.word} — {NAME} {VERSION}")
        self.lang_box.configure(values=["all"] + [l.label() for l in self.languages])
        if self.view and not self.view.toc:
            self.set_status(no_language_message(self.lang.get(), self.languages))
        else:
            n = len(self.view.language_lines) if self.view else 0
            self.set_status(f"{plural(n, 'language')} shown"
                            f" · {len(self.languages)} on the page · click a link or double-click"
                            " a word to look it up")
        self.update_nav_buttons()
        self.compute_matches()

    # ------------------------------------------------------------- display --
    def display(self, view: Rendered, width: int):
        self.view = view
        self.render_chars = width
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        self.link_urls = {}
        links = self.settings["gui.links"]
        chunk: list = []
        for i, line in enumerate(view.lines):
            urls: list[str] = []
            last = None
            for seg, codes, url in styled_segments(line):
                tag = self.tag_for(codes)
                tags = (tag,) if tag else ()
                if url and links:
                    # (side by side links take turns with the two tags, so that
                    # they stay apart; link_at counts them)
                    if url != last:
                        urls.append(url)
                    tags += (LINK_TAGS[(len(urls) - 1) % 2],)
                last = url
                chunk.append(seg)
                chunk.append(tags)
            if urls:
                self.link_urls[i + 1] = urls
            chunk.extend(("\n", ()))
            if len(chunk) > 4000:
                t.insert("end", *chunk)
                chunk = []
        if chunk:
            t.insert("end", *chunk)
        t.configure(state="disabled")
        self.raise_tags()
        self.fill_toc()

    def fill_toc(self):
        tree = self.tree
        self.syncing = True
        tree.delete(*tree.get_children())
        self.toc_items.clear()
        self.toc_order = []
        parents: list[str] = [""]
        many = len([1 for d, _, _ in self.view.toc if d == 0]) > 3
        for depth, title, line in self.view.toc:
            del parents[depth + 1:]
            while len(parents) < depth + 1:
                parents.append(parents[-1])
            iid = tree.insert(parents[depth], "end", text=title,
                              open=(depth == 0) or not many)
            parents.append(iid)
            self.toc_items[iid] = line
            self.toc_order.append(iid)
        self.syncing = False

    def show_missing(self, word: str, sugg: list[str]):
        # leave the current page (Back returns to it) and clear its contents pane
        if self.word:
            self.history.visit(self.here())
        self.word, self.view, self.languages = None, None, []
        self.tree.delete(*self.tree.get_children())
        self.toc_items.clear()
        self.toc_order = []
        self.root.title(title())
        self.update_nav_buttons()
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", f"No Wiktionary entry for “{word}”.\n\n", self.tag_for((1,)))
        if sugg:
            t.insert("end", "Did you mean:\n\n")
            for i, s in enumerate(sugg):
                tag = f"sugg{i}"
                t.insert("end", "   ")
                t.insert("end", s, ("link", tag))
                t.insert("end", "\n")
                t.tag_bind(tag, "<Button-1>", lambda e, s=s: self.open(s))
                t.tag_bind(tag, "<Enter>", lambda e: t.configure(cursor="hand2"))
                t.tag_bind(tag, "<Leave>", lambda e: t.configure(cursor="arrow"))
        t.configure(state="disabled")
        self.set_status(f"No entry for “{word}”.")

    def welcome(self):
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", f"{NAME} {VERSION}\n", self.tag_for((1, 4)))
        t.insert("end", "\nThe English Wiktionary on your desktop.\n\n"
                        "Type a word in the box above and press Enter.\n"
                        "Click a link, or double-click any word, to look it up.\n\n" + KEYS_HELP,
                 "welcome")
        t.configure(state="disabled")

    # ---------------------------------------------------------- navigation --
    def top_line(self) -> int:
        return int(self.text.index("@0,0").split(".")[0]) - 1

    def current_toc_index(self) -> int | None:
        return self.view.toc_index(self.top_line()) if self.view else None

    def anchor(self):
        i = self.current_toc_index()
        if i is None or self.top_line() == 0:  # at the top: stay there
            return None
        return i, self.top_line() - self.view.toc[i][2]

    def restore(self, anchor):
        i, offset = anchor
        if self.view and i < len(self.view.toc):
            self.goto_line(self.view.toc[i][2] + max(0, offset))

    def goto_line(self, line: int):
        self.text.yview(f"{line + 1}.0")

    def on_scroll(self):
        if self.syncing or not self.toc_order:
            return
        i = self.current_toc_index()
        if i is None or i >= len(self.toc_order):
            return
        iid = self.toc_order[i]
        if self.tree.selection() != (iid,):
            self.syncing = True
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self.root.after_idle(lambda: setattr(self, "syncing", False))

    def on_toc_select(self, _):
        if self.syncing:
            return
        sel = self.tree.selection()
        if sel and sel[0] in self.toc_items:
            self.syncing = True
            self.goto_line(self.toc_items[sel[0]])
            self.root.after_idle(lambda: setattr(self, "syncing", False))

    def toc_shown(self) -> bool:
        return str(self.toc_frame) in map(str, self.paned.panes())

    def restore_sash(self):
        if self.toc_shown():
            self.paned.sashpos(0, round(self.settings["gui.contents_width"]
                                        * scale_factor(self.root)))

    def toggle_toc(self, save: bool = True):
        if save:
            self.save_setting("gui.show_contents", self.show_toc.get())
        if self.show_toc.get() and not self.toc_shown():
            self.paned.insert(0, self.toc_frame, weight=0)
            self.root.after(10, self.restore_sash)
        elif not self.show_toc.get() and self.toc_shown():
            self.paned.forget(self.toc_frame)

    def back(self):
        self.go(self.history.back(self.here()), "No earlier page.")

    def forward(self):
        self.go(self.history.forward(self.here()), "No later page.")

    def here(self) -> tuple[str, float] | None:
        """The page shown and how far down it is, for the history."""
        return (self.word, self.text.yview()[0]) if self.word else None

    def go(self, place: tuple[str, float] | None, nowhere: str):
        if place is None:
            self.set_status(nowhere)
        else:
            self.open(place[0], push=False, position=place[1])

    def update_nav_buttons(self):
        self.back_btn.state(["!disabled"] if self.history.past else ["disabled"])
        self.fwd_btn.state(["!disabled"] if self.history.future else ["disabled"])

    def on_resize(self, _=None):
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(250, self._resize_now)

    def _resize_now(self):
        self.resize_job = None
        if self.view and abs(self.wrap_chars() - self.render_chars) >= 2:
            self.rerender()

    def on_lang(self):
        val = self.lang.get().strip()
        # "Latin (la)" from the drop-down -> "la"
        if val.endswith(")") and "(" in val:
            val = val[val.rindex("(") + 1:-1]
            self.lang.set(val)
        if not val:
            self.lang.set("all")
        self.rerender(keep_position=False)

    def open_browser(self):
        if self.word:
            self.set_status(open_in_browser(page_url(self.word)))

    # --------------------------------------------------------- search box --
    def focus_search(self):
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def submit(self):
        if self.sugg.winfo_ismapped() and self.sugg.curselection():
            self.pick_suggestion()
        else:
            self.open(self.query.get())

    def on_search_key(self, ev):
        if not self.settings["gui.live_suggestions"]:
            return
        if ev.keysym in ("Return", "KP_Enter", "Escape", "Down", "Up", "Tab",
                         "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return
        if self.suggest_job:
            self.root.after_cancel(self.suggest_job)
        self.suggest_job = self.root.after(250, self.fetch_suggestions)

    def fetch_suggestions(self):
        self.suggest_job = None
        q = self.query.get().strip()
        if not q:
            self.hide_suggestions()
            return

        def done(ok, items):
            if ok and items and self.root.focus_get() in (self.search_entry, self.sugg) \
                    and self.query.get().strip() == q:
                self.show_suggestions(items)
            else:
                self.hide_suggestions()
        limit = self.settings["general.search_results"]
        self.run_async("suggest", lambda: search(q, limit=limit), done)

    def show_suggestions(self, items):
        s = self.sugg
        s.delete(0, "end")
        for it in items:
            s.insert("end", it)
        e = self.search_entry
        x = e.winfo_rootx() - self.root.winfo_rootx()
        y = e.winfo_rooty() - self.root.winfo_rooty() + e.winfo_height()
        s.configure(height=min(10, len(items)))
        s.place(x=x, y=y, width=max(e.winfo_width(), 260))
        s.lift()

    def hide_suggestions(self):
        self.sugg.place_forget()

    def cancel_suggestions(self):
        """Hide the list and drop any pending or in-flight suggestion request."""
        if self.suggest_job:
            self.root.after_cancel(self.suggest_job)
            self.suggest_job = None
        self.tickets["suggest"] = self.tickets.get("suggest", 0) + 1
        self.hide_suggestions()

    def maybe_hide_suggestions(self):
        if self.root.focus_get() is not self.sugg:
            self.hide_suggestions()

    def enter_suggestions(self):
        if self.sugg.winfo_ismapped() and self.sugg.size():
            self.sugg.focus_set()
            self.sugg.selection_clear(0, "end")
            self.sugg.selection_set(0)
            self.sugg.activate(0)
        return "break"

    def suggestion_up(self):
        if self.sugg.curselection() == (0,):
            self.search_entry.focus_set()
            return "break"

    def pick_suggestion(self):
        sel = self.sugg.curselection()
        if sel:
            self.open(self.sugg.get(sel[0]))
            self.text.focus_set()

    # --------------------------------------------------------------- find --
    def focus_find(self):
        self.find_entry.focus_set()
        self.find_entry.select_range(0, "end")

    def clear_find(self):
        self.find_var.set("")
        self.text.focus_set()

    def compute_matches(self):
        t = self.text
        t.tag_remove("match", "1.0", "end")
        t.tag_remove("current", "1.0", "end")
        self.matches, self.match_i = [], -1
        term = self.find_var.get()
        if not term or not self.view:
            self.find_count.configure(text="")
            return
        count = tk.IntVar()
        pos = "1.0"
        while True:
            pos = t.search(term, pos, stopindex="end", nocase=True, count=count)
            if not pos or count.get() == 0:
                break
            end = f"{pos}+{count.get()}c"
            t.tag_add("match", pos, end)
            self.matches.append(pos)
            pos = end
        self.find_count.configure(text=f"{len(self.matches)} found" if self.matches else "not found")

    def find_next(self, direction: int):
        if not self.matches:
            self.compute_matches()
            if not self.matches:
                return
        t = self.text
        if self.match_i < 0:
            # first jump: nearest match from the current view
            top = f"{self.top_line() + 1}.0"
            after = [i for i, m in enumerate(self.matches) if t.compare(m, ">=", top)]
            self.match_i = (after[0] if after else 0) if direction > 0 else \
                ((after[0] - 1) if after else len(self.matches) - 1)
        else:
            self.match_i = (self.match_i + direction) % len(self.matches)
        pos = self.matches[self.match_i]
        t.tag_remove("current", "1.0", "end")
        t.tag_add("current", pos, f"{pos}+{len(self.find_var.get())}c")
        t.see(pos)
        self.find_count.configure(text=f"{self.match_i + 1} of {len(self.matches)}")

    # ------------------------------------------------------ word lookups --
    def selected_word(self) -> str:
        try:
            s = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return ""
        return s.strip().strip(".,;:!?()[]{}“”\"'‘’«»—–-•*/|").strip()

    # --------------------------------------------------------------- links --
    def link_at(self, index: str) -> tuple[str, str, str] | None:
        """(start, end, URL) of the link at INDEX of the entry, or None."""
        t = self.text
        index = t.index(index)
        row = int(index.split(".")[0])
        urls = self.link_urls.get(row)
        if not urls:
            return None
        ranges = []
        for tag in LINK_TAGS:
            r = t.tag_nextrange(tag, f"{row}.0", f"{row}.end")
            while r:
                ranges.append((int(str(r[0]).split(".")[1]), str(r[0]), str(r[1])))
                r = t.tag_nextrange(tag, r[1], f"{row}.end")
        for k, (_, start, end) in enumerate(sorted(ranges)):
            if t.compare(start, "<=", index) and t.compare(index, "<", end):
                return (start, end, urls[k]) if k < len(urls) else None
        return None

    def link_hover(self, on: bool):
        """Underlines the link under the mouse, and says where it leads."""
        t = self.text
        t.tag_remove("hover", "1.0", "end")
        link = self.link_at("current") if on else None
        if link is None:
            t.configure(cursor="arrow")
            if self.link_status is not None and self.link_status == self.status.cget("text"):
                self.set_status(self.status_before_link)
            self.link_status = None
            return
        start, end, url = link
        t.tag_add("hover", start, end)
        t.configure(cursor="hand2")
        text = link_description(url)
        if self.link_status is None:
            self.status_before_link = self.status.cget("text")
        self.link_status = text
        self.set_status(text)

    def link_click(self, ev):
        if self.text.tag_ranges("sel"):        # (text was selected)
            return
        link = self.link_at(f"@{ev.x},{ev.y}")
        if link:
            self.follow(link[2])

    def follow(self, url: str):
        """Open the entry URL leads to (at its top), or, if it leads out
        of the entries of Wiktionary, open it in the browser."""
        target = entry_target(url)
        if target is None:
            self.set_status(open_in_browser(url))
            return
        word, language = target
        self.link_status = None
        if self.word == word:
            if language:
                self.goto_language(language)
        else:
            # (at the top, with the languages of the filter, not at the
            # language of the link)
            self.open(word)

    def goto_language(self, language: str):
        """Scrolls to the heading of LANGUAGE, if the entry shows it."""
        line = self.view.language_line(language) if self.view else None
        if line is not None:
            self.goto_line(line)

    def on_double_click(self, ev):
        if not self.settings["gui.double_click_lookup"]:
            return
        if self.link_at(f"@{ev.x},{ev.y}"):     # (the first click followed it)
            return
        # let Tk select the word first
        self.root.after(1, lambda: self.open(self.selected_word()) if self.selected_word() else None)

    def copy(self):
        try:
            s = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        self.root.clipboard_clear()
        self.root.clipboard_append(s)
        return "break"

    def on_context(self, ev):
        word = self.selected_word()
        if not word:
            idx = self.text.index(f"@{ev.x},{ev.y}")
            word = self.text.get(f"{idx} wordstart", f"{idx} wordend").strip()
        m = self.ctx
        m.delete(0, "end")
        if word:
            short = word if len(word) <= 30 else word[:29] + "…"
            m.add_command(label=f"Look up “{short}”", command=lambda: self.open(word))
        m.add_command(label="Copy", command=self.copy)
        m.add_command(label="Select all", command=lambda: self.text.tag_add("sel", "1.0", "end"))
        m.tk_popup(ev.x_root, ev.y_root)


# --------------------------------------------------------------------------- #
# Settings dialog
# --------------------------------------------------------------------------- #
class SettingsDialog:
    """The settings, one tab per program; made from settings.SCHEMA."""

    #  (tab name, [(heading, section), ...])
    TABS = (("Appearance", (("", "appearance"), ("Fonts", "fonts"))),
            ("Window", (("", "gui"),)),
            ("General", (("", "general"),)),
            ("Terminal UI", (("", "tui"),)),
            ("Command line", (("", "cli"),)))
    NOTES = {"Terminal UI": "These apply to py-wtk-tui; they are kept in the same file.",
             "Command line": "These apply to the py-wtk command; they are kept in the same file."}
    SAMPLE = "rosa, rosae f — ῥόδον — роза — [ˈrɔ.sa] — 0123456789"

    def __init__(self, app: "App"):
        self.app = app
        self.st = app.settings
        self.fonts = app.fonts
        top = self.top = tk.Toplevel(app.root)
        top.title(f"{NAME} {VERSION}: settings")
        top.transient(app.root)
        self.vars: dict[str, tk.Variable] = {}
        self.tab_settings: dict[str, list[Setting]] = {}

        outer = ttk.Frame(top, padding=10)
        outer.pack(fill="both", expand=True)
        nb = self.nb = ttk.Notebook(outer)
        nb.pack(fill="both", expand=True)
        for tab, groups in self.TABS:
            frame = ttk.Frame(nb, padding=12)
            nb.add(frame, text=tab)
            frame.columnconfigure(1, weight=1)
            self.tab_settings[str(frame)] = []
            row = 0
            if tab in self.NOTES:
                ttk.Label(frame, text=self.NOTES[tab], style="Muted.TLabel").grid(
                    row=row, column=0, columnspan=2, sticky="w", pady=(0, 6))
                row += 1
            for heading, section in groups:
                if heading:
                    ttk.Label(frame, text=heading, font=self.fonts_bold()).grid(
                        row=row, column=0, columnspan=2, sticky="w", pady=(10 if row else 0, 0))
                    row += 1
                for s in self.st.visible(section):
                    row = self.add_row(frame, row, s)
                    self.tab_settings[str(frame)].append(s)
                if section == "fonts":
                    ttk.Label(frame, text="Preview:").grid(row=row, column=0, sticky="nw",
                                                           pady=(8, 0))
                    self.preview = tk.Label(frame, text=self.SAMPLE, anchor="w",
                                            relief="groove", padx=8, pady=6)
                    self.preview.grid(row=row, column=1, sticky="ew", pady=(8, 0))
                    row += 1
                    for name in ("fonts.text_family", "fonts.text_size", "appearance.dark_mode"):
                        self.vars[name].trace_add("write", lambda *a: self.update_preview())
                    self.update_preview()
                if section == "general":
                    cache = ttk.Frame(frame)
                    cache.grid(row=row, column=0, columnspan=2, sticky="w", pady=(12, 0))
                    self.cache_label = ttk.Label(cache, text="")
                    self.cache_label.pack(side="left")
                    ttk.Button(cache, text="Clear disk cache", command=self.clear_cache).pack(
                        side="left", padx=8)
                    self.update_cache_label()
                    row += 1

        ttk.Label(outer, text=f"Settings file: {self.st.path}", style="Muted.TLabel").pack(
            anchor="w", pady=(8, 0))
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Usual values (this tab)",
                   command=self.restore_tab).pack(side="left")
        ttk.Button(buttons, text="OK", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(buttons, text="Apply", command=self.apply).pack(side="right", padx=4)
        ttk.Button(buttons, text="Cancel", command=top.destroy).pack(side="right")
        top.bind("<Escape>", lambda e: top.destroy())
        top.bind("<Return>", lambda e: self.ok())
        top.update_idletasks()
        top.minsize(top.winfo_reqwidth(), top.winfo_reqheight())
        top.grab_set()

    @staticmethod
    def fonts_bold():
        f = tkfont.nametofont("TkDefaultFont").actual()
        return (f["family"], abs(f["size"]), "bold")

    # ---- widgets ------------------------------------------------------- #
    def add_row(self, frame, row: int, s: Setting) -> int:
        value = self.st[s.name]
        if s.kind == "bool":
            var = tk.BooleanVar(value=value)
            ttk.Checkbutton(frame, text=s.label, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))
        else:
            ttk.Label(frame, text=s.label + ":").grid(row=row, column=0, sticky="w",
                                                     pady=(6, 0), padx=(0, 10))
            if s.kind == "int":
                var = tk.StringVar(value=str(value))
                w = ttk.Spinbox(frame, from_=s.min, to=s.max, textvariable=var, width=8)
                w.grid(row=row, column=1, sticky="w", pady=(6, 0))
            elif s.kind == "choice":
                var = tk.StringVar(value=value)
                w = ttk.Combobox(frame, textvariable=var, values=list(s.choices),
                                 state="readonly", width=12)
                w.grid(row=row, column=1, sticky="w", pady=(6, 0))
            elif s.name in ("fonts.text_family", "fonts.ui_family"):
                var = tk.StringVar(value=value)
                families = self.fonts.fixed_families() if s.key == "text_family" \
                    else self.fonts.all_families()
                w = ttk.Combobox(frame, textvariable=var, width=36, values=[""] + families)
                w.grid(row=row, column=1, sticky="w", pady=(6, 0))
            else:
                var = tk.StringVar(value=s.format(value))
                w = ttk.Entry(frame, textvariable=var, width=40)
                w.grid(row=row, column=1, sticky="ew", pady=(6, 0))
        self.vars[s.name] = var
        ttk.Label(frame, text=s.help, style="Muted.TLabel", wraplength=540).grid(
            row=row + 1, column=0, columnspan=2, sticky="w",
            padx=(22 if s.kind == "bool" else 0, 0))
        return row + 2

    def update_preview(self):
        """The sample in the entry font and colours chosen."""
        try:
            size = int(self.vars["fonts.text_size"].get())
        except (ValueError, tk.TclError):
            return
        family = self.vars["fonts.text_family"].get() or self.fonts.defaults["text_family"]
        p = DARK if self.vars["appearance.dark_mode"].get() else LIGHT
        self.preview.configure(font=(family, max(6, min(size, 40))),
                               background=p["field"], foreground=p["foreground"])

    def update_cache_label(self):
        self.cache_label.configure(text=f"Disk cache: {cache_summary()}")

    def clear_cache(self):
        self.app.set_status(clear_cache())
        self.update_cache_label()

    # ---- actions ------------------------------------------------------- #
    def restore_tab(self):
        for s in self.tab_settings[self.nb.select()]:
            var = self.vars[s.name]
            var.set(s.default if s.kind == "bool" else s.format(s.default))

    def apply(self) -> bool:
        new = {}
        for name, var in self.vars.items():
            s = BY_NAME[name]
            try:
                new[name] = s.parse(var.get())
            except (ValueError, tk.TclError) as e:
                messagebox.showerror("Invalid setting", f"{s.label}: {e}", parent=self.top)
                return False
        changed = {n for n, v in new.items() if v != self.st[n]}
        if not changed:
            return True
        for n in changed:
            if new[n] == BY_NAME[n].default:
                self.st.reset(n)        # (the usual value: removed from the file)
            else:
                self.st.set(n, new[n])
        try:
            self.st.save()
        except OSError as e:
            messagebox.showerror("Settings", f"Could not save the settings:\n{e}",
                                 parent=self.top)
            return False
        self.app.apply_settings(changed)
        self.app.set_status(f"Settings saved ({len(changed)} changed).")
        return True

    def ok(self):
        if self.apply():
            self.top.destroy()


#  The window's class (for the window manager and the desktop entry) and icons
WM_CLASS = "py-wtk"
ICON_DIR = os.path.join(HERE, "icons", "linux", "hicolor")


def set_icon(root):
    """Gives the window the program's icon, if the icons are there."""
    images = []
    for size in (16, 32, 48, 128, 256):
        path = os.path.join(ICON_DIR, f"{size}x{size}", "apps", WM_CLASS + ".png")
        try:
            images.append(tk.PhotoImage(file=path))
        except tk.TclError:             # missing, or no PNG support
            pass
    if images:
        root.iconphoto(True, *images)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="py-wtk-gui",
                                 description=f"{title()}, in a window.")
    add_lookup_args(ap, "word or phrase to open")
    look = ap.add_mutually_exclusive_group()
    look.add_argument("--dark", action="store_const", const=True, default=None,
                      help="dark this time (default: setting appearance.dark_mode)")
    look.add_argument("--light", dest="dark", action="store_const", const=False,
                      help="light this time")
    ap.add_argument("--size", type=int,
                    help="entry text size this time (default: setting fonts.text_size)")
    args = ap.parse_args(argv)
    try:
        root = tk.Tk(className=WM_CLASS)
    except tk.TclError as e:
        print(f"py-wtk-gui: cannot open a window ({e})", file=sys.stderr)
        return 1
    set_icon(root)
    App(root, " ".join(args.word).strip() or None, args.lang, args.dark, args.size)
    root.mainloop()
    return 0


def run():
    sys.exit(main())


if __name__ == "__main__":
    run()
