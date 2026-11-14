#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Takes the screenshots of the README: the three programs (the command
line, the terminal in full screen and the window, the window both light and
dark), looking up the same word.

    python3 tools/screenshots.py [-o FOLDER] [--only cli,tui,gui]
                                 [--looks light,dark] [--word rosa]
                                 [--lang la] [--scale 2]

It writes FOLDER/cli.png, FOLDER/tui.png and FOLDER/gui_LOOK.png (by
default in docs/img/, where the READMEs would take them from), at SCALE
times the size of the screen (2 by default, sharp on screens of high
resolution).  Each program runs with settings and a cache of its own, in a
temporary folder, so the user's settings are not touched (and the pages are
downloaded afresh):

* the window (py-wtk-gui); only its own window is captured, with
  ImageMagick's import, never the screen.  If Xvfb is installed the window
  is opened there, out of sight and with room for any scale; if not, on the
  screen, and the scale is made smaller when the window would not fit;
* the command line (py-wtk, brief) and the terminal in full screen
  (py-wtk-tui) in a hidden tmux terminal of a fixed size; what it shows,
  with its colours, is written as a web page like a terminal, and Chrome
  (without a window: --headless --screenshot) takes it.

It needs Linux with an X display (XWayland is enough) or Xvfb, ImageMagick,
tmux and Google Chrome (or Chromium), and a connection to Wiktionary; the
program itself needs none of them.
"""

import argparse
import html
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = ("cli", "tui", "gui")
LOOKS = ("light", "dark")

#  The size of the hidden terminals (columns, lines) and of the window
#  (pixels, before the scale)
TERMINAL = {"cli": (96, 40), "tui": (110, 34)}
WINDOW = (1000, 640)
CONTENTS = 210                  # the width of the window's contents pane
SCALE = 2

#  The colours of the terminal drawn: those of Konsole's Breeze, its usual
#  scheme (background, text, then the 16 colours of the ANSI codes)
BACKGROUND, FOREGROUND = "#232627", "#fcfcfc"
ANSI = ["#232627", "#ed1515", "#11d116", "#f67400", "#1d99f3", "#9b59b6",
        "#1abc9c", "#fcfcfc", "#7f8c8d", "#c0392b", "#1cdc9a", "#fdbc4b",
        "#3daee9", "#8e44ad", "#16a085", "#ffffff"]
FONTS = ("Hack", "DejaVu Sans Mono", "Liberation Mono", "monospace")
#  The terminal's letters (pixels, before the scale), the width of one (that
#  of these fonts, a little more) and the space around the text
FONT_SIZE, CHAR_WIDTH, LINE_HEIGHT, MARGIN = 15, 0.61, 1.3, 12
#  The prompt drawn before the command line's command
PROMPT = "\x1b[1;32m$\x1b[0m "


def say(text: str):
    print(text, flush=True)


# ---------------------------------------------------------------------------
#  Settings of their own for each program

def settings_folder(dark: bool, scale: float = 1) -> str:
    """A temporary folder with a configuration file (dark or light, and the
    contents pane as wide as the scale needs) and a cache folder."""
    folder = tempfile.mkdtemp(prefix="py-wtk-shot-")
    with open(os.path.join(folder, "config.toml"), "w", encoding="utf-8") as f:
        f.write(f"[gui]\ncontents_width = {min(700, round(CONTENTS * scale))}\n"
                "remember_window = false\n"
                f"\n[appearance]\ndark_mode = {str(dark).lower()}\n")
    return folder


def environment(folder: str) -> dict:
    env = dict(os.environ)
    env.pop("PY_WKT_CONFIG", None)              # (the name of earlier versions)
    env["PY_WTK_CONFIG"] = folder
    env["XDG_CACHE_HOME"] = os.path.join(folder, "cache")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# ---------------------------------------------------------------------------
#  The window

class Display:
    """Where the window is opened: an Xvfb of its own if there is one (out of
    sight, as large as needed), the screen if not."""

    def __init__(self, scale: float):
        self.server = None
        self.name = os.environ.get("DISPLAY", "")
        if shutil.which("Xvfb"):
            width, height = WINDOW
            size = f"{math.ceil(width * scale) + 200}x{math.ceil(height * scale) + 400}x24"
            read, write = os.pipe()
            self.server = subprocess.Popen(
                ["Xvfb", "-displayfd", str(write), "-screen", "0", size,
                 "-nolisten", "tcp"], pass_fds=(write,),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.close(write)
            with os.fdopen(read) as f:
                number = f.readline().strip()
            if not number:
                raise SystemExit("Xvfb did not start")
            self.name = f":{number}"

    def close(self):
        if self.server:
            self.server.terminate()
            self.server.wait()


def gui(look: str, word: str, lang: str, out: str, scale: float, display: Display):
    """The window, in a process of its own (with its settings)."""
    scale = fit(scale, display.name)
    folder = settings_folder(dark=look == "dark", scale=scale)
    env = environment(folder)
    env["DISPLAY"] = display.name
    env.pop("WAYLAND_DISPLAY", None)
    #  (Tk's letters are drawn by Xft, which does not follow Tk's scaling but
    #  the dpi of fontconfig: this one, for this window only)
    env["FONTCONFIG_FILE"] = os.path.join(folder, "fonts.conf")
    with open(env["FONTCONFIG_FILE"], "w", encoding="utf-8") as f:
        f.write(f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <match target="pattern">
    <edit name="dpi" mode="assign"><double>{96 * scale}</double></edit>
  </match>
</fontconfig>
""")
    try:
        subprocess.run([sys.executable, os.path.abspath(__file__), "--child-gui",
                        word, lang, out, str(scale)], env=env, check=True)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def gui_child(word: str, lang: str, out: str, scale: str):
    sys.path.insert(0, ROOT)
    from pywtk import gui as program
    root = tk.Tk(className=program.WM_CLASS)
    #  (the fonts are given in points, so they grow with Tk's scaling; the
    #  window too, with its size)
    width, height = WINDOW
    scale = float(scale)
    root.tk.call("tk", "scaling", 96 / 72 * scale)
    program.set_icon(root)
    app = program.App(root, word, lang, None, None)
    root.geometry(f"{round(width * scale)}x{round(height * scale)}")

    def wait(ready, seconds=90):
        end = time.time() + seconds
        while time.time() < end:
            root.update()
            if ready():
                return
            time.sleep(0.03)
        raise SystemExit("the window did not get ready (no connection to Wiktionary?)")
    #  the entry shown, and no longer busy (also after re-wrapping to the size)
    wait(lambda: app.view is not None and app.word == word and
         str(root.cget("cursor")) == "")
    for _ in range(40):
        root.update()
        time.sleep(0.03)
    wait(lambda: str(root.cget("cursor")) == "")
    app.text.focus_set()
    for _ in range(20):                 # (all drawn)
        root.update()
        time.sleep(0.03)
    #  The menu bar is a window of its own (Tk keeps it outside the window, and
    #  import does not take it with it): both are taken, and put one over the
    #  other.  Only the program's windows, never the screen.
    clones = [str(w) for w in root.tk.call("winfo", "children", ".")
              if str(w).startswith(".#")]      # (the menu bar on screen)
    menu_bar = root.tk.call("winfo", "id", clones[0]) if clones else None
    if menu_bar:
        top = out + ".menu.png"
        capture(menu_bar, top)
        capture(root.winfo_id(), out + ".window.png")
        subprocess.run([magick(), top, out + ".window.png", "-append", out], check=True)
        os.remove(top)
        os.remove(out + ".window.png")
    else:
        capture(root.winfo_id(), out)
    root.destroy()


