#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Nicolas Vaughan <nivaca@fastmail.com>
# This file is part of py-wtk. See the LICENSE file for details.
#
# Builds py-wtk's RPM (and source RPM) from this checkout, into
# build/rpm/ — not ~/rpmbuild, so nothing outside the repo is touched.
#
#   packaging/build-rpm.sh [--sign[=KEY]]
#
# --sign signs both RPMs with OpenPGP, so dnf can check where they came
# from, with the project's signing key, SIGNING_KEY below (the same on all
# the author's machines; a copy of its public key is in
# packaging/RPM-GPG-KEY-py-wtk). --sign=KEY, or $SIGNING_KEY, names
# another key for an exceptional build. The public key is exported next to them as
# build/rpm/RPM-GPG-KEY-py-wtk, for people to import before installing
# (sudo rpm --import RPM-GPG-KEY-py-wtk). gpg asks for the key's
# passphrase as usual. Needs rpm-sign; RPMSIGN names another rpmsign.
#
# The source tarball is made from the files git knows about, committed or
# not (ignored files, such as dist/, are left out), so a change can be
# packaged before it is committed. For a release, build from a clean tree.
#
# The commit of HEAD goes into the tarball as COMMIT, for "About" and
# --version, as tools/bundle-zip.py does for the zip.
#
# Needs rpm-build, plus what the spec builds with: python3-devel,
# desktop-file-utils and python3-tkinter.
set -euo pipefail

DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
# The project's signing key (Nicolas Vaughan, ed25519, 2026)
SIGNING_KEY="${SIGNING_KEY:-236EF043AB7A4434A05CA4ECB5549099FC0D6464}"
SPEC="$DIR/packaging/py-wtk.spec"
TOP="$DIR/build/rpm"
RPMSIGN="${RPMSIGN:-rpmsign}"

die() { echo "build-rpm: $*" >&2; exit 1; }

SIGN=0
KEY=""
for arg in "$@"; do
    case "$arg" in
        --sign) SIGN=1; KEY="$SIGNING_KEY" ;;
        --sign=*) SIGN=1; KEY="${arg#--sign=}"
                  [ -n "$KEY" ] || die "--sign= needs a key" ;;
        -h|--help)  # the comment block after the licence, as help
            awk 'NR > 5 && !/^#/ { exit } NR > 5 { sub(/^# ?/, ""); print }' "$0"
            exit 0 ;;
        *) die "unknown option $arg (try --help)" ;;
    esac
done

for tool in rpmbuild rpmspec git; do
    command -v "$tool" >/dev/null 2>&1 ||
        die "$tool not found (dnf install rpm-build git)"
done

# Signing is checked before building, so a missing tool or key costs
# seconds rather than a whole build.
if [ "$SIGN" = 1 ]; then
    command -v "$RPMSIGN" >/dev/null 2>&1 ||
        die "$RPMSIGN not found (sudo dnf install rpm-sign)"
    command -v gpg >/dev/null 2>&1 || die "gpg not found (sudo dnf install gnupg2)"
    # The fingerprint, whichever way the key was named: unambiguous for
    # rpmsign, and what the exported key file is made from. Revoked,
    # expired, invalid and disabled keys are passed over.
    # (gpg exits non-zero when nothing matches; "|| true" lets the check
    # below say so, where set -e and pipefail would end the script mute.)
    FPR="$(gpg --batch --with-colons --list-secret-keys ${KEY:+"$KEY"} 2>/dev/null |
        awk -F: '$1 == "sec" { want = ($2 !~ /[reid]/) }
                 want && $1 == "fpr" { print $10; exit }' ||
        true)"
    [ -n "$FPR" ] || die "no secret key matching $KEY in gpg: import the signing key on this machine
(gpg --import the exported secret key; see packaging/COPR.org)"
    echo "Signing with $(gpg --batch --with-colons --list-keys "$FPR" |
        awk -F: '$1 == "uid" { print $10; exit }') ($FPR)"
