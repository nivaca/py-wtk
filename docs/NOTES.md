# Release notes

## 1.8

**A new icon.** The bracketed `pW` of the program, now drawn with shapes instead of a font
(so it looks the same on every system), in white and cream on a teal tile, with an amber
stress mark before the `p`, as in a pronunciation. It can be read on light and dark panels,
and down to 16 pixels. If you added the program to the applications menu with
`py-wtk-install.py`, run it again to get the new icon there.

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
(`rosa#Latin` scrolled to Latin), and it seemed that the language had changed. A link
to another part of the same entry still goes there.

## 1.4

**Bug fixed.** `py-wtk --set NAME=VALUE` and `py-wtk --unset NAME` failed with an error
instead of changing the setting. They work again, and a wrong or ambiguous name (for
example `--set links=false`, that is `cli.links` and `gui.links`) is now reported clearly.

**The same messages in the three programs.** The size of the disk cache is shown in the
same way everywhere ("2 pages, 192.7 KB"; the terminal interface said "1 pages"), and so
is the message for a language that the page doesn't have. In the window, "Open in
browser" and "Clear disk cache" now say in the status line what they did. In the command
line, a network error while searching (`-s`) gives a clear message.

**Installer.** `py-wtk-install.py --only-gui` adds only the window (`py-wtk (GUI)`) to the
applications menu; if an earlier run added the terminal version and the command line, their
entries are removed.

**Inside.** The code that the three programs had each one for itself (the history of
Back and Forward, the links, the messages, the disk cache, the common options) is now in
one place, `pywtk/common.py`, and the drawing of lists and the command line are simpler.
The entries are shown exactly as before.

**For developers.** The scripts that make the bundles are now in `tools/` with the others:
`python3 tools/bundle-zip.py` and `python3 tools/bundle-appimage.py`. The new
`tools/icons.py` makes all the icons again from `icons/py-wtk.svg`.

## 1.3

**New icon.** The icon has now a white background, and the letters are better centred.
The icons of every size (Linux, macOS, Windows and the PNG) are made again from it. Run
`py-wtk-install.py` again to get the new icon in the applications menu.

The screenshots of the README are updated.

## 1.2

**Clickable links.** The links of an entry now work in the three programs. A link to
another entry opens it in the program, at the language of the link (`rosa#Latin` opens
"rosa" at Latin); the other links (Wikipedia, the appendices of Wiktionary, other
dictionaries…) open in the web browser. Links to pages that don't exist yet, footnotes and
edit links are not clickable.

- **Window (`py-wtk-gui`):** the links are in the colour of links and get underlined
  under the mouse; one click opens them, and the status line says where they go.
  Dragging over a link selects the text without opening it. New setting `gui.links`
  (on by default).
- **Terminal interface (`py-wtk-tui`):** the links are blue (underlined without
  colours). A click opens them (with the mouse on), and the new key `L` lists the links
  on the screen, for open one with the keyboard.
- **Command line (`py-wtk`):** the links are hyperlinks (OSC 8), that most modern
  terminals and `less` make clickable. Only with colours, so `--json`, `--no-color` and
  the output to other programs don't change. New setting `cli.links` (on by default), for
  turn them off in the terminals that show them as stray characters.

The text of the entries is the same as before.

**Interactive command line.** `py-wtk -i` asks for one word after another (each line can
have options too, like `rosa -l la`; the options given with `-i` apply to all of them).
`Ctrl-D` or `Ctrl-C` ends it.

**Installer.** `py-wtk-install.py` adds also `py-wtk (CLI)` to the applications menu,
which opens `py-wtk -i` in a terminal. The entries are now only in the categories
Office and Dictionary, so they don't appear twice in some menus. Run it again for have
the new entry.

**Other changes.** `py-wtk-tui` started without a terminal (for example from a menu whose
terminal emulator is missing) says so, instead of failing with an error of curses.

## 1.0

First version of the new py-wtk: the command line, the terminal interface and the window,
with the settings shared between them, the disk cache, the zip and the AppImage, and
`py-wtk-install.py` for add the programs to the applications menu.