def fit(scale: float, display: str) -> float:
    """SCALE, or a smaller one if the window would not fit on the screen of
    DISPLAY (with the menu bar, and the panel of the desktop)."""
    width, height = WINDOW
    root = tk.Tk(screenName=display)
    room = min((root.winfo_screenwidth() - 20) / width,
               (root.winfo_screenheight() - 120) / height)
    root.destroy()
    if scale > room:
        say(f"  (the screen is too small for --scale {scale:g}: using {room:.2f}; "
            "Xvfb gives room for any scale)")
        return room
    return scale


def magick() -> str:
    """ImageMagick's command for putting images together."""
    return "magick" if shutil.which("magick") else "convert"


def capture(window_id, out: str):
    """The window WINDOW_ID (only it) as an image."""
    subprocess.run(["import", "-window", str(window_id), out], check=True)


# ---------------------------------------------------------------------------
#  The terminals: tmux, then the screen as a web page that Chrome takes

def chrome() -> str:
    for name in ("google-chrome", "chromium-browser", "chromium"):
        if shutil.which(name):
            return name
    raise SystemExit("Chrome or Chromium is needed for the terminals")


def shoot(url: str, size: tuple[int, int], out: str, scale: float, folder: str):
    """The page at URL, of SIZE (pixels before the scale), as an image."""
    width, height = size
    subprocess.run(
        [chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={width},{height}", f"--screenshot={out}",
         f"--force-device-scale-factor={scale:g}",
         f"--user-data-dir={os.path.join(folder, 'chrome')}",
         "--force-prefers-reduced-motion", url],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)


