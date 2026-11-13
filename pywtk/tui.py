# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""py-wtk-tui — a curses interface for browsing the English Wiktionary.

    py-wtk-tui            # start with an empty search prompt
    py-wtk-tui rosa       # open "rosa" directly
    py-wtk-tui rosa -l la # Latin only

Press ? inside the program for the list of keys.
"""

from __future__ import annotations

import argparse
import curses
import os
import sys

from . import clipboard
from .api import NetworkError, NotFound, entry_target, page_url, search, suggestions
from .common import (History, add_lookup_args, cache_summary, clear_cache, network_message,
                     no_language_message, open_in_browser, render_languages)
from .entry import Language, language_sections
from .render import Rendered
from .settings import SECTION_TITLES, Settings
from .text import char_width, display_width, styled_segments
from .version import NAME, TAGLINE, VERSION, title as program_title

HELP = [
    ("Lookup", ""),
    ("/  s", "look up a word"),
    ("Tab", "(in the prompt) show suggestions"),
    ("l", "language filter (e.g. en,la or all)"),
    ("b  Backspace", "back in history"),
    ("B", "forward in history"),
    ("L", "the links on the screen: choose one to open"),
    ("click", "open a link (with the mouse on)"),
    ("", ""),
    ("Reading", ""),
    ("j k  ↓ ↑", "scroll line by line"),
    ("Space PgDn / PgUp", "scroll page"),
    ("d u", "scroll half page"),
    ("g G  Home End", "top / bottom"),
    ("← →  h", "scroll sideways (wide tables)"),
    ("[ ]", "previous / next section"),
    ("{ }", "previous / next language"),
    ("", ""),
    ("Contents", ""),
    ("c  Tab", "focus the contents pane (Tab/Esc to leave)"),
    ("t", "show / hide the contents pane"),
    ("", ""),
    ("Find", ""),
    ("f  Ctrl-F", "find in page"),
    ("n N", "next / previous match"),
    ("", ""),
    ("Other", ""),
    ("x", "show / hide quotations"),
    ("T", "show / hide tables"),
    ("o", "open the page in a web browser"),
    ("r", "reload"),
    ("y  F7", "copy the whole entry (as plain text)"),
    ("?", "this help"),
    ("S", "settings"),
    ("q", "quit"),
]


class Page:
    """A fetched page and its rendering for the current settings."""

    def __init__(self, word: str, root):
        self.word = word
        self.root = root
        self.languages: list[Language] = language_sections(root)
        self.view = Rendered(lines=[])

    @property
    def lines(self):
        return self.view.lines

    @property
    def toc(self):
        return self.view.toc


class App:
    def __init__(self, scr, word: str | None, lang: str | None):
        self.scr = scr
        self.settings = Settings()
        st = self.settings
        self.lang = lang or st["general.languages"]
        self.show_toc = st["tui.show_contents"]
        self.show_quotes = st["general.show_quotations"]
        self.show_tables = st["general.show_tables"]
        self.focus = "content"  # or "toc"
        self.page: Page | None = None
        self.top = 0
        self.hscroll = 0
        self.toc_sel = 0
        self.toc_top = 0
        self.find_term = ""
        self.matches: list[int] = []
        self.message = ""
        self.history: History[tuple[str, int]] = History()
        self.client = st.client(on_fetch=lambda t: self.status_now(f"Loading “{t}”…"))
        self.render_width = 0
        self.running = True

        curses.curs_set(0)
        scr.keypad(True)
        self.apply_mouse()
        self.init_colors()
        if word:
            self.open(word)
        else:
            self.message = "Press / to look up a word, S for settings, ? for help, q to quit."
        if st.problems:
            self.message = "Settings: " + "; ".join(st.problems)
        elif st.messages:
            self.message = " ".join(st.messages)

    def apply_mouse(self):
        try:
            if self.settings["tui.mouse"]:
                curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
            else:
                curses.mousemask(0)
        except curses.error:
            pass

    def save_setting(self, name: str, value):
        self.settings.set(name, value)
        try:
            self.settings.save()
        except OSError as e:
            self.message = f"Could not save settings: {e}"

    # ---- colors ---------------------------------------------------------- #
    def init_colors(self):
        self.color = {}
        if not curses.has_colors() or not self.settings["tui.colors"]:
            return
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        names = {31: curses.COLOR_RED, 32: curses.COLOR_GREEN, 33: curses.COLOR_YELLOW,
                 34: curses.COLOR_BLUE, 35: curses.COLOR_MAGENTA, 36: curses.COLOR_CYAN}
        for i, (code, c) in enumerate(names.items(), start=1):
            curses.init_pair(i, c, bg)
            self.color[code] = curses.color_pair(i)
        curses.init_pair(10, curses.COLOR_BLACK, curses.COLOR_CYAN)
        self.color["bar"] = curses.color_pair(10)
        curses.init_pair(11, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        self.color["match"] = curses.color_pair(11)

    def codes_attr(self, codes) -> int:
        attr = 0
        for c in codes:
            if c == 1:
                attr |= curses.A_BOLD
            elif c == 2:
                attr |= curses.A_DIM
            elif c == 3:
                attr |= getattr(curses, "A_ITALIC", 0)
            elif c == 4:
                attr |= curses.A_UNDERLINE
            elif c in self.color:
                attr |= self.color[c]
        return attr

    def cells(self, line: str) -> list[tuple[str, int]]:
        """Split a styled line into (char, curses attr) pairs.  Links are
        blue (underlined without colours), keeping bold and the like."""
        out = []
        for text, codes, url in styled_segments(line):
            if url:
                attr = self.codes_attr([c for c in codes if c not in self.color])
                attr |= self.color.get(34, curses.A_UNDERLINE)
            else:
                attr = self.codes_attr(codes)
            out.extend((ch, attr) for ch in text)
        return out

    def line_links(self, i: int) -> list[tuple[int, int, str, str]]:
        """The links of line I of the page: (first column, column after it,
        URL, text)."""
        out: list[tuple[int, int, str, str]] = []
        col = 0
        for text, _, url in styled_segments(self.page.lines[i]):
            width = display_width(text)
            if url:
                if out and out[-1][1] == col and out[-1][2] == url:
                    start, _, _, before = out.pop()       # (one link, two styles)
                    out.append((start, col + width, url, before + text))
                else:
                    out.append((col, col + width, url, text))
            col += width
        return out

    # ---- geometry -------------------------------------------------------- #
    @property
    def h(self):
        return self.scr.getmaxyx()[0]

    @property
    def w(self):
        return self.scr.getmaxyx()[1]

    def toc_width(self):
        if not self.show_toc or not self.page or not self.page.languages or self.w < 70:
            return 0
        return min(self.settings["tui.contents_width"], self.w // 2)

    def content_x(self):
        tw = self.toc_width()
        return tw + 1 if tw else 0

    def content_w(self):
        return self.w - self.content_x()

    def body_h(self):
        return max(1, self.h - 2)

    # ---- fetching & rendering --------------------------------------------- #
    def open(self, word: str, push: bool = True, top: int = 0,
             language: str | None = None):
        word = word.strip()
        if not word:
            return
        try:
            root = self.client.page(word)
        except NotFound:
            self.not_found(word)
            return
        except NetworkError as e:
            self.message = network_message(e)
            return
        if push and self.page:
            self.history.visit((self.page.word, self.top))
        self.page = Page(word, root)
        self.find_term = ""
        self.matches = []
        self.render()
        self.top = min(top, self.max_top())
        self.hscroll = 0
        if language:
            self.goto_language(language)
        self.sync_toc()
        self.check_language_filter(" Press l to change.")

    def goto_language(self, language: str):
        """Scrolls to the heading of LANGUAGE, if the page shows it."""
        line = self.page.view.language_line(language)
        if line is not None:
            self.jump_line(line)

    def follow(self, url: str):
        """Open the entry URL leads to (at its top), or, if it leads out
        of the entries of Wiktionary, open it in the browser."""
        target = entry_target(url)
        if target is None:
            self.message = open_in_browser(url)
            return
        word, language = target
        if self.page and self.page.word == word:
            if language:
                self.goto_language(language)
                self.sync_toc()
        else:
            # (at the top, with the languages of the filter, not at the
            # language of the link)
            self.open(word)

    def choose_link(self):
        """A list of the links on the screen, to open one."""
        links: list[tuple[str, str]] = []
        for i in range(self.top, min(self.top + self.body_h(), len(self.page.lines))):
            for _, _, url, text in self.line_links(i):
                if (text, url) not in links:
                    links.append((text, url))
        if not links:
            self.message = "No links on the screen."
            return
        items = []
        for text, url in links:
            target = entry_target(url)
            where = (target[1] or "") if target else url
            items.append(f"{text}  ({where})" if where else text)
        choice = self.choose("Open a link:", items)
        if choice is not None:
            self.follow(links[items.index(choice)][1])

    def check_language_filter(self, hint: str = ""):
        if self.page and not self.page.toc:
            self.message = no_language_message(self.lang, self.page.languages) + hint
        else:
            self.message = ""

    def not_found(self, word: str):
        sugg = suggestions(word, limit=self.settings["general.search_results"])
        if not sugg:
            self.message = f"No Wiktionary entry for “{word}”."
            return
        choice = self.choose(f"No entry for “{word}”. Did you mean:", sugg)
        if choice:
            self.open(choice)

    def render(self):
        page = self.page
        if not page:
            return
        self.render_width = self.content_w()
        st = self.settings
        opts = st.options(self.show_quotes, self.show_tables)
        width = max(30, min(self.content_w() - 2, st["general.max_width"]))
        page.view = render_languages(st, page.word, page.languages, self.lang, width, opts,
                                     self.client.subpage)
        if self.find_term:
            self.compute_matches()

    def rerender_keep_position(self):
        if not self.page:
            return
        if self.top == 0:  # at the top: stay there
            self.render()
            self.sync_toc()
            return
        # keep the current section in view
        anchor = self.current_toc_index()
        offset = self.top - self.page.toc[anchor][2] if anchor is not None else 0
        self.render()
        if anchor is not None and anchor < len(self.page.toc):
            self.top = self.page.toc[anchor][2] + max(0, offset)
        self.top = max(0, min(self.top, self.max_top()))
        self.sync_toc()

    # ---- navigation -------------------------------------------------------- #
    def max_top(self):
        if not self.page:
            return 0
        return max(0, len(self.page.lines) - self.body_h())

    def scroll(self, n: int):
        self.top = max(0, min(self.top + n, self.max_top()))
        self.sync_toc()

    def current_toc_index(self):
        return self.page.view.toc_index(self.top) if self.page else None

    def sync_toc(self):
        i = self.current_toc_index()
        if i is not None and self.focus != "toc":
            self.toc_sel = i

    def jump_line(self, ln: int):
        self.top = max(0, min(ln, self.max_top()))

    def jump_section(self, direction: int, languages_only: bool = False):
        if not self.page:
            return
        targets = (self.page.view.language_lines if languages_only
                   else [ln for _, _, ln in self.page.toc])
        if direction > 0:
            nxt = [ln for ln in targets if ln > self.top + 1]
            if nxt:
                self.jump_line(nxt[0])
        else:
            prv = [ln for ln in targets if ln < self.top]
            self.jump_line(prv[-1] if prv else 0)
        self.sync_toc()

    def back(self):
        self.go(self.history.back(self.here()), "No earlier page.")

    def forward(self):
        self.go(self.history.forward(self.here()), "No later page.")

    def here(self) -> tuple[str, int] | None:
        return (self.page.word, self.top) if self.page else None

    def go(self, place: tuple[str, int] | None, nowhere: str):
        if place is None:
            self.message = nowhere
        else:
            self.open(place[0], push=False, top=place[1])

    # ---- find -------------------------------------------------------------- #
    def compute_matches(self):
        t = self.find_term.lower()
        self.matches = ([i for i, l in enumerate(self.page.view.plain) if t in l.lower()]
                        if t else [])

    def find_next(self, direction: int):
        if not self.find_term:
            self.message = "Nothing to find (press f)."
            return
        if not self.matches:
            self.message = f"“{self.find_term}” not found."
            return
        cur = self.top + 2  # matches are shown a couple of lines below the top
        if direction > 0:
            nxt = [m for m in self.matches if m > cur]
            target = nxt[0] if nxt else self.matches[0]
        else:
            prv = [m for m in self.matches if m < cur]
            target = prv[-1] if prv else self.matches[-1]
        self.jump_line(target - 2)
        self.sync_toc()
        n = self.matches.index(target) + 1
        self.message = f"“{self.find_term}”: match {n} of {len(self.matches)}"

    # ---- drawing ----------------------------------------------------------- #
    def put(self, y: int, x: int, cells, width: int, skip: int = 0, base_attr: int = 0):
        """Draw (char, attr) cells at y,x clipped to `width` columns, skipping
        the first `skip` columns (horizontal scroll)."""
        col = 0
        drawn = 0
        for ch, attr in cells:
            cw = char_width(ch)
            if col < skip:
                col += cw
                continue
            if drawn + cw > width:
                break
            if ch in "\t\r\n":
                ch = " "
            try:
                self.scr.addstr(y, x + drawn, ch, attr | base_attr)
            except curses.error:
                pass
            drawn += cw
            col += cw
        return drawn

    def bar(self, y: int, text: str, right: str = ""):
        w = self.w
        attr = self.color.get("bar", curses.A_REVERSE)
        try:
            self.scr.addstr(y, 0, " " * (w - 1), attr)
            self.scr.insstr(y, w - 1, " ", attr)
        except curses.error:
            pass
        rw = display_width(right)
        self.put(y, 0, [(c, attr) for c in " " + text], max(0, w - rw - 2))
        if right:
            self.put(y, max(0, w - rw - 1), [(c, attr) for c in right], rw)

    def draw(self):
        self.scr.erase()
        h, w = self.h, self.w
        if h < 5 or w < 30:
            self.scr.addstr(0, 0, "Window too small"[: w - 1])
            self.scr.refresh()
            return
        page = self.page
        # title bar
        if page:
            cur = self.current_toc_index()
            where = ""
            if cur is not None:
                langs = [t for t in page.toc[: cur + 1] if t[0] == 0]
                where = langs[-1][1] if langs else ""
                if page.toc[cur][0] != 0:
                    where += " › " + page.toc[cur][1]
            total = len(page.lines)
            pct = 100 if total <= self.body_h() else int(100 * self.top / max(1, self.max_top()))
            self.bar(0, f"{NAME} {VERSION} │ {page.word} │ {where}", f"[{self.lang}] {pct}% ")
        else:
            self.bar(0, program_title())

        # contents pane
        tw = self.toc_width()
        bh = self.body_h()
        if tw and page:
            toc = page.toc
            if self.toc_sel < self.toc_top:
                self.toc_top = self.toc_sel
            elif self.toc_sel >= self.toc_top + bh:
                self.toc_top = self.toc_sel - bh + 1
            for row in range(bh):
                i = self.toc_top + row
                if i >= len(toc):
                    break
                depth, title, _ = toc[i]
                label = "  " * depth + title
                attr = curses.A_BOLD | self.color.get(36, 0) if depth == 0 else 0
                if i == self.toc_sel:
                    attr = curses.A_REVERSE | (curses.A_BOLD if self.focus == "toc" else 0)
                    label = label + " " * max(0, tw - display_width(label))
                self.put(1 + row, 0, [(c, attr) for c in label], tw)
            sep_attr = curses.A_BOLD if self.focus == "toc" else curses.A_DIM
            for row in range(bh):
                try:
                    self.scr.addstr(1 + row, tw, "│", sep_attr)
                except curses.error:
                    pass

        # content
        cx, cw = self.content_x(), self.content_w()
        if page:
            term = self.find_term.lower()
            mattr = self.color.get("match", curses.A_REVERSE)
            for row in range(bh):
                i = self.top + row
                if i >= len(page.lines):
                    break
                cells = self.cells(page.lines[i])
                if term and term in page.view.plain[i].lower():
                    low = "".join(c for c, _ in cells).lower()
                    start = 0
                    while True:
                        k = low.find(term, start)
                        if k < 0:
                            break
                        for j in range(k, k + len(term)):
                            cells[j] = (cells[j][0], mattr)
                        start = k + len(term)
                self.put(1 + row, cx + 1, cells, cw - 1, skip=self.hscroll)
        else:
            logo = [f"{NAME} {VERSION}", "", f"{TAGLINE[0].upper()}{TAGLINE[1:]} in your terminal", "",
                    "/  look up a word", "?  help", "q  quit"]
            for k, l in enumerate(logo):
                y = 2 + k + max(0, (bh - len(logo)) // 3)
                if y < h - 1:
                    self.put(y, max(0, (w - display_width(l)) // 2),
                             [(c, curses.A_BOLD if k == 0 else 0) for c in l], w)

        # status line
        hints = "/ look up  f find  c contents  L links  b back  x quotes  y copy  ? help  q quit"
        msg = self.message or hints
        self.put(h - 1, 0, [(c, curses.A_DIM if not self.message else curses.A_BOLD)
                            for c in msg], w - 1)
        self.scr.refresh()

    def status_now(self, text: str):
        h, w = self.h, self.w
        try:
            self.scr.move(h - 1, 0)
            self.scr.clrtoeol()
        except curses.error:
            pass
        self.put(h - 1, 0, [(c, curses.A_BOLD) for c in text], w - 1)
        self.scr.refresh()

    # ---- modal widgets ----------------------------------------------------- #
    def prompt(self, label: str, initial: str = "", suggest: bool = False) -> str | None:
        """Single-line editor on the status line. Returns None on Esc."""
        buf = list(initial)
        pos = len(buf)
        curses.curs_set(1)
        try:
            while True:
                h, w = self.h, self.w
                self.scr.move(h - 1, 0)
                self.scr.clrtoeol()
                text = "".join(buf)
                avail = w - display_width(label) - 2
                # keep cursor visible in long input
                start = 0
                while display_width(text[start:pos]) > avail:
                    start += 1
                shown = label + text[start:]
                self.put(h - 1, 0, [(c, curses.A_BOLD if i < len(label) else 0)
                                    for i, c in enumerate(shown)], w - 1)
                cur_x = display_width(label) + display_width(text[start:pos])
                try:
                    self.scr.move(h - 1, min(cur_x, w - 1))
                except curses.error:
                    pass
                self.scr.refresh()
                try:
                    k = self.scr.get_wch()
                except curses.error:
                    continue
                if k in ("\n", "\r", curses.KEY_ENTER):
                    return "".join(buf)
                if k == "\x1b":
                    return None
                if k in (curses.KEY_BACKSPACE, "\x7f", "\b"):
                    if pos:
                        del buf[pos - 1]
                        pos -= 1
                elif k == curses.KEY_DC:
                    if pos < len(buf):
                        del buf[pos]
                elif k == curses.KEY_LEFT:
                    pos = max(0, pos - 1)
                elif k == curses.KEY_RIGHT:
                    pos = min(len(buf), pos + 1)
                elif k in (curses.KEY_HOME, "\x01"):
                    pos = 0
                elif k in (curses.KEY_END, "\x05"):
                    pos = len(buf)
                elif k == "\x15":  # Ctrl-U
                    del buf[:pos]
                    pos = 0
                elif k == "\x17":  # Ctrl-W
                    j = pos
                    while j and buf[j - 1] == " ":
                        j -= 1
                    while j and buf[j - 1] != " ":
                        j -= 1
                    del buf[j:pos]
                    pos = j
                elif k == "\t" and suggest:
                    q = "".join(buf).strip()
                    if q:
                        try:
                            res = search(q, limit=self.settings["general.search_results"])
                        except NetworkError:
                            res = []
                        curses.curs_set(0)
                        choice = self.choose(f"Pages matching “{q}”:", res) if res else None
                        curses.curs_set(1)
                        if choice:
                            return choice
                        self.draw()
                elif k == curses.KEY_RESIZE:
                    self.handle_resize()
                    self.draw()
                elif isinstance(k, str) and k.isprintable():
                    buf.insert(pos, k)
                    pos += 1
        finally:
            curses.curs_set(0)

    def choose(self, title: str, items: list[str]) -> str | None:
        """Pick one item from a centred list. Returns None on Esc/q."""
        if not items:
            return None
        sel = 0
        top = 0
        while True:
            self.draw()
            h, w = self.h, self.w
            bw = min(w - 4, max(display_width(title), *(display_width(i) for i in items)) + 6)
            bh = min(h - 4, len(items) + 4)
            y0, x0 = (h - bh) // 2, (w - bw) // 2
            win = curses.newwin(bh, bw, y0, x0)
            win.keypad(True)
            win.erase()
            win.border()
            rows = bh - 4
            if sel < top:
                top = sel
            elif sel >= top + rows:
                top = sel - rows + 1
            try:
                win.addstr(1, 2, title[: bw - 4], curses.A_BOLD)
            except curses.error:
                pass
            for r in range(rows):
                i = top + r
                if i >= len(items):
                    break
                attr = curses.A_REVERSE if i == sel else 0
                label = items[i][: bw - 6]
                try:
                    win.addstr(3 + r, 3, label + " " * max(0, bw - 6 - display_width(label)), attr)
                except curses.error:
                    pass
            win.refresh()
            try:
                k = win.get_wch()
            except curses.error:
                continue
            if k in ("\x1b", "q"):
                return None
            if k in ("\n", "\r", curses.KEY_ENTER):
                return items[sel]
            if k in (curses.KEY_DOWN, "j", "\t"):
                sel = (sel + 1) % len(items)
            elif k in (curses.KEY_UP, "k", curses.KEY_BTAB):
                sel = (sel - 1) % len(items)
            elif k == curses.KEY_RESIZE:
                self.handle_resize()

    def show_help(self):
        h, w = self.h, self.w
        lines = []
        for key, desc in HELP:
            if key and not desc:
                lines.append((key, "", curses.A_BOLD | self.color.get(33, 0)))
            else:
                lines.append((key, desc, 0))
        bw = min(w - 2, 64)
        bh = min(h - 2, len(lines) + 4)
        win = curses.newwin(bh, bw, max(0, (h - bh) // 2), max(0, (w - bw) // 2))
        win.keypad(True)
        top = 0
        while True:
            win.erase()
            win.border()
            try:
                win.addstr(0, 2, " Keys ", curses.A_BOLD)
                win.addstr(bh - 1, 2, " any key to close ", curses.A_DIM)
            except curses.error:
                pass
            for r in range(bh - 4):
                i = top + r
                if i >= len(lines):
                    break
                key, desc, attr = lines[i]
                try:
                    if desc:
                        win.addstr(2 + r, 3, key.ljust(20)[: bw - 6], curses.A_BOLD)
                        win.addstr(2 + r, 24, desc[: bw - 26])
                    else:
                        win.addstr(2 + r, 2, key[: bw - 4], attr)
                except curses.error:
                    pass
            win.refresh()
            k = win.getch()
            if k in (curses.KEY_DOWN, ord("j")) and top + bh - 4 < len(lines):
                top += 1
            elif k in (curses.KEY_UP, ord("k")) and top > 0:
                top -= 1
            else:
                return

    # ---- settings ---------------------------------------------------------- #
    def settings_screen(self):
        """Full-screen list of settings; changes are saved and applied at once."""
        st = self.settings
        rows: list = []  # section titles (str) and Setting objects
        for section, title in SECTION_TITLES.items():
            items = st.visible(section)
            if items:
                rows.append(title)
                rows.extend(items)
        rows.append("Disk cache")
        rows.append("clear-cache")
        selectable = [i for i, r in enumerate(rows) if not isinstance(r, str) or r == "clear-cache"]
        sel = 0
        top = 0
        note = "Enter: change · d: default · Esc/q: close. Changes are saved immediately."
        while True:
            h, w = self.h, self.w
            self.scr.erase()
            home = os.path.expanduser("~")
            shown = str(st.path)
            shown = "~" + shown[len(home):] if shown.startswith(home + os.sep) else shown
            self.bar(0, f"{NAME} {VERSION} │ Settings", shown + " ")
            body = h - 4
            cur = selectable[sel]
            if cur < top:
                top = cur
            elif cur >= top + body:
                top = cur - body + 1
            if top and cur - top < 2:
                top = max(0, cur - 2)
            label_w = min(34, w // 2)
            for r in range(body):
                i = top + r
                if i >= len(rows):
                    break
                row = rows[i]
                y = 1 + r
                if isinstance(row, str) and row != "clear-cache":
                    self.put(y, 1, [(c, curses.A_BOLD | self.color.get(36, 0)) for c in row], w - 2)
                    continue
                if row == "clear-cache":
                    label = "Clear the disk cache"
                    value = cache_summary()
                else:
                    label = row.label
                    value = row.format(st[row.name]) or "(empty)"
                    if not st.is_default(row.name):
                        value += "  *"
                attr = curses.A_REVERSE if i == cur else 0
                text = f"   {label:<{label_w}} {value}"
                text += " " * max(0, w - 2 - display_width(text))
                self.put(y, 0, [(c, attr) for c in text], w - 1)
            # help for the selected row
            row = rows[cur]
            if row == "clear-cache":
                helptext = "Delete the downloaded pages kept on disk (see 'Keep pages on disk')."
            else:
                helptext = f"{row.help}  [{row.describe_range()}; default: " \
                           f"{row.format(row.default) or '(empty)'}]"
            self.put(h - 3, 1, [(c, curses.A_DIM) for c in "─" * (w - 2)], w - 2)
            self.put(h - 2, 1, [(c, 0) for c in helptext], w - 2)
            self.put(h - 1, 0, [(c, curses.A_BOLD if self.message else curses.A_DIM)
                                for c in (self.message or note)], w - 1)
            self.scr.refresh()
            try:
                k = self.scr.get_wch()
            except curses.error:
                continue
            self.message = ""
            if k in ("q", "\x1b", "S"):
                break
            if k in (curses.KEY_DOWN, "j"):
                sel = min(len(selectable) - 1, sel + 1)
            elif k in (curses.KEY_UP, "k"):
                sel = max(0, sel - 1)
            elif k in ("g", curses.KEY_HOME):
                sel = 0
            elif k in ("G", curses.KEY_END):
                sel = len(selectable) - 1
            elif k == curses.KEY_RESIZE:
                curses.update_lines_cols()
            elif row == "clear-cache" and k in ("\n", "\r", curses.KEY_ENTER, " "):
                self.message = clear_cache()
            elif row != "clear-cache" and k == "d":
                st.reset(row.name)
                self.after_setting_change(row.name)
            elif row != "clear-cache" and k in ("\n", "\r", curses.KEY_ENTER, " "):
                if row.kind == "bool":
                    new = not st[row.name]
                elif row.kind == "choice":
                    ch = row.choices
                    new = ch[(ch.index(st[row.name]) + 1) % len(ch)]
                else:
                    new = self.prompt(f"{row.label} ({row.describe_range()}): ",
                                      row.format(st[row.name]))
                    if new is None:
                        continue
                try:
                    st.set(row.name, new)
                except ValueError as e:
                    self.message = str(e)
                    continue
                self.after_setting_change(row.name)
        self.message = ""
        if self.page:
            self.rerender_keep_position()

    def after_setting_change(self, name: str):
        """Save and apply one changed setting."""
        st = self.settings
        try:
            st.save()
        except OSError as e:
            self.message = f"Could not save settings: {e}"
            return
        if name == "general.languages":
            self.lang = st[name]
        elif name == "general.show_quotations":
            self.show_quotes = st[name]
        elif name == "general.show_tables":
            self.show_tables = st[name]
        elif name == "tui.show_contents":
            self.show_toc = st[name]
        elif name == "tui.colors":
            self.init_colors()
        elif name == "tui.mouse":
            self.apply_mouse()
        elif name == "general.cache_days":
            self.client = st.client(on_fetch=self.client.on_fetch)
        self.message = "Saved."

    # ---- events ------------------------------------------------------------ #
    def handle_resize(self):
        curses.update_lines_cols()
        if self.page and self.content_w() != self.render_width:
            self.rerender_keep_position()

    def lookup(self):
        word = self.prompt("Look up (Tab: suggestions): ", suggest=True)
        if word:
            self.open(word)

    def key_toc(self, k):
        toc = self.page.toc
        if k in ("\t", "\x1b", "c", curses.KEY_RIGHT, "l"):
            self.focus = "content"
        elif k in (curses.KEY_DOWN, "j"):
            self.toc_sel = min(len(toc) - 1, self.toc_sel + 1)
        elif k in (curses.KEY_UP, "k"):
            self.toc_sel = max(0, self.toc_sel - 1)
        elif k in (curses.KEY_NPAGE, " "):
            self.toc_sel = min(len(toc) - 1, self.toc_sel + self.body_h() - 1)
        elif k == curses.KEY_PPAGE:
            self.toc_sel = max(0, self.toc_sel - self.body_h() + 1)
        elif k in ("g", curses.KEY_HOME):
            self.toc_sel = 0
        elif k in ("G", curses.KEY_END):
            self.toc_sel = len(toc) - 1
        elif k in ("\n", "\r", curses.KEY_ENTER):
            self.jump_line(toc[self.toc_sel][2])
            self.focus = "content"
            return
        else:
            return self.key_content(k)
        if toc:
            self.jump_line(toc[self.toc_sel][2])

    def key_content(self, k):
        bh = self.body_h()
        if k in ("q", "Q"):
            self.running = False
        elif k in ("/", "s"):
            self.lookup()
        elif k == "?":
            self.show_help()
        elif k == "S":
            self.settings_screen()
        elif not self.page:
            if k == "l":
                self.change_lang()
            elif k in ("y", curses.KEY_F7):
                self.message = "There is no entry to copy yet."
            return
        elif k in (curses.KEY_DOWN, "j", "\x0e"):
            self.scroll(1)
        elif k in (curses.KEY_UP, "k", "\x10"):
            self.scroll(-1)
        elif k in (curses.KEY_NPAGE, " "):
            self.scroll(bh - 1)
        elif k in (curses.KEY_PPAGE, "\x02"):
            self.scroll(-(bh - 1))
        elif k in ("d", "\x04"):
            self.scroll(bh // 2)
        elif k in ("u", "\x15"):
            self.scroll(-(bh // 2))
        elif k in ("g", curses.KEY_HOME):
            self.jump_line(0)
            self.sync_toc()
        elif k in ("G", curses.KEY_END):
            self.jump_line(self.max_top())
            self.sync_toc()
        elif k == curses.KEY_RIGHT:
            self.hscroll += 8
        elif k in (curses.KEY_LEFT, "h"):
            self.hscroll = max(0, self.hscroll - 8)
        elif k == "]":
            self.jump_section(1)
        elif k == "[":
            self.jump_section(-1)
        elif k == "}":
            self.jump_section(1, languages_only=True)
        elif k == "{":
            self.jump_section(-1, languages_only=True)
        elif k in ("c", "\t"):
            if self.page.toc:
                self.show_toc = True
                self.focus = "toc"
                self.toc_sel = self.current_toc_index() or 0
        elif k == "t":
            self.show_toc = not self.show_toc
            self.save_setting("tui.show_contents", self.show_toc)
            self.rerender_keep_position()
        elif k in ("b", curses.KEY_BACKSPACE, "\x7f", "\b"):
            self.back()
        elif k == "B":
            self.forward()
        elif k == "L":
            self.choose_link()
        elif k == "l":
            self.change_lang()
        elif k == "x":
            self.show_quotes = not self.show_quotes
            self.save_setting("general.show_quotations", self.show_quotes)
            self.rerender_keep_position()
            self.message = "Quotations " + ("shown." if self.show_quotes else "hidden.")
        elif k == "T":
            self.show_tables = not self.show_tables
            self.save_setting("general.show_tables", self.show_tables)
            self.rerender_keep_position()
            self.message = "Tables " + ("shown." if self.show_tables else "hidden.")
        elif k == "n":
            self.find_next(1)
        elif k == "N":
            self.find_next(-1)
        elif k == "o":
            self.message = open_in_browser(page_url(self.page.word))
        elif k == "r":
            self.client.forget(self.page.word)
            self.open(self.page.word, push=False, top=self.top)
        elif k in ("y", curses.KEY_F7):
            self.copy_entry()

    def copy_entry(self):
        """The whole entry, as shown (all its languages and sections, without
        colours or links), into the clipboard."""
        text = "\n".join(l.rstrip() for l in self.page.view.plain).strip("\n") + "\n"
        self.message = "Copied the entry." if clipboard.copy(text) else \
            "Copied the entry, if the terminal lets programs use the clipboard."

    def change_lang(self):
        val = self.prompt("Languages (e.g. en, la, Spanish, all): ", self.lang)
        if val and val.strip():
            self.lang = val.strip()
            if self.page:
                self.render()
                self.top = 0
                self.sync_toc()
                self.check_language_filter()

    def find(self):
        if not self.page:
            return
        term = self.prompt("Find: ", self.find_term)
        if term is None:
            return
        self.find_term = term
        self.compute_matches()
        if term:
            self.find_next(1)
        else:
            self.message = ""

    def handle_mouse(self):
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return
        up = getattr(curses, "BUTTON4_PRESSED", 0)
        down = getattr(curses, "BUTTON5_PRESSED", 0)
        if bstate & up:
            self.scroll(-self.settings["tui.wheel_lines"])
        elif down and bstate & down:
            self.scroll(self.settings["tui.wheel_lines"])
        elif bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
            tw = self.toc_width()
            if self.page and tw and mx < tw and 1 <= my <= self.body_h():
                i = self.toc_top + my - 1
                if i < len(self.page.toc):
                    self.toc_sel = i
                    self.jump_line(self.page.toc[i][2])
            elif self.page and 1 <= my <= self.body_h() and mx > self.content_x():
                # (the text is drawn one column right of content_x)
                i = self.top + my - 1
                col = mx - self.content_x() - 1 + self.hscroll
                if i < len(self.page.lines):
                    for start, end, url, _ in self.line_links(i):
                        if start <= col < end:
                            self.follow(url)
                            break

    def run(self):
        while self.running:
            self.draw()
            try:
                k = self.scr.get_wch()
            except curses.error:
                continue
            except KeyboardInterrupt:
                break
            self.message = ""
            if k == curses.KEY_RESIZE:
                self.handle_resize()
            elif k == curses.KEY_MOUSE:
                self.handle_mouse()
            elif k in ("f", "\x06"):  # f or Ctrl-F
                self.find()
            elif self.focus == "toc" and self.page and self.page.toc:
                self.key_toc(k)
            else:
                self.focus = "content"
                self.key_content(k)


def main(argv=None) -> int:
    os.environ.setdefault("ESCDELAY", "25")
    ap = argparse.ArgumentParser(prog="py-wtk-tui",
                                 description=f"{program_title()}, in the terminal.")
    add_lookup_args(ap, "word or phrase to open")
    args = ap.parse_args(argv)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        # (e.g. started from a menu whose terminal could not be found)
        sys.exit("py-wtk-tui must run in a terminal; to start it from the applications "
                 "menu, the desktop needs a working terminal emulator.")
    word = " ".join(args.word).strip() or None
    try:
        curses.wrapper(lambda scr: App(scr, word, args.lang).run())
    except KeyboardInterrupt:
        pass
    return 0


def run():
    sys.exit(main())


if __name__ == "__main__":
    run()