fi

VERSION="$(rpmspec -q --srpm --qf '%{version}\n' "$SPEC")"
NAME="py-wtk-$VERSION"

if [ -n "$(git -C "$DIR" status --porcelain)" ]; then
    echo "note: the tree has uncommitted changes; they go into this build."
fi

rm -rf "$TOP"
mkdir -p "$TOP"/{SOURCES,SPECS,BUILD,RPMS,SRPMS}
# Tracked and new files, as they are on disk, under py-wtk-VERSION/,
# and COMMIT.
LIST="$TOP/files"
(cd "$DIR" && git ls-files -z --cached --others --exclude-standard |
    while IFS= read -r -d '' f; do [ -e "$f" ] && printf '%s\0' "$f"; done) \
    > "$LIST"
# A new file is packed too, so an exported secret key left in the folder
# would go into the source RPM for anyone to download.
secret="$(cd "$DIR" && xargs -0 grep -l -E -- \
    '-----BEGIN ([A-Z]+ )*PRIVATE KEY( BLOCK)?-----' < "$LIST" || true)"
[ -z "$secret" ] || die "refusing to pack a private key: $(echo $secret)
(move it out of the folder, and out of any folder that is synced or
under version control)"
TAR="$TOP/SOURCES/$NAME.tar"
(cd "$DIR" && tar --null -T "$LIST" --transform "s|^|$NAME/|" -cf "$TAR")
rm "$LIST"
git -C "$DIR" rev-parse HEAD > "$TOP/COMMIT"
tar -C "$TOP" --transform "s|^|$NAME/|" -rf "$TAR" COMMIT
rm "$TOP/COMMIT"
gzip -9 "$TAR"

rpmbuild --define "_topdir $TOP" -ba "$SPEC"

mapfile -t RPMS < <(find "$TOP/RPMS" "$TOP/SRPMS" -name '*.rpm' | sort)

if [ "$SIGN" = 1 ]; then
    # rpm looks for gpg's keys in ~/.gnupg unless told otherwise.
    "$RPMSIGN" --define "_gpg_name $FPR" \
        ${GNUPGHOME:+--define "_gpg_path $GNUPGHOME"} --addsign "${RPMS[@]}"
    gpg --batch --armor --export "$FPR" > "$TOP/RPM-GPG-KEY-py-wtk"
    # The key published with the RPMs must be the project's, the one in
    # packaging/ (unless another was asked for).
    if [ "$KEY" = "$SIGNING_KEY" ] && [ -f "$DIR/packaging/RPM-GPG-KEY-py-wtk" ]; then
        shipped="$(gpg --batch --with-colons --show-keys "$DIR/packaging/RPM-GPG-KEY-py-wtk" |
            awk -F: '$1 == "fpr" { print $10; exit }')"
        [ "$shipped" = "$FPR" ] ||
            die "packaging/RPM-GPG-KEY-py-wtk is not the key that signed ($FPR)"
    fi
    # Prove it the way a user's dnf will: in a keyring of its own, holding
    # only the exported key, every package must verify. That checks the
    # signatures and that the key file published with them is the right
    # one, without touching the system's keys.
    keyring="$(mktemp -d)"
    trap 'rm -rf "$keyring"' EXIT
    check=(--dbpath "$keyring" --define "_keyring fs"
           --define "_keyringpath $keyring/pubkeys/")
    rpmkeys "${check[@]}" --import "$TOP/RPM-GPG-KEY-py-wtk" ||
        die "the exported key could not be read back"
    for rpm in "${RPMS[@]}"; do
        rpmkeys "${check[@]}" -K "$rpm" >/dev/null ||
            die "$(basename "$rpm") does not verify with the exported key"
    done
fi

echo
echo "Built:"
for rpm in "${RPMS[@]}"; do
    echo "  $rpm"
done
if [ "$SIGN" = 1 ]; then
    echo "Signed by $FPR; public key: $TOP/RPM-GPG-KEY-py-wtk"
fi
