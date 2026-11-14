# Release notes

## 1.12

**Python 3.13 or later.** py-wtk now needs Python 3.13 (it was 3.11), as the other
programs of the author do. The AppImage carries its own Python 3.13 and every supported
Fedora has a newer one, so only those who run the zip with an older Python are affected.

## 1.11

**No Flatpak any more.** Releases carry again only the zip, the AppImage and the RPM: the
Flatpak of 1.10 is no longer made, and it was also taken off that release.

**Plainer documentation.** The READMEs, the descriptions, these notes and the comments of
the code read more plainly and idiomatically, in English and in Spanish; the program itself
is the same.

## 1.10

**Copying and pasting.** The window has an *Edit* menu with Cut, Copy and Paste
(`Ctrl+X`, `Ctrl+C`, `Ctrl+V`), for the search box, the languages and the find box, and
Copy also for the text selected in the entry; what can't be done at the moment is greyed
out. In the terminal interface, `y` (or `F7`) copies the whole entry as plain text, through
the system's clipboard program or, if there is none, through the terminal itself.

**A Flatpak.** Each release now has `py-wtk-v.VERSION-x86_64.flatpak` too, with the three
programs, their menu entries and the icon, which runs on any Linux with Flatpak:
`flatpak install --user py-wtk-v.*-x86_64.flatpak`, then `flatpak run io.github.nivaca.PyWtk`
(the window). Its runtime comes from Flathub.

**The contents pane follows the size of the text.** Its rows had a fixed height, so with a
bigger text (`Ctrl++`) or on a scaled hi-res display the items overlapped; now they are as
tall as their text. On a scaled display the pane is also as wide as it should be.

## 1.9

**The terminal interface starts in the AppImage.** The Python in the AppImage could not
read how most terminals describe themselves (those with 256 colours, as in Fedora and
Debian 12 and later), and `py-wtk-tui` stopped at once with “setupterm: could not find
terminal”. The AppImage now carries those descriptions in a form it can read.

## 1.8

**A new icon.** The bracketed `pW` of the program, now drawn with shapes instead of a font
(so it looks the same on every system), in white and cream on a teal tile, with an amber
stress mark before the `p`, as in a pronunciation. It can be read on light and dark panels,
and down to 16 pixels. If you added the program to the applications menu with
`py-wtk-install.py`, run it again to get the new icon there.

**A new signing key for the RPM.** The RPM attached to the releases is now signed with the
key `8187 0643 CA22 1AF9 0C30  554E BE68 32CD 3599 4948` (a copy is in
`packaging/RPM-GPG-KEY-py-wtk`, and in each release as `RPM-GPG-KEY-py-wtk`). If you
installed an earlier RPM from a release, import the new key once:
`sudo rpm --import RPM-GPG-KEY-py-wtk`. The package from Copr is not affected.

## 1.7

**The window follows the desktop's scaling on hi-res displays.** With the desktop scaled
(for example at 200% in Plasma), the window of the AppImage came out very small: its Tk
ignored the scaling that the desktop gives to X11 programs (`Xft.dpi`). Now the window
reads it, and the text and the size of the window grow with it.