class Tmux:
    """A hidden terminal of a size of its own, on a server of its own."""

    def __init__(self, columns: int, lines: int, command: list[str], env: dict):
        self.socket = f"py-wtk-shots-{os.getpid()}"
        settings = {k: env[k] for k in ("PY_WTK_CONFIG", "XDG_CACHE_HOME",
                                        "PYTHONDONTWRITEBYTECODE")}
        self.run("-f", "/dev/null", "new-session", "-d", "-s", "shot",
                 "-x", str(columns), "-y", str(lines),
                 *[a for k, v in settings.items() for a in ("-e", f"{k}={v}")],
                 " ".join(map(_quoted, command)))
        self.run("set-option", "-g", "status", "off")

    def run(self, *args) -> str:
        return subprocess.run(["tmux", "-L", self.socket, *args],
                              capture_output=True, text=True, check=True).stdout

    def screen(self, colours: bool = False) -> str:
        return self.run("capture-pane", "-p", "-t", "shot", *(["-e"] if colours else []))

    def wait_for(self, text: str, seconds: float = 90):
        end = time.time() + seconds
        while text not in self.screen():
            if time.time() > end:
                raise SystemExit(f'did not see "{text}" in the terminal '
                                 "(no connection to Wiktionary?)")
            time.sleep(0.2)
        time.sleep(0.5)                 # (the rest drawn too)

    def close(self):
        subprocess.run(["tmux", "-L", self.socket, "kill-server"], capture_output=True)


def _quoted(arg: str) -> str:
    return "'" + arg.replace("'", "'\\''") + "'"


def cli(word: str, lang: str, out: str, scale: float):
    """py-wtk, brief, after a prompt with its command (the terminal is kept
    open afterwards, to be captured)."""
    folder = settings_folder(dark=False)
    columns, lines = TERMINAL["cli"]
    shown = f"py-wtk {word} -l {lang} -b"
    script = (f"printf '%s%s\\n' {_quoted(PROMPT)} {_quoted(shown)}; "
              f"{_quoted(sys.executable)} {_quoted(os.path.join(ROOT, 'py-wtk'))} "
              f"{_quoted(word)} -l {_quoted(lang)} -b --no-pager; exec sleep 3600")
    term = Tmux(columns, lines, ["sh", "-c", script], environment(folder))
    try:
        term.wait_for("https://en.wiktionary.org/wiki/")       # (its last line)
        draw(term.screen(colours=True), columns, out, scale, folder)
    finally:
        term.close()
        shutil.rmtree(folder, ignore_errors=True)


def tui(word: str, lang: str, out: str, scale: float):
    folder = settings_folder(dark=False)
    columns, lines = TERMINAL["tui"]
    term = Tmux(columns, lines, [sys.executable, os.path.join(ROOT, "py-wtk-tui"),
                                 word, "-l", lang], environment(folder))
    try:
        term.wait_for("Etymology")      # (in the contents and the entry)
        time.sleep(1)
        draw(term.screen(colours=True), columns, out, scale, folder)
    finally:
        term.close()
        shutil.rmtree(folder, ignore_errors=True)


SGR = re.compile(r"\x1b\[([0-9;]*)m")
#  Other codes that are not drawn, such as OSC 8 hyperlinks (ended by ST or BEL)
OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")


def styled(text: str) -> list[tuple[str, tuple]]:
    """TEXT (with ANSI codes) as (piece, (foreground, background, bold, dim))."""
    out = []
    fg, bg, bold, dim, reverse = None, None, False, False, False
    at = 0
    for m in SGR.finditer(text):
        if m.start() > at:
            out.append((text[at:m.start()], _style(fg, bg, bold, dim, reverse)))
        at = m.end()
        codes = [int(c) if c else 0 for c in m.group(1).split(";")]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                fg, bg, bold, dim, reverse = None, None, False, False, False
            elif c == 1:
                bold = True
            elif c == 2:
                dim = True
            elif c == 22:
                bold = dim = False
            elif c == 7:
                reverse = True
            elif c == 27:
                reverse = False
            elif 30 <= c <= 37 or 90 <= c <= 97:
                fg = ANSI[c - 30 if c < 90 else c - 82]
            elif 40 <= c <= 47 or 100 <= c <= 107:
                bg = ANSI[c - 40 if c < 100 else c - 92]
            elif c == 39:
                fg = None
            elif c == 49:
                bg = None
            elif c in (38, 48) and i + 2 < len(codes) and codes[i + 1] == 5:
                colour = _colour256(codes[i + 2])
                fg, bg = (colour, bg) if c == 38 else (fg, colour)
                i += 2
            elif c in (38, 48) and i + 4 < len(codes) and codes[i + 1] == 2:
                r, g, b = codes[i + 2:i + 5]
                colour = f"#{r:02x}{g:02x}{b:02x}"
                fg, bg = (colour, bg) if c == 38 else (fg, colour)
                i += 4
            i += 1
    out.append((text[at:], _style(fg, bg, bold, dim, reverse)))
    return out


