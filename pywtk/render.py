# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Turning Wiktionary HTML into wrapped, styled lines of text (or JSON)."""

from __future__ import annotations

import re
import textwrap
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Iterator

from .api import link_url
from .dom import HEADINGS, Node, heading_of
from .entry import Language, Options, norm_title
from .text import clean_inline, display_width, strip_ansi

Loader = Callable[[str], "Node | None"]  # page title -> parsed page, or None


class Style:
    """ANSI styling; with enabled=False every method returns text unchanged.
    The TUI turns these ANSI codes into curses attributes.  Links are OSC 8
    hyperlinks (made only if `links`, by default when enabled), which
    terminals that know them make clickable and the TUI and the window
    follow."""

    def __init__(self, enabled: bool, links: bool | None = None):
        self.on = enabled
        self.links = enabled if links is None else links

    def _w(self, code, s):
        return f"\033[{code}m{s}\033[0m" if self.on and s else s

    def title(self, s): return self._w("1;4", s)
    def lang(self, s): return self._w("1;36", s)
    def h3(self, s): return self._w("1;33", s)
    def h4(self, s): return self._w("1;35", s)
    def h5(self, s): return self._w("1;34", s)
    def headword(self, s): return self._w("1", s)
    def example(self, s): return self._w("32", s)
    def quote(self, s): return self._w("2", s)
    def dim(self, s): return self._w("2", s)

    def link(self, url, s):
        return f"\033]8;;{url}\033\\{s}\033]8;;\033\\" if self.links and s else s


#  While an entry is rendered, a link is "\x02URL\x03text\x04" in the text
#  (control characters, which pages never have), so that it survives the
#  cleanup of the text; it becomes a Style.link when the text is wrapped.
LINK_OPEN, LINK_MID, LINK_CLOSE = "\x02", "\x03", "\x04"
LINK_RE = re.compile("\x02([^\x02-\x04]*)\x03([^\x02-\x04]*)\x04")
_NO_MARKERS = dict.fromkeys(map(ord, LINK_OPEN + LINK_MID + LINK_CLOSE))


def split_links(s: str) -> tuple[str, list[tuple[int, int, str]]]:
    """S without the link markers, and the links in it as (start, end,
    URL), positions in the text without the markers."""
    plain: list[str] = []
    spans: list[tuple[int, int, str]] = []
    n = pos = 0

    def add(text):
        nonlocal n
        text = text.translate(_NO_MARKERS)       # (those of a broken link)
        plain.append(text)
        n += len(text)

    for m in LINK_RE.finditer(s):
        add(s[pos:m.start()])
        start = n
        add(m.group(2))
        if n > start:
            spans.append((start, n, m.group(1)))
        pos = m.end()
    add(s[pos:])
    return "".join(plain), spans


SKIP_TAGS = {"style", "script", "link", "meta", "figure", "img", "audio", "video",
             "source", "noscript", "math", "annotation"}
SKIP_CLASSES = {"mw-editsection", "mw-empty-elt", "etymonid", "audiotable",
                "interProject", "sister-project", "sister-wikipedia", "noprint",
                "reference", "mw-cite-backlink", "maintenance-line", "checktrans",
                "ib-content-hidden", "serial-comma", "metadata", "mwe-math-element",
                "attentionseeking"}
# Wrappers of quotations ({{quote-*}} templates and {{Q}}).
QUOTE_CLASSES = {"citation-whole", "wiktQuote"}
BLOCK_TAGS = {"p", "div", "ul", "ol", "dl", "dd", "dt", "li", "table", "section",
              "blockquote", "center", "pre", "h2", "h3", "h4", "h5", "h6", "hr"}


