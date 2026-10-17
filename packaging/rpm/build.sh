#!/usr/bin/env bash

# Builds Turnpad's .rpm (Fedora) from this clone:
#
#   bash packaging/rpm/build.sh                # the checked-out commit (HEAD)
#   bash packaging/rpm/build.sh <commit>       # another commit, tag or branch
#   bash packaging/rpm/build.sh --worktree     # HEAD plus uncommitted changes
#   bash packaging/rpm/build.sh -o <dir> ...   # where the .rpm goes
#
# then: sudo dnf install ./asus-turnpad-*.noarch.rpm and, once as your user,
# asus-turnpad-setup. Needs: sudo dnf install rpm-build python3-devel systemd-rpm-macros desktop-file-utils git
#
# rpmbuild runs in a temporary directory on a tarball made with git archive;
# the clone is never written to (--worktree only adds a git object).

set -euo pipefail

SRC=$(realpath "$(dirname "$0")/../..")
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/asus-turnpad/rpm"
REV=HEAD
DIRTY=""
while (( $# )); do
    case $1 in
        -o) OUT=$2; shift 2 ;;
        --worktree) REV=$(git -C "$SRC" stash create); REV=${REV:-HEAD}; [[ $REV != HEAD ]] && DIRTY=".dirty"; shift ;;
        -h|--help) sed -n '3,14p' "$0"; exit 0 ;;
        *) REV=$1; shift ;;
    esac
done

for tool in rpmbuild git; do
    command -v "$tool" >/dev/null || { echo "$tool is missing: sudo dnf install rpm-build python3-devel systemd-rpm-macros desktop-file-utils git"; exit 1; }
done

# Like the Arch package's pkgver (r<commits>.<hash>), after "0." so it sorts
# below real version numbers. For --worktree the commit is HEAD's.
BASE=$(git -C "$SRC" rev-parse "$REV^{commit}")
[[ -n $DIRTY ]] && BASE=$(git -C "$SRC" rev-parse HEAD)
VERSION="0.r$(git -C "$SRC" rev-list --count "$BASE").$(git -C "$SRC" rev-parse --short=7 "$BASE")$DIRTY"

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
mkdir -p "$BUILD/SOURCES"
git -C "$SRC" archive --format=tar.gz --prefix="asus-turnpad-$VERSION/" -o "$BUILD/SOURCES/asus-turnpad-$VERSION.tar.gz" "$REV"
# The spec of the same commit.
git -C "$SRC" show "$REV:packaging/rpm/asus-turnpad.spec" > "$BUILD/asus-turnpad.spec"

rpmbuild -bb --define "_topdir $BUILD" --define "turnpad_version $VERSION" "$BUILD/asus-turnpad.spec"

mkdir -p "$OUT"
cp "$BUILD"/RPMS/noarch/asus-turnpad-"$VERSION"-*.noarch.rpm "$OUT/"
RPM=$(cd "$OUT" && ls -t asus-turnpad-"$VERSION"-*.noarch.rpm | head -1)
echo
echo "Built $OUT/$RPM"
echo "Install: sudo dnf install $OUT/$RPM"
