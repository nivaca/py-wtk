#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
"""Publishes a release of py-wtk on GitHub (with gh) and on Codeberg (with
tea): the tag vVERSION (the version of pywtk/__init__.py), with the zip and
the AppImage attached, and (--rpm) the RPM, also published on Copr.

    python3 tools/release.py [--redo] [--notes TEXT | --notes-file FILE]
                             [--no-build] [--no-appimage] [--rpm [--no-copr]]
                             [--only github|codeberg] [--dry-run] [--yes]

In order, each step only if it is needed:

1. checks that the repository is on main, with nothing left to commit,
   and that gh and tea are installed;
2. makes the zip and the AppImage in dist/ (tools/bundle-zip.py
   and tools/bundle-appimage.py), unless --no-build (then those in dist/ are used);
   with --rpm, also the signed RPM and its public key in build/rpm/
   (packaging/build-rpm.sh --sign; gpg asks for the passphrase);
3. tags HEAD as vVERSION.  If the tag is there already on another commit,
   it stops, unless --redo moves it;
4. pushes main and the tag to the remote (origin, whose push addresses are
   GitHub and Codeberg; --redo pushes the tag with --force).  Whether each
   forge has the tag already is asked of each push address, as the remote
   may have no address to fetch from;
5. on each forge, makes the release of the tag, or keeps the one there is,
   and attaches the files to it, replacing those of the same name;
6. with --rpm, sends the source RPM to Copr (copr-cli build, project
   nivaca/py-wtk), unless --no-copr.  Copr builds it for each Fedora of
   the project and signs it with its own key; each build needs a higher
   version-release than the last, so the spec must have been bumped
   (rpmdev-bumpspec, see packaging/COPR.org).

Before doing anything, it shows the commands it will run and asks; --yes
does not ask, --dry-run only shows them.  The notes of a new release are
--notes, --notes-file, or else made by GitHub from the commits (on
Codeberg, none); a release that is there keeps its notes.

The repositories are found from the push addresses of the remote; tea uses
the login named codeberg unless --tea-login says another.
"""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pywtk.version import NAME, VERSION  # noqa: E402

TAG = f"v{VERSION}"
ZIP = os.path.join("dist", f"{NAME}-v.{VERSION}.zip")
APPIMAGE = os.path.join("dist", f"{NAME}-v.{VERSION}-x86_64.AppImage")
BRANCH = "main"
#  Where tea runs: outside the repository, as tea reads the remote's fetch
#  address there (which origin may not have) even when --repo is given
TEA_CWD = tempfile.gettempdir()
FORGES = {"github": "github.com", "codeberg": "codeberg.org"}
SPEC = os.path.join("packaging", f"{NAME}.spec")
RPM_KEY = os.path.join("build", "rpm", f"RPM-GPG-KEY-{NAME}")
COPR_PROJECT = NAME             # (of the copr-cli user, nivaca)


def signing_key() -> str:
    """The project's signing key, as packaging/build-rpm.sh pins it."""
    with open(os.path.join(ROOT, "packaging", "build-rpm.sh"), encoding="utf-8") as f:
        m = re.search(r'SIGNING_KEY="\$\{SIGNING_KEY:-([0-9A-F]{40})\}"', f.read())
    return m.group(1) if m else ""