class Renderer:
    """Accumulates rendered lines in self.lines, and the heading positions in
    self.toc as (heading level, title, line index)."""

    def __init__(self, style: Style, width: int, options: Options | None = None,
                 loader: Loader | None = None):
        self.s = style
        self.width = max(width, 40)
        self.opts = options or Options()
        self.loader = loader if self.opts.load_subpages else None
        self.lines: list[str] = []
        self.toc: list[tuple[int, str, int]] = []

    # ---- helpers ---------------------------------------------------------- #
    def skip(self, n: Node) -> bool:
        if n.tag in SKIP_TAGS:
            return True
        if n.classes & SKIP_CLASSES:
            return True
        st = n.attrs.get("style", "").replace(" ", "").lower()
        if "display:none" in st:
            return True
        if n.tag == "sup":
            t = n.text().strip()
            if t in ("(key)", "key") or re.fullmatch(r"\[\d+\]", t):
                return True
        if not self.opts.show_quotes and n.classes & QUOTE_CLASSES:
            return True
        return False

    def is_block(self, n: Node) -> bool:
        return n.tag in BLOCK_TAGS

    def has_block(self, n: Node) -> bool:
        return any(isinstance(c, Node) and not self.skip(c) and
                   (self.is_block(c) or self.has_block(c)) for c in n.children)

    def runs(self, n: Node) -> Iterator[tuple[str, str | Node]]:
        """The children of N, as ("text", inline text) for each stretch of
        inline content and ("block", node) for each block between them."""
        buf: list[str] = []
        for c in n.children:
            if isinstance(c, str):
                buf.append(c)
            elif self.skip(c):
                continue
            elif c.tag == "br":
                buf.append("\n")
            elif self.is_block(c) or self.has_block(c):
                if buf:
                    yield "text", "".join(buf)
                    buf = []
                yield "block", c
            else:
                buf.append(self.piece(c))
        if buf:
            yield "text", "".join(buf)

    def inline(self, n: Node) -> str:
        parts = []
        for c in n.children:
            if isinstance(c, str):
                parts.append(c)
            elif self.skip(c):
                continue
            elif c.tag == "br":
                parts.append("\n")
            elif c.tag == "sup":
                t = clean_inline(c.text())
                # word-like superscripts are labels (e.g. "hablastú" -> "hablas (tú)")
                parts.append(f" ({t})" if re.fullmatch(r"[^\W\d_]{2,}", t) else t)
            else:
                parts.append(self.piece(c))
        return "".join(parts)

    def piece(self, n: Node) -> str:
        """The text of the inline element N (with its link, if it is one)."""
        return self.anchor(n) if n.tag == "a" and self.s.links else self.inline(n)

    def anchor(self, a: Node) -> str:
        """The text of the link A, marked as a link if it leads somewhere
        (spaces at its ends go outside the marks)."""
        text = self.inline(a)
        url = link_url(a.attrs.get("href", ""), a.classes)
        core = text.strip()
        if not url or not core or LINK_OPEN in core:
            return text
        lead = text[:len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        return f"{lead}{LINK_OPEN}{url}{LINK_MID}{core}{LINK_CLOSE}{trail}"

    def linked(self, plain: str, spans, start: int = 0) -> str:
        """PLAIN, a piece of a text beginning at START, with the links of
        SPANS (positions in the whole text) made Style.links."""
        if not spans:
            return plain
        end = start + len(plain)
        out, pos = [], 0
        for s, e, url in spans:
            s, e = max(s, start) - start, min(e, end) - start
            if s >= e:
                continue
            out.append(plain[pos:s])
            out.append(self.s.link(url, plain[s:e]))
            pos = e
        out.append(plain[pos:])
        return "".join(out)

    def emit(self, text: str, indent: str, hang: str | None = None, fmt=None):
        text = clean_inline(text)
        if not text:
            return
        hang = indent if hang is None else hang
        first = True
        for para in text.split("\n"):
            plain, spans = split_links(para)
            lead = len(plain) - len(plain.lstrip())
            plain = plain.strip()
            if not plain:
                continue
            spans = [(s - lead, e - lead, u) for s, e, u in spans]
            prefix = indent if first else hang
            wrapped = textwrap.wrap(plain, width=self.width, initial_indent=prefix,
                                    subsequent_indent=hang, break_on_hyphens=False,
                                    break_long_words=False)
            first = False
            pos = 0
            for j, line in enumerate(wrapped):
                if spans:
                    # each line is a piece of the text (only the spaces where it
                    # was broken are left out): find it, to put its links in
                    pre = prefix if j == 0 else hang
                    body = line[len(pre):]
                    at = plain.find(body, pos)
                    if at >= 0:
                        line = pre + self.linked(body, spans, at)
                        pos = at + len(body)
                if fmt:
                    pre = len(line) - len(line.lstrip())
                    line = line[:pre] + fmt(line[pre:])
                self.lines.append(line)

    def blank(self):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    # ---- block walker ----------------------------------------------------- #
    def block(self, n: Node, indent: str, fmt=None):
        """Render children of n: runs of inline content become paragraphs."""
        for kind, run in self.runs(n):
            if kind == "text":
                self.emit(run, indent, fmt=fmt)
            else:
                self.element(run, indent, fmt)

    def element(self, n: Node, indent: str, fmt=None):
        tag, cls = n.tag, n.classes
        if tag in HEADINGS or tag == "section":
            return  # sections handled by render_section
        if tag in ("ul", "ol"):
            self.list_(n, indent, ordered=(tag == "ol"), fmt=fmt)
        elif tag == "dl":
            for c in n.children:
                if isinstance(c, Node) and not self.skip(c):
                    if c.tag == "dt":
                        self.block(c, indent, fmt=self.s.headword)
                    else:
                        sub_fmt = fmt
                        if c.find(lambda x: "h-usage-example" in x.classes):
                            sub_fmt = self.s.example
                        elif c.find(lambda x: "h-quotation" in x.classes) or \
                                "h-quotation" in c.classes:
                            sub_fmt = self.s.quote
                        self.block(c, indent + "  ", sub_fmt)
        elif tag == "table" and "translations" in cls:
            for td in n.iter():
                if td.tag == "td" and not self.skip(td):
                    self.block(td, indent, fmt)
        elif tag == "table":
            if self.opts.show_tables:
                self.table(n, indent)
        elif "NavFrame" in cls:
            head = n.find(lambda x: "NavHead" in x.classes)
            if head is not None:
                self.emit(self.inline(head), indent, fmt=self.s.headword)
            for c in n.children:
                if isinstance(c, Node) and not self.skip(c) and "NavHead" not in c.classes:
                    if self.is_block(c) or self.has_block(c):
                        self.element(c, indent + "  ", fmt)
                    else:
                        self.emit(self.inline(c), indent + "  ", fmt=fmt)
        elif tag == "p" and n.find(lambda x: "headword" in x.classes):
            self.blank()
            self.emit(self.inline(n), indent, fmt=self.s.headword)
            self.blank()
        elif tag == "p":
            self.block(n, indent, fmt)
            self.blank()
        else:
            self.block(n, indent, fmt)

    def list_(self, n: Node, indent: str, ordered: bool, fmt=None):
        i = 0
        for li in n.children:
            if not isinstance(li, Node) or li.tag != "li" or self.skip(li):
                continue
            i += 1
            if li.classes & QUOTE_CLASSES or any(
                    isinstance(c, Node) and c.classes & QUOTE_CLASSES for c in li.children):
                if not self.opts.show_quotes:
                    continue
                li_fmt = self.s.quote
            else:
                li_fmt = fmt
            marker = f"{i}. " if ordered else "• "
            hang = indent + " " * len(marker)
            # inline lead text of the item, then nested blocks; the marker
            # goes on the first line of whichever comes first
            first = True
            for kind, run in self.runs(li):
                if kind == "text":
                    if clean_inline(run):
                        self.emit(run, indent + marker if first else hang, hang, li_fmt)
                        first = False
                    continue
                start = len(self.lines)
                self.element(run, hang, li_fmt)
                if first:
                    self.put_marker(start, indent, marker, hang)
                    first = False

    def put_marker(self, start: int, indent: str, marker: str, hang: str):
        """Puts a list MARKER on the first line rendered since START (an
        item that starts with a block)."""
        while start < len(self.lines) and not self.lines[start].strip():
            del self.lines[start]
        if start < len(self.lines) and self.lines[start].startswith(hang):
            self.lines[start] = indent + marker + self.lines[start][len(hang):]
        else:
            self.lines.insert(start, (indent + marker).rstrip())

    def table(self, n: Node, indent: str):
        caption = n.find(lambda x: x.tag == "caption")
        if caption is not None:
            self.emit(self.inline(caption), indent, fmt=self.s.headword)
        rows: list[list[str]] = []
        for tr in n.iter():
            if tr.tag != "tr" or self.skip(tr):
                continue
            # ignore rows of nested tables
            p = tr.parent
            while p is not None and p.tag != "table":
                p = p.parent
            if p is not n:
                continue
            cells = []
            for td in tr.children:
                if isinstance(td, Node) and td.tag in ("td", "th") and not self.skip(td):
                    # (the cells keep their link marks, see below)
                    cells.append(clean_inline(self.inline(td)).replace("\n", ", "))
                    try:
                        span = int(td.attrs.get("colspan", "1"))
                    except ValueError:
                        span = 1
                    cells.extend([""] * (min(span, 20) - 1))
            if any(cells):
                rows.append(cells)
        if not rows:
            return
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        plain = [[split_links(c)[0] for c in r] for r in rows]
        widths = [max(display_width(r[i]) for r in plain) for i in range(ncol)]
        total = len(indent) + sum(widths) + 2 * (ncol - 1)
        if total <= self.width + 20:
            for r in rows:
                cells = []
                for i, c in enumerate(r):
                    text, spans = split_links(c)
                    cells.append(self.linked(text, spans).rstrip() if i == ncol - 1 else
                                 self.linked(text, spans) + " " * (widths[i] - display_width(text)))
                self.lines.append((indent + "  ".join(cells)).rstrip())
        else:  # too wide: one row per line
            for r in rows:
                self.emit(" | ".join(c for c in r if c), indent, indent + "    ")
        self.blank()

    def inline_translation_subpage(self, sec: Node, indent: str):
        """Large entries keep translations on a 'WORD/translations' subpage."""
        link = sec.find(lambda x: x.tag == "a" and re.match(
            r"^\./[^#]+/translations#", x.attrs.get("href", "")))
        if link is None:
            return
        href = urllib.parse.unquote(link.attrs["href"][2:])
        page, anchor = href.split("#", 1)
        sub = self.loader(page)
        if sub is None:
            return
        anchor = anchor.replace("_", " ").lower()
        for s in sub.iter():
            h = heading_of(s) if s.tag == "section" else None
            if h is None or h.tag == "h2":
                continue
            if clean_inline(h.text()).lower() == anchor or \
                    h.attrs.get("id", "").replace("_", " ").lower() == anchor:
                for t in s.iter():
                    if t.tag == "section":
                        th = heading_of(t)
                        if th is not None and norm_title(th.text()) == "translations":
                            self.section_body(t, indent)
                return

    # ---- sections --------------------------------------------------------- #
    def section_body(self, sec: Node, indent: str):
        """Render a section's own content (not its heading or subsections)."""
        for c in sec.children:
            if isinstance(c, Node):
                if c.tag in HEADINGS or c.tag == "section" or self.skip(c):
                    continue
                self.element(c, indent)
            elif clean_inline(c):
                self.emit(c, indent)

    def render_section(self, sec: Node, include=None, exclude=None, depth_indent=""):
        """Render a section and its subsections, honouring include/exclude
        (sets of normalised section names; include=None means everything)."""
        exclude = self.opts.exclude if exclude is None else exclude
        h = heading_of(sec)
        title = clean_inline(h.text()) if h is not None else ""
        level = int(h.tag[1]) if h is not None else 2
        key = norm_title(title)

        if exclude and key in exclude:
            return
        wanted = include is None or key in include or level == 2
        if wanted:
            if level > 2:  # language (h2) headings are written by render_entry
                fmt = {3: self.s.h3, 4: self.s.h4}.get(level, self.s.h5)
                self.blank()
                self.toc.append((level, title, len(self.lines)))
                self.lines.append(depth_indent + fmt(title))
            body_indent = depth_indent + ("  " if level > 2 else "")
            self.section_body(sec, body_indent)
            if key == "translations" and self.loader is not None:
                self.inline_translation_subpage(sec, body_indent)
            # a selected section brings its subsections along, except "Etymology N",
            # which on Wiktionary wraps whole entries
            child_include = None if (include is not None and key in include and level > 2
                                     and key != "etymology") else include
        else:
            child_include = include
        sub_indent = depth_indent + ("  " if level > 2 and wanted else "")
        for c in sec.subsections():
            self.render_section(c, child_include, exclude,
                                sub_indent if wanted else depth_indent)


# --------------------------------------------------------------------------- #
# Whole entries
# --------------------------------------------------------------------------- #
@dataclass
class Rendered:
    """A rendered entry. toc holds (depth, title, line index): depth 0 is a
    language, 1 an h3 section (Etymology, Noun, ...), 2 an h4, and so on."""
    lines: list[str]
    toc: list[tuple[int, str, int]] = field(default_factory=list)
    language_lines: list[int] = field(default_factory=list)
    _plain: list[str] | None = field(default=None, repr=False)

    @property
    def plain(self) -> list[str]:
        """The lines without ANSI codes."""
        if self._plain is None:
            self._plain = [strip_ansi(l) for l in self.lines]
        return self._plain

    def text(self) -> str:
        return "\n".join(self.lines)

    def toc_index(self, top: int) -> int | None:
        """The item of the contents being read when line TOP is the first
        shown (None if there are none)."""
        if not self.toc:
            return None
        idx = 0
        for i, (_, _, line) in enumerate(self.toc):
            if line > top + 1:
                break
            idx = i
        return idx

    def language_line(self, language: str) -> int | None:
        """The line of the heading of LANGUAGE (a name), if it is shown."""
        return next((line for depth, name, line in self.toc
                     if depth == 0 and name.casefold() == language.casefold()), None)


def render_entry(word: str, languages: list[Language], style: Style, width: int,
                 options: Options | None = None, loader: Loader | None = None) -> Rendered:
    """Render the given languages of a page: a title line, then for each
    language a heading followed by its sections."""
    opts = options or Options()
    r = Renderer(style, width, opts, loader)
    toc: list[tuple[int, str, int]] = []
    lang_lines: list[int] = []
    r.lines.append(style.title(word))
    for lang in languages:
        r.blank()
        start_toc = len(r.toc)
        lang_lines.append(len(r.lines))
        toc.append((0, lang.name, len(r.lines)))
        r.lines.append(style.lang(lang.name) + (style.dim(f"  [{lang.code}]") if lang.code else ""))
        if opts.include is None:  # content directly under the language heading (rare)
            r.section_body(lang.section, "")
        for c in lang.section.subsections():
            r.render_section(c, opts.include, opts.exclude)
        toc.extend((lvl - 2, title, ln) for lvl, title, ln in r.toc[start_toc:])
        r.blank()

    # strip trailing spaces and collapse runs of blank lines, remapping positions
    keep: list[str] = []
    remap: dict[int, int] = {}
    for i, line in enumerate(r.lines):
        line = line.rstrip()
        if line == "" and keep and keep[-1] == "":
            remap[i] = len(keep) - 1
            continue
        remap[i] = len(keep)
        keep.append(line)
    return Rendered(
        lines=keep,
        toc=[(d, t, remap.get(ln, ln)) for d, t, ln in toc],
        language_lines=[remap.get(ln, ln) for ln in lang_lines],
    )


def section_to_json(sec: Node, options: Options, loader: Loader | None = None) -> dict:
    h = heading_of(sec)
    r = Renderer(Style(False), 10_000, options, loader)
    r.section_body(sec, "")
    return {
        "title": clean_inline(h.text()) if h is not None else "",
        "text": "\n".join(r.lines).strip(),
        "sections": [section_to_json(c, options, loader) for c in sec.subsections()],
    }


def entry_to_json(languages: list[Language], options: Options | None = None,
                  loader: Loader | None = None) -> list[dict]:
    opts = options or Options()
    loader = loader if opts.load_subpages else None
    return [{
        "language": lang.name, "code": lang.code,
        "sections": [section_to_json(c, opts, loader) for c in lang.section.subsections()],
    } for lang in languages]