**A package for Fedora.** py-wtk is now an RPM, which uses the Python and Tk of the system
and adds the three programs to the `PATH` and to the applications menu. It is on
[Copr](https://copr.fedorainfracloud.org/coprs/nivaca/py-wtk/), so `dnf upgrade` brings each
new version (`sudo dnf copr enable nivaca/py-wtk && sudo dnf install py-wtk`), and the
releases have it too, signed, with its public key.

## 1.6

**Uninstalling removes only what the installer added.** `py-wtk-install.py --uninstall`
removes from the applications menu the `.desktop` files and the icons that the installer
made, and nothing else: an entry of the same name that it did not write (one without the
program's icon) is left alone, and so are links. `--only-gui` follows the same rule when it
removes the entries of the terminal version and the command line.

**Bug fixed: stray characters in the command line.** When a long entry was opened in a
pager other than `less` (for example `PAGER=most`), its links showed up as stray
characters such as `^[]8;;`. Only `less` can show these links, so with any other pager the
entry is now shown without them, keeping its colours. The screenshot of the command line in
the README showed these characters too; it has been taken again.

## 1.5

**Links open the entry at the top.** A link to another entry now opens it at the top,
with all the languages of the filter (with `all`, every language of the page), in the
window and in the terminal interface. Before, it jumped to the language of the link
(`rosa#Latin` scrolled to Latin), and the language seemed to have changed. A link to
another part of the same entry still goes there.

## 1.4

**Bug fixed.** `py-wtk --set NAME=VALUE` and `py-wtk --unset NAME` failed with an error
instead of changing the setting. They work again, and a wrong or ambiguous name (for
example `--set links=false`, which matches both `cli.links` and `gui.links`) is now
reported clearly.

**The same messages in the three programs.** The size of the disk cache is shown in the
same way everywhere ("2 pages, 192.7 KB"; the terminal interface said "1 pages"), and so
is the message for a language that the page doesn't have. In the window, "Open in
browser" and "Clear disk cache" now say in the status line what they did. In the command
line, a network error while searching (`-s`) gives a clear message.

**Installer.** `py-wtk-install.py --only-gui` adds only the window (`py-wtk (GUI)`) to the
applications menu; if an earlier run added the terminal version and the command line, their
entries are removed.

**Inside.** The code that each of the three programs had on its own (the history of
Back and Forward, the links, the messages, the disk cache, the common options) is now in
one place, `pywtk/common.py`, and the drawing of lists and the command line are simpler.
The entries are shown exactly as before.

**For developers.** The scripts that make the bundles are now in `tools/` with the others:
`python3 tools/bundle-zip.py` and `python3 tools/bundle-appimage.py`. The new
`tools/icons.py` makes all the icons again from `icons/py-wtk.svg`.

## 1.3

**New icon.** The icon now has a white background, and the letters are better centred.
The icons of every size (Linux, macOS, Windows and the PNG) are made again from it. Run
`py-wtk-install.py` again to get the new icon in the applications menu.

The screenshots of the README are updated.

## 1.2

**Clickable links.** The links of an entry now work in all three programs. A link to
another entry opens it in the program, at the language of the link (`rosa#Latin` opens
"rosa" at Latin); the other links (Wikipedia, the appendices of Wiktionary, other
dictionaries…) open in the web browser. Links to pages that don't exist yet, footnotes and
edit links are not clickable.

- **Window (`py-wtk-gui`):** the links are in the link colour and get underlined
  under the mouse; one click opens them, and the status line says where they go.
  Dragging over a link selects the text without opening it. New setting `gui.links`
  (on by default).
- **Terminal interface (`py-wtk-tui`):** the links are blue (underlined without
  colours). A click opens them (with the mouse on), and the new key `L` lists the links
  on the screen, to open one with the keyboard.
- **Command line (`py-wtk`):** the links are hyperlinks (OSC 8), which most modern
  terminals and `less` make clickable. Only with colours, so `--json`, `--no-color` and
  the output to other programs don't change. New setting `cli.links` (on by default), to
  turn them off in the terminals that show them as stray characters.

The text of the entries is the same as before.

**Interactive command line.** `py-wtk -i` asks for one word after another (each line can
have options too, like `rosa -l la`; the options given with `-i` apply to all of them).
`Ctrl-D` or `Ctrl-C` ends it.

**Installer.** `py-wtk-install.py` also adds `py-wtk (CLI)` to the applications menu,
which opens `py-wtk -i` in a terminal. The entries are now only in the categories
Office and Dictionary, so they don't appear twice in some menus. Run it again to get
the new entry.

**Other changes.** `py-wtk-tui` started without a terminal (for example from a menu whose
terminal emulator is missing) says so, instead of failing with a curses error.

## 1.0

First version of the new py-wtk: the command line, the terminal interface and the window,
with the settings shared between them, the disk cache, the zip and the AppImage, and
`py-wtk-install.py` to add the programs to the applications menu.
