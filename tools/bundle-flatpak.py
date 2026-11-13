#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Makes a Flatpak of the program: python3 tools/bundle-flatpak.py

The Flatpak is dist/py-wtk-v.VERSION-x86_64.flatpak (the version of
pywtk/__init__.py; --output gives another folder), a single-file bundle of
the app io.github.nivaca.PyWtk, which people install with

    flatpak install --user py-wtk-v.VERSION-x86_64.flatpak

(its runtime, org.freedesktop.Platform, comes from Flathub).  It is built
by flatpak-builder from packaging/flatpak/io.github.nivaca.PyWtk.yml, with
the program as bundle-zip.py puts it in the zip, and COMMIT, copied first
into build/flatpak/src.  Everything else it makes stays in build/flatpak/
(the build, its cache and the repository the bundle is taken from).

Before building, it checks that the first release of the metainfo file
(packaging/flatpak/io.github.nivaca.PyWtk.metainfo.xml) is this version, and
validates that file and the menu entries.  It needs flatpak-builder (sudo
dnf install flatpak-builder), and installs the runtime and the SDK for the
user from Flathub if they are missing.  --install also installs the bundle
for the user, to try it.
"""

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # (above tools/)
sys.path.insert(0, HERE)

from pywtk.version import COMMIT_FILE, NAME, VERSION  # noqa: E402

APP_ID = "io.github.nivaca.PyWtk"
FLATPAK = os.path.join(HERE, "packaging", "flatpak")
MANIFEST = os.path.join(FLATPAK, APP_ID + ".yml")
METAINFO = os.path.join(FLATPAK, APP_ID + ".metainfo.xml")
WORK = os.path.join(HERE, "build", "flatpak")
DIST = os.path.join(HERE, "dist")
FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo"


def bundle_zip():
    """The module bundle-zip.py, whose list of files is used."""
    spec = importlib.util.spec_from_file_location(
        "bundle_zip", os.path.join(HERE, "tools", "bundle-zip.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def name() -> str:
    """The name of the bundle: py-wtk-v.1.10-x86_64.flatpak."""
    return f"{NAME}-v.{VERSION}-x86_64.flatpak"


def run(*command):
    print("+", " ".join(command), flush=True)
    if subprocess.run(command, cwd=HERE).returncode != 0:
        sys.exit(f"bundle-flatpak.py: failed: {' '.join(command)}")


def check():
    """Stops if a tool is missing or the metainfo is not at this version."""
    for tool in ("flatpak", "flatpak-builder"):
        if not shutil.which(tool):
            sys.exit(f"bundle-flatpak.py: {tool} is not installed "
                     f"(sudo dnf install {tool})")
    releases = ET.parse(METAINFO).getroot().find("releases")
    first = releases[0].get("version") if releases is not None and len(releases) else None
    if first != VERSION:
        sys.exit(f"bundle-flatpak.py: the first release of {os.path.relpath(METAINFO, HERE)} "
                 f"is {first}, not {VERSION}: add a <release> for {VERSION}")
    if shutil.which("appstreamcli"):
        run("appstreamcli", "validate", "--no-net", "--pedantic", METAINFO)
    if shutil.which("desktop-file-validate"):
        for f in ("py-wtk.desktop", "py-wtk.tui.desktop", "py-wtk.cli.desktop"):
            run("desktop-file-validate", os.path.join("packaging", f))


def stage() -> str:
    """The program, as in the zip, and COMMIT, in build/flatpak/src."""
    bz = bundle_zip()
    src = os.path.join(WORK, "src")
    shutil.rmtree(src, ignore_errors=True)
    for f in bz.files():
        os.makedirs(os.path.join(src, os.path.dirname(f)), exist_ok=True)
        shutil.copy2(os.path.join(HERE, f), os.path.join(src, f))
    commit = bz.built_from()
    if not commit:
        sys.exit("bundle-flatpak.py: the commit is not known (not a git clone?)")
    with open(os.path.join(src, COMMIT_FILE), "w", encoding="ascii") as f:
        f.write(commit + "\n")
    return src


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tools/bundle-flatpak.py",
        description=f"Make dist/{name()}, the Flatpak of {NAME}.")
    parser.add_argument("-o", "--output", metavar="FOLDER", default=DIST,
                        help="where the bundle goes (default: dist/)")
    parser.add_argument("--install", action="store_true",
                        help="also install the bundle for this user, to try it")
    args = parser.parse_args(argv)
    check()
    stage()
    repo = os.path.join(WORK, "repo")
    run("flatpak-builder", "--user", "--install-deps-from=flathub", "--force-clean",
        "--state-dir", os.path.join(WORK, "state"), "--repo", repo,
        os.path.join(WORK, "app"), MANIFEST)
    os.makedirs(args.output, exist_ok=True)
    bundle = os.path.join(os.path.abspath(args.output), name())
    run("flatpak", "build-bundle", f"--runtime-repo={FLATHUB}", repo, bundle, APP_ID)
    print(f"Wrote {bundle} ({os.path.getsize(bundle) / 1e6:.1f} MB).")
    if args.install:
        run("flatpak", "install", "--user", "--reinstall", "--noninteractive", bundle)


if __name__ == "__main__":
    main()