def rpm_nvr() -> str:
    """NAME-VERSION-RELEASE of the RPM that packaging/build-rpm.sh makes, as
    its spec says (py-wtk-1.6-1.fc45); stops if the spec is not at VERSION."""
    try:
        nvr = subprocess.run(
            ["rpmspec", "-q", "--srpm", "--qf", "%{name}-%{version}-%{release}", SPEC],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        sys.exit("release.py: rpmspec cannot read the spec (sudo dnf install rpm-build)")
    if not nvr.startswith(f"{NAME}-{VERSION}-"):
        sys.exit(f"release.py: {SPEC} is not at version {VERSION} "
                 f"(rpmdev-bumpspec -n {VERSION} -c '...' {SPEC})")
    return nvr


def rpm() -> str:
    return os.path.join("build", "rpm", "RPMS", "noarch", rpm_nvr() + ".noarch.rpm")


def srpm() -> str:
    return os.path.join("build", "rpm", "SRPMS", rpm_nvr() + ".src.rpm")


class Release:
    """The steps, run (or only shown) in order."""

    def __init__(self, args):
        self.args = args
        self.planned = []           # (description, command, folder)

    # ---- running -------------------------------------------------------- #
    def read(self, *command, check=True, cwd=ROOT) -> str:
        """The output of COMMAND (which only reads, so it runs even with
        --dry-run)."""
        out = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        if check and out.returncode != 0:
            sys.exit(f"release.py: {shlex.join(command)}: "
                     f"{(out.stderr or out.stdout).strip()}")
        return out.stdout.strip() if out.returncode == 0 else ""

    def plan(self, description: str, *command, cwd=ROOT):
        self.planned.append((description, list(command), cwd))

    def run_plan(self):
        if not self.planned:
            print("Nothing to do.")
            return
        print(f"Releasing {TAG}:")
        for description, command, cwd in self.planned:
            where = "" if cwd == ROOT else f"(in {cwd}) "
            print(f"\n  # {description}\n  {where}{shlex.join(command)}")
        print()
        if self.args.dry_run:
            return
        if not self.args.yes:
            answer = input("Run these commands? [y/N] ").strip().lower()
            if answer not in ("y", "yes", "s", "sí", "si"):
                sys.exit("Nothing done.")
        for description, command, cwd in self.planned:
            print(f"\n==> {description}", flush=True)
            if subprocess.run(command, cwd=cwd).returncode != 0:
                sys.exit(f"release.py: failed: {shlex.join(command)}\n"
                         "The steps before it were done; after fixing the cause, "
                         "run the script again (with --redo if the tag was "
                         "already moved).")
        print(f"\nReleased {TAG}.")

    # ---- checks --------------------------------------------------------- #
    def check(self):
        tools = ("git",) + tuple(t for t, f in (("gh", "github"), ("tea", "codeberg"))
                                 if f in self.forges)
        if self.args.rpm:
            tools += ("rpmbuild",) + (() if self.args.no_copr else ("copr-cli",))
        for tool in tools:
            if not shutil.which(tool):
                sys.exit(f"release.py: {tool} is not installed")
        if self.args.rpm:
            key = signing_key()
            if not key or subprocess.run(["gpg", "--batch", "--list-secret-keys", key],
                                         capture_output=True).returncode != 0:
                sys.exit(f"release.py: the signing key {key or '(none)'} is not in this "
                         "machine's gpg keyring; import it first (see packaging/COPR.org)")
        self.read("git", "rev-parse", "--git-dir")      # (stops if not a repository)
        branch = self.read("git", "rev-parse", "--abbrev-ref", "HEAD")
        if branch != BRANCH:
            sys.exit(f"release.py: on branch {branch}, not {BRANCH}")
        if self.read("git", "status", "--porcelain"):
            message = "there are changes not committed (see git status)"
            if not self.args.dry_run:
                sys.exit(f"release.py: {message}")
            print(f"release.py: (dry run) {message}", file=sys.stderr)

    def push_urls(self) -> list[str]:
        return self.read("git", "remote", "get-url", "--push", "--all",
                         self.args.remote).split("\n")

    def repos(self) -> dict:
        """{forge: (owner/name, push address)}, from the remote."""
        found = {}
        for url in self.push_urls():
            m = re.search(r"(github\.com|codeberg\.org)[:/]+([^/]+/[^/]+?)(?:\.git)?/?$", url)
            if m:
                found["github" if "github" in m[1] else "codeberg"] = (m[2], url)
        for forge in self.forges:
            if forge not in found:
                sys.exit(f"release.py: the remote {self.args.remote} does not push "
                         f"to {FORGES[forge]} (git remote -v)")
        return found

    # ---- steps ---------------------------------------------------------- #
    def build(self):
        if self.args.no_build:
            for f in self.files:
                if not os.path.isfile(os.path.join(ROOT, f)):
                    sys.exit(f"release.py: there is no {f} (leave out --no-build "
                             "to make it)")
            return
        self.plan("Make the zip", sys.executable, "tools/bundle-zip.py")
        if APPIMAGE in self.files:
            self.plan("Make the AppImage", sys.executable, "tools/bundle-appimage.py")
        if RPM_KEY in self.files:
            self.plan("Make the signed RPM", "packaging/build-rpm.sh", "--sign")

    def tag(self, repos: dict):
        head = self.read("git", "rev-parse", "HEAD")
        tagged = self.read("git", "rev-parse", "--verify", "--quiet",
                           f"refs/tags/{TAG}^{{commit}}", check=False)
        if tagged == head:
            pass
        elif tagged and not self.args.redo:
            sys.exit(f"release.py: {TAG} is already the tag of {tagged[:7]}, not of "
                     f"HEAD ({head[:7]}); --redo moves it (and replaces the files "
                     "of the releases)")
        else:
            self.plan("Move the tag to HEAD" if tagged else "Tag HEAD",
                      "git", "tag", "--force", "--annotate", TAG, "--message", TAG)
        self.plan(f"Push {BRANCH}", "git", "push", self.args.remote, BRANCH)
        #  With --redo the tag is always pushed with --force (to all the
        #  push addresses of the remote)
        if self.args.redo:
            self.plan("Push the tag (replacing it on the forges)", "git", "push",
                      "--force", self.args.remote, f"refs/tags/{TAG}")
            return
        #  Asked of each forge (the remote may have no address to fetch from)
        on_forges = []
        for forge in self.forges:
            url = repos[forge][1]
            out = self.read("git", "ls-remote", "--tags", url, f"refs/tags/{TAG}^{{}}",
                            check=False)
            there = out.split()[0] if out else ""
            if there and there != head:
                sys.exit(f"release.py: on {FORGES[forge]}, {TAG} is the tag of "
                         f"{there[:7]}; --redo moves it")
            on_forges.append(there == head)
        if not all(on_forges):
            self.plan("Push the tag", "git", "push", self.args.remote, f"refs/tags/{TAG}")

    def notes(self, github: bool) -> list[str]:
        if self.args.notes_file:
            return ["--notes-file" if github else "--note-file", self.args.notes_file]
        if self.args.notes:
            return ["--notes" if github else "--note", self.args.notes]
        return ["--generate-notes"] if github else []

    def github(self, repo: str):
        exists = subprocess.run(["gh", "release", "view", TAG, "--repo", repo],
                                cwd=ROOT, capture_output=True).returncode == 0
        if exists:
            self.plan("GitHub: attach the files to the release (replacing those there)",
                      "gh", "release", "upload", TAG, *self.files, "--clobber",
                      "--repo", repo)
        else:
            self.plan("GitHub: make the release", "gh", "release", "create", TAG,
                      *self.files, "--title", TAG, "--verify-tag", *self.notes(True),
                      "--repo", repo)

    def codeberg(self, repo: str):
        where = ["--repo", repo, "--login", self.args.tea_login]
        files = [os.path.join(ROOT, f) for f in self.files]   # (tea runs elsewhere)
        releases = self.tea_json("releases", "ls", "--limit", "50", *where)
        exists = any(TAG in (r.get("tagname"), r.get("tag")) for r in releases)
        if exists:
            names = {a.get("name") for a in self.tea_json("releases", "assets", "ls",
                                                          TAG, *where)}
            old = [os.path.basename(f) for f in self.files if os.path.basename(f) in names]
            if old:
                self.plan("Codeberg: remove the files of the same name (tea cannot "
                          "replace them)", "tea", "releases", "assets", "delete", TAG,
                          *old, "--confirm", *where, cwd=TEA_CWD)
            self.plan("Codeberg: attach the files to the release", "tea", "releases",
                      "assets", "create", TAG, *files, *where, cwd=TEA_CWD)
        else:
            assets = [a for f in files for a in ("--asset", f)]
            self.plan("Codeberg: make the release", "tea", "releases", "create",
                      "--tag", TAG, "--title", TAG, *self.notes(False), *assets, *where,
                      cwd=TEA_CWD)

    def copr(self):
        if self.args.no_build and not os.path.isfile(os.path.join(ROOT, srpm())):
            sys.exit(f"release.py: there is no {srpm()} (leave out --no-build to make it)")
        self.plan(f"Copr: build the RPM (project {COPR_PROJECT})", "copr-cli", "build",
                  COPR_PROJECT, srpm())

    def tea_json(self, *command) -> list[dict]:
        """The rows tea gives in JSON, with its keys made plain ("tag-_name" is
        tagname)."""
        result = subprocess.run(["tea", *command, "--output", "json"], cwd=TEA_CWD,
                                capture_output=True, text=True)
        if result.returncode != 0:
            error = (result.stderr or result.stdout).strip()
            if "couldn't be found" in error or "404" in error:
                repo = command[command.index("--repo") + 1]
                sys.exit(f"release.py: Codeberg has no repository {repo}, or the tea "
                         f"login {self.args.tea_login!r} cannot see it (make it on "
                         "codeberg.org first, or use --only github)")
            sys.exit(f"release.py: tea {shlex.join(command)}: {error}")
        out = result.stdout.strip()
        try:
            rows = json.loads(out or "[]")
        except ValueError:
            sys.exit(f"release.py: tea {' '.join(command)}: not JSON: {out[:200]}")
        return [{re.sub("[^a-z]", "", k.lower()): v for k, v in r.items()} for r in rows]

    # ---- all ------------------------------------------------------------ #
    def __call__(self):
        args = self.args
        self.forges = [args.only] if args.only else ["github", "codeberg"]
        self.files = [ZIP] + ([] if args.no_appimage else [APPIMAGE])
        if args.rpm:
            self.files += [rpm(), RPM_KEY]
        self.check()
        repos = self.repos()
        self.build()
        self.tag(repos)
        for forge in self.forges:
            getattr(self, forge)(repos[forge][0])
        if args.rpm and not args.no_copr:
            self.copr()
        self.run_plan()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="tools/release.py",
        description=f"Publish {TAG} on GitHub and Codeberg, with the zip, the AppImage "
                    "and (--rpm) the RPM, which goes to Copr too.")
    parser.add_argument("--redo", action="store_true",
                        help=f"move {TAG} to HEAD if it is on another commit (here and "
                             "on the forges), and replace the files of the releases")
    notes = parser.add_mutually_exclusive_group()
    notes.add_argument("--notes", metavar="TEXT", help="the notes of a new release")
    notes.add_argument("--notes-file", metavar="FILE",
                       help="the notes of a new release, from FILE")
    parser.add_argument("--no-build", action="store_true",
                        help="use the zip and AppImage in dist/, without making them again")
    parser.add_argument("--no-appimage", action="store_true", help="only the zip")
    parser.add_argument("--rpm", action="store_true",
                        help="also the signed RPM and its public key "
                             "(packaging/build-rpm.sh --sign), and a Copr build of it")
    parser.add_argument("--no-copr", action="store_true",
                        help="with --rpm, do not send it to Copr")
    parser.add_argument("--only", choices=("github", "codeberg"),
                        help="publish on one forge only")
    parser.add_argument("--remote", default="origin",
                        help="the remote to push to (default: origin)")
    parser.add_argument("--tea-login", default="codeberg",
                        help="the login of tea for Codeberg (default: codeberg)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="only show the commands")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="do not ask before running them")
    args = parser.parse_args(argv)
    if args.notes_file:
        args.notes_file = os.path.abspath(args.notes_file)
    Release(args)()


if __name__ == "__main__":
    main()
