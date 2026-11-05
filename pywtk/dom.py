# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""A minimal DOM, enough to walk Wiktionary's Parsoid HTML."""

from __future__ import annotations

from html.parser import HTMLParser

VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
             "meta", "source", "track", "wbr"}
HEADINGS = ("h2", "h3", "h4", "h5", "h6")


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list = []  # Node or str
        self.parent = parent

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def iter(self):
        """All descendant elements, depth first."""
        for c in self.children:
            if isinstance(c, Node):
                yield c
                yield from c.iter()

    def find(self, pred):
        return next((n for n in self.iter() if pred(n)), None)

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)

    def subsections(self) -> list["Node"]:
        return [c for c in self.children if isinstance(c, Node) and c.tag == "section"]


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(src: str) -> Node:
    b = _Builder()
    b.feed(src)
    b.close()
    return b.root


def heading_of(section: Node) -> Node | None:
    for c in section.children:
        if isinstance(c, Node) and c.tag in HEADINGS:
            return c
    return None