def _style(fg, bg, bold, dim, reverse) -> tuple:
    fg, bg = fg or FOREGROUND, bg or BACKGROUND
    if reverse:
        fg, bg = bg, fg
    return fg, bg, bold, dim


def _colour256(n: int) -> str:
    if n < 16:
        return ANSI[n]
    if n >= 232:
        v = 8 + (n - 232) * 10
        return f"#{v:02x}{v:02x}{v:02x}"
    n -= 16
    steps = [0, 95, 135, 175, 215, 255]
    r, g, b = steps[n // 36], steps[n // 6 % 6], steps[n % 6]
    return f"#{r:02x}{g:02x}{b:02x}"


def draw(screen: str, columns: int, out: str, scale: float, folder: str):
    """The screen of a terminal (with its colours) as an image: written as a
    web page, which Chrome takes."""
    screen = OSC.sub("", screen)        # (tmux -e keeps the hyperlinks)
    lines = screen.rstrip("\n").split("\n")
    while lines and not SGR.sub("", lines[-1]).strip():      # (the empty end)
        lines.pop()
    body = []
    for line in lines:
        for piece, (fg, bg, bold, dim) in styled(line):
            style = f"color:{fg};background:{bg};"
            style += "font-weight:bold;" if bold else ""
            style += "opacity:.6;" if dim else ""
            body.append(f'<span style="{style}">{html.escape(piece)}</span>')
        body.append("\n")
    family = ", ".join(f"'{f}'" if f != "monospace" else f for f in FONTS)
    page = os.path.join(folder, "terminal.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><style>
html, body {{ margin: 0; background: {BACKGROUND}; }}
pre {{ margin: 0; padding: {MARGIN}px; color: {FOREGROUND};
      font: {FONT_SIZE}px/{LINE_HEIGHT} {family}; }}
</style><pre>{''.join(body).rstrip()}</pre>""")
    size = (math.ceil(columns * FONT_SIZE * CHAR_WIDTH) + 2 * MARGIN,
            math.ceil(len(lines) * FONT_SIZE * LINE_HEIGHT) + 2 * MARGIN)
    shoot("file://" + page, size, out, scale, folder)
    #  (the width of the letters is only approximate: the space left over is
    #  cut, and the same margin put all round)
    subprocess.run([magick(), out, "-trim", "+repage", "-bordercolor", BACKGROUND,
                    "-border", str(round(MARGIN * scale)), out], check=True)


# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Take the screenshots of the three programs (for the READMEs).")
    parser.add_argument("-o", "--output", default=os.path.join(ROOT, "docs", "img"),
                        help="the folder of the images (default: docs/img)")
    parser.add_argument("--only", default=",".join(KINDS),
                        help="which programs: cli,tui,gui")
    parser.add_argument("--looks", default=",".join(LOOKS),
                        help="the looks of the window: light,dark (default: both)")
    parser.add_argument("--word", default="rosa",
                        help="the word looked up (default: rosa)")
    parser.add_argument("--lang", default="la",
                        help="the language of the entry shown (default: la)")
    parser.add_argument("--scale", type=float, default=SCALE,
                        help="times the size on the screen (default: 2)")
    parser.add_argument("--child-gui", nargs=4, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.child_gui:
        gui_child(*args.child_gui)
        return
    kinds = [k for k in args.only.split(",") if k]
    looks = [k for k in args.looks.split(",") if k]
    for kind in kinds:
        if kind not in KINDS:
            raise SystemExit(f"unknown program: {kind}")
        if kind in ("cli", "tui"):
            if not shutil.which("tmux"):
                raise SystemExit("tmux is needed for cli and tui")
            chrome()
    for look in looks:
        if look not in LOOKS:
            raise SystemExit(f"unknown look: {look}")
    if "gui" in kinds and not (shutil.which("import") and (
            os.environ.get("DISPLAY") or shutil.which("Xvfb"))):
        raise SystemExit("the window needs ImageMagick (import) and an X display or Xvfb")
    if args.scale <= 0:
        raise SystemExit("the scale must be more than 0")
    os.makedirs(args.output, exist_ok=True)
    display = Display(args.scale) if "gui" in kinds else None
    try:
        for kind in kinds:
            if kind == "gui":
                for look in looks:
                    out = os.path.join(args.output, f"gui_{look}.png")
                    say(f"gui ({look}) -> {out}")
                    gui(look, args.word, args.lang, out, args.scale, display)
            else:
                out = os.path.join(args.output, f"{kind}.png")
                say(f"{kind} -> {out}")
                (cli if kind == "cli" else tui)(args.word, args.lang, out, args.scale)
    finally:
        if display:
            display.close()


if __name__ == "__main__":
    main()
