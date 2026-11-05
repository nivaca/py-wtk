#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Makes all the icons afresh from icons/py-wtk.svg:

    python3 tools/icons.py [--svg FILE] [-o FOLDER] [--dry-run]

In FOLDER (icons/ by default) it writes:

* png/py-wtk-N.png, for each N in PNG_SIZES;
* linux/hicolor/NxN/apps/py-wtk.png, for each N in HICOLOR_SIZES, and
  linux/hicolor/scalable/apps/py-wtk.svg (a copy of the SVG);
* mac/py-wtk.iconset/icon_NxN[@2x].png and mac/py-wtk.icns;
* windows/py-wtk.ico.

Each size is drawn by Inkscape from the SVG (never scaled down from a
bigger PNG), all of them in a single run of Inkscape.  The .icns and the
.ico are put together with Pillow from those same PNGs.

Inkscape may be a Flatpak (org.inkscape.Inkscape), and then it is run with
"flatpak run" (a wrapper called inkscape on the PATH may not pass on the
arguments), with absolute paths, and writing only inside FOLDER: a Flatpak
does not see the host's /tmp.  So the PNGs are first drawn in a hidden
folder inside FOLDER, and only moved to their places once all are there.
If there is no Flatpak, the inkscape on the PATH is used.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

NAME = "py-wtk"
FLATPAK_ID = "org.inkscape.Inkscape"
PNG_SIZES = [16, 20, 22, 24, 32, 40, 48, 64, 96, 128, 256, 512, 1024]
HICOLOR_SIZES = [16, 22, 24, 32, 48, 64, 96, 128, 256, 512]
ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
ICONSET_SIZES = [16, 32, 128, 256, 512]   # each also @2x

ROOT = Path(__file__).resolve().parent.parent


def find_inkscape():
    """The command to run Inkscape, and whether it is a Flatpak."""
    if shutil.which("flatpak"):
        found = subprocess.run(["flatpak", "info", FLATPAK_ID],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        if found.returncode == 0:
            return ["flatpak", "run", FLATPAK_ID], True
    native = shutil.which("inkscape")
    if native:
        return [native], False
    sys.exit("Inkscape was not found (neither the Flatpak %s nor inkscape "
             "on the PATH)." % FLATPAK_ID)


def render(inkscape, svg, folder, sizes):
    """Draws svg as folder/N.png for each N in sizes, in one run."""
    actions = []
    for n in sizes:
        actions += ["export-width:%d" % n, "export-height:%d" % n,
                    "export-type:png",
                    "export-filename:%s" % (folder / ("%d.png" % n)),
                    "export-do"]
    command = inkscape + [str(svg), "--actions=" + ";".join(actions)]
    result = subprocess.run(command, capture_output=True, text=True)
    missing = [n for n in sizes if not (folder / ("%d.png" % n)).is_file()]
    if result.returncode != 0 or missing:
        sys.stderr.write(result.stderr)
        sys.exit("Inkscape did not draw the sizes %s." %
                 ", ".join(map(str, missing or sizes)))


def check_sizes(folder, sizes):
    from PIL import Image
    for n in sizes:
        with Image.open(folder / ("%d.png" % n)) as im:
            if im.size != (n, n):
                sys.exit("%d.png came out %dx%d: is the SVG not square?"
                         % (n, *im.size))


def put(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def main():
    parser = argparse.ArgumentParser(
        description="Makes all the icons afresh from the SVG.")
    parser.add_argument("--svg", type=Path, default=ROOT / "icons" /
                        (NAME + ".svg"), help="the SVG (icons/%s.svg)" % NAME)
    parser.add_argument("-o", "--output", type=Path, default=ROOT / "icons",
                        help="the folder for the icons (icons/)")
    parser.add_argument("--dry-run", action="store_true",
                        help="only show how Inkscape would be run")
    args = parser.parse_args()

    svg = args.svg.resolve()
    out = args.output.resolve()
    if not svg.is_file():
        sys.exit("There is no %s." % svg)
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow is needed for the .icns and the .ico "
                 "(dnf install python3-pillow, or pip install pillow).")

    inkscape, flatpak = find_inkscape()
    print("Inkscape: %s%s" % (" ".join(inkscape),
                              " (Flatpak)" if flatpak else ""))
    if flatpak and (out == Path("/tmp") or Path("/tmp") in out.parents):
        sys.exit("The Flatpak of Inkscape cannot write in /tmp; "
                 "choose another folder with -o.")
    if args.dry_run:
        print("Would draw %s at %s px into %s." %
              (svg, ", ".join(map(str, PNG_SIZES)), out))
        return

    out.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".render-", dir=out))
    try:
        render(inkscape, svg, stage, PNG_SIZES)
        check_sizes(stage, PNG_SIZES)
        png = lambda n: stage / ("%d.png" % n)

        for n in PNG_SIZES:
            put(png(n), out / "png" / ("%s-%d.png" % (NAME, n)))

        hicolor = out / "linux" / "hicolor"
        for n in HICOLOR_SIZES:
            put(png(n), hicolor / ("%dx%d" % (n, n)) / "apps" /
                (NAME + ".png"))
        if svg != (hicolor / "scalable" / "apps" / (NAME + ".svg")).resolve():
            put(svg, hicolor / "scalable" / "apps" / (NAME + ".svg"))

        iconset = out / "mac" / (NAME + ".iconset")
        for n in ICONSET_SIZES:
            put(png(n), iconset / ("icon_%dx%d.png" % (n, n)))
            put(png(2 * n), iconset / ("icon_%dx%d@2x.png" % (n, n)))
        icns_sizes = sorted({n for n in ICONSET_SIZES} |
                            {2 * n for n in ICONSET_SIZES})
        images = [Image.open(png(n)).convert("RGBA") for n in icns_sizes]
        images[-1].save(out / "mac" / (NAME + ".icns"),
                        append_images=images[:-1])

        (out / "windows").mkdir(parents=True, exist_ok=True)
        images = [Image.open(png(n)).convert("RGBA") for n in ICO_SIZES]
        images[-1].save(out / "windows" / (NAME + ".ico"),
                        sizes=[(n, n) for n in ICO_SIZES],
                        append_images=images[:-1])
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    print("Made the icons in %s:" % out)
    for part in ["png", "linux/hicolor", "mac", "windows"]:
        print("  %s/" % part)


if __name__ == "__main__":
    main()
