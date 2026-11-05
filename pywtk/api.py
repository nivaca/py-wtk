# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Talking to en.wiktionary.org."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from . import __version__
from .dom import Node, parse_html

BASE = "https://en.wiktionary.org"
WIKI = BASE + "/wiki/"
HTML_URL = BASE + "/api/rest_v1/page/html/{}"
SEARCH_URL = BASE + "/w/api.php"
USER_AGENT = f"py-wtk/{__version__} (command-line Wiktionary client; Python urllib)"
TIMEOUT = 20

# Errors callers should treat as "could not reach Wiktionary".
NetworkError = (urllib.error.URLError, OSError)


class NotFound(Exception):
    """The requested page does not exist."""


def _get(url: str, accept: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFound(url) from None
            if e.code in (429, 502, 503, 504) and attempt < 3:
                try:
                    delay = float(e.headers.get("Retry-After", ""))
                except ValueError:
                    delay = 2 ** attempt
                time.sleep(min(max(delay, 1), 10))
                continue
            raise
    raise RuntimeError("unreachable")


def page_title(word: str) -> str:
    return word.strip().replace(" ", "_")


def page_url(word: str) -> str:
    return WIKI + urllib.parse.quote(page_title(word))


#  Namespaces whose pages are entries, which the programs show themselves
#  (links to other namespaces, such as Appendix: or Wiktionary:, open in
#  the browser)
ENTRY_NAMESPACES = ("", "Reconstruction")
_URL_SAFE = "/:!$&'()*+,;=@~-._%"


def link_url(href: str, classes=frozenset()) -> str | None:
    """The full URL of a link of a page (the href of an <a>, with its
    classes), or None for links not worth following: to pages that do not
    exist yet, to files, to footnotes and to edit forms."""
    if not href or classes & {"new", "mw-file-description"}:
        return None
    if href.startswith("./"):
        path, _, frag = href[2:].partition("#")
        if "?" in path or not path or frag.startswith("cite_"):
            return None
        url = WIKI + urllib.parse.quote(urllib.parse.unquote(path), safe=_URL_SAFE)
        if frag:
            url += "#" + urllib.parse.quote(urllib.parse.unquote(frag), safe=_URL_SAFE)
        return url
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith(("https://", "http://")) and \
            not any(c <= " " or c == "\x7f" for c in href):
        return href
    return None


def entry_target(url: str) -> tuple[str, str | None] | None:
    """(page title, language) of a link to an entry of Wiktionary, the
    language taken from the anchor ('rosa#Latin' -> ('rosa', 'Latin'));
    None for any other link (to open in the browser)."""
    if not url.startswith(WIKI):
        return None
    path, _, frag = url[len(WIKI):].partition("#")
    title = urllib.parse.unquote(path).replace("_", " ").strip()
    namespace = title.split(":", 1)[0] if ":" in title else ""
    if not title or namespace not in ENTRY_NAMESPACES:
        return None
    language = urllib.parse.unquote(frag).replace("_", " ").split(":")[0].strip()
    return title, language or None


def get_page_html(word: str) -> str:
    url = HTML_URL.format(urllib.parse.quote(page_title(word), safe=""))
    return _get(url, "text/html").decode("utf-8", "replace")


def search(query: str, limit: int = 10) -> list[str]:
    """Page titles matching `query` (prefix search)."""
    params = urllib.parse.urlencode({
        "action": "opensearch", "search": query, "limit": limit,
        "namespace": 0, "format": "json",
    })
    data = json.loads(_get(f"{SEARCH_URL}?{params}", "application/json"))
    return data[1] if len(data) > 1 else []


def suggestions(word: str, limit: int = 8) -> list[str]:
    """Alternatives for a word that has no page; empty on network errors."""
    try:
        return [s for s in search(word, limit=limit) if s != word]
    except NetworkError:
        return []


class Client:
    """Fetches and parses pages, caching them in memory (missing pages included)
    and, when cache_dir is given, keeping the downloaded HTML on disk for
    max_age_days so that repeated lookups do not hit Wiktionary again."""

    def __init__(self, on_fetch: Callable[[str], None] | None = None,
                 cache_dir: Path | None = None, max_age_days: float = 0):
        self._cache: dict[str, Node | None] = {}
        self.on_fetch = on_fetch  # called with the title before a network fetch
        self.cache_dir = Path(cache_dir) / "pages" if cache_dir and max_age_days > 0 else None
        self.max_age = max_age_days * 86400

    # ---- disk cache ------------------------------------------------------- #
    def _disk_path(self, key: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (hashlib.sha1(key.encode("utf-8")).hexdigest() + ".html.gz")

    def _disk_read(self, key: str) -> str | None:
        path = self._disk_path(key)
        try:
            if path and time.time() - path.stat().st_mtime < self.max_age:
                return gzip.decompress(path.read_bytes()).decode("utf-8")
        except (OSError, EOFError, gzip.BadGzipFile, UnicodeDecodeError):
            pass
        return None

    def _disk_write(self, key: str, html: str):
        path = self._disk_path(key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_bytes(gzip.compress(html.encode("utf-8")))
            os.replace(tmp, path)
        except OSError:
            pass  # the disk cache is only an optimisation

    # ---- pages ------------------------------------------------------------ #
    def page(self, title: str) -> Node:
        """Parsed page; raises NotFound, or a NetworkError on failure."""
        key = page_title(title)
        if key not in self._cache:
            html = self._disk_read(key)
            if html is None:
                if self.on_fetch:
                    self.on_fetch(title)
                try:
                    html = get_page_html(title)
                except NotFound:
                    self._cache[key] = None
                else:
                    self._disk_write(key, html)
            if html is not None:
                self._cache[key] = parse_html(html)
        root = self._cache[key]
        if root is None:
            raise NotFound(title)
        return root

    def subpage(self, title: str) -> Node | None:
        """Like page(), but returns None instead of raising (for optional extras)."""
        try:
            return self.page(title)
        except (NotFound, *NetworkError):
            return None

    def forget(self, title: str) -> None:
        """Drop a page from both caches, so the next request downloads it again."""
        key = page_title(title)
        self._cache.pop(key, None)
        path = self._disk_path(key)
        if path:
            try:
                path.unlink()
            except OSError:
                pass


def _cached_files(cache_dir: Path, suffixes: tuple[str, ...]) -> list[tuple[Path, int]]:
    """The files of the disk cache ending in SUFFIXES, with their sizes."""
    pages = Path(cache_dir) / "pages"
    if not pages.is_dir():
        return []
    out = []
    for f in pages.iterdir():
        if f.name.endswith(suffixes):
            try:
                out.append((f, f.stat().st_size))
            except OSError:
                pass
    return out


def clear_disk_cache(cache_dir: Path) -> tuple[int, int]:
    """Delete cached pages. Returns (files removed, bytes freed)."""
    n = size = 0
    for f, f_size in _cached_files(cache_dir, (".html.gz", ".tmp")):
        try:
            f.unlink()
        except OSError:
            continue
        n += 1
        size += f_size
    return n, size


def disk_cache_usage(cache_dir: Path) -> tuple[int, int]:
    """(number of cached pages, total bytes)."""
    files = _cached_files(cache_dir, (".html.gz",))
    return len(files), sum(size for _, size in files)
