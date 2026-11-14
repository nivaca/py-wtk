# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
#
# Build with packaging/build-rpm.sh, which makes the source tarball.

Name:           py-wtk
Version:        1.12
Release:        1%{?dist}
Summary:        Look up words in the English Wiktionary

License:        GPL-3.0-or-later
URL:            https://github.com/nivaca/py-wtk
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
# For %check, which loads the window's module.
BuildRequires:  python3-tkinter

Requires:       python3 >= 3.13
# The window (py-wtk-gui) is Tk.
Requires:       python3-tkinter
Requires:       hicolor-icon-theme

%description
py-wtk looks up words in the English Wiktionary and shows their entries
(definitions, etymology, pronunciation, inflection tables, quotations ...)
for any language, with the sections and languages you choose.

It comes as three programs: a command line (py-wtk), a full-screen
terminal interface (py-wtk-tui) and a window (py-wtk-gui). Only the
Python standard library is used; it needs a connection to the Internet.

%prep
%autosetup -n %{name}-%{version}

%build
# Nothing to build: the program is Python.

%install
# The program: the three launchers and the pywtk package, with the icons
# (the window reads them), not the tools, docs or py-wtk-install.py (the
# package has its own menu entries). The launchers find pywtk next to
# their real path, so /usr/bin has links to them.
install -d %{buildroot}%{_datadir}/%{name}
for f in py-wtk py-wtk-tui py-wtk-gui; do
    install -pm 0755 "$f" %{buildroot}%{_datadir}/%{name}/
done
install -d %{buildroot}%{_datadir}/%{name}/pywtk
install -pm 0644 pywtk/*.py %{buildroot}%{_datadir}/%{name}/pywtk/
[ -f COMMIT ] && install -pm 0644 COMMIT %{buildroot}%{_datadir}/%{name}/
install -d %{buildroot}%{_datadir}/%{name}/icons/linux
install -pm 0644 icons/py-wtk.svg %{buildroot}%{_datadir}/%{name}/icons/
cp -pr icons/linux/hicolor %{buildroot}%{_datadir}/%{name}/icons/linux/
# Compiled now: users cannot write next to the modules, so Python would
# otherwise compile every module on every start.
%py_byte_compile %{python3} %{buildroot}%{_datadir}/%{name}/pywtk

install -d %{buildroot}%{_bindir}
for f in py-wtk py-wtk-tui py-wtk-gui; do
    ln -s ../share/%{name}/"$f" %{buildroot}%{_bindir}/"$f"
done

for f in packaging/*.desktop; do
    desktop-file-install --dir=%{buildroot}%{_datadir}/applications "$f"
done
install -d %{buildroot}%{_datadir}/icons
cp -pr icons/linux/hicolor %{buildroot}%{_datadir}/icons/

%check
for f in %{buildroot}%{_datadir}/applications/*.desktop; do
    desktop-file-validate "$f"
done
# The installed programs start, from their links, with no settings or
# cache of the builder's (and no network: nothing is looked up).
export HOME="$PWD/check-home" XDG_CONFIG_HOME= XDG_CACHE_HOME=
%{buildroot}%{_bindir}/py-wtk --version | grep -q '%{version}'
%{buildroot}%{_bindir}/py-wtk-tui --help | grep -q '%{version}'
%{buildroot}%{_bindir}/py-wtk-gui --help >/dev/null
PYTHONPATH=%{buildroot}%{_datadir}/%{name} %{python3} -c \
    'import pywtk.cli, pywtk.tui, pywtk.gui, pywtk.render, pywtk.settings'

%files
%license LICENSE
%doc README.md README.es.md docs/NOTES.md docs/NOTES.es.md
%doc docs/DESCRIPTION.md docs/DESCRIPCIÓN_es.md
%{_bindir}/py-wtk
%{_bindir}/py-wtk-tui
%{_bindir}/py-wtk-gui
%{_datadir}/%{name}/
%{_datadir}/applications/py-wtk.desktop
%{_datadir}/applications/py-wtk.cli.desktop
%{_datadir}/applications/py-wtk.tui.desktop
%{_datadir}/icons/hicolor/*/apps/py-wtk.*

%changelog
* Sat Nov 14 2026 Nicolas Vaughan <nivaca@fastmail.com> - 1.12-1
- Python 3.13 or later is needed

* Sat Nov 14 2026 Nicolas Vaughan <nivaca@fastmail.com> - 1.11-1
- No Flatpak any more; plainer documentation and comments

* Fri Nov 13 2026 Nicolas Vaughan <nivaca@fastmail.com> - 1.10-1
- Copying and pasting: an Edit menu in the window, y in the terminal interface

* Fri Nov 13 2026 Nicolas Vaughan <nivaca@fastmail.com> - 1.9-1
- The AppImage carries terminal descriptions in the old format, so py-wtk-tui
  starts in it

* Thu Nov 12 2026 Nicolas Vaughan <nivaca@fastmail.com> - 1.8-1
- A new icon

* Wed Nov 11 2026 Nicolas Vaughan <nivaca@fastmail.com> - 1.7-1
- The window follows the desktop's scaling (Xft.dpi) on hi-res displays

* Wed Nov 11 2026 Nicolas Vaughan <nivaca@fastmail.com> - 1.6-1
- First package: runs on the system's Python and Tk; the commands
  py-wtk, py-wtk-tui and py-wtk-gui, with three menu entries
