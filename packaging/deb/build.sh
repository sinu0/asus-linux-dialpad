#!/usr/bin/env bash

# Builds Turnpad's .deb (Debian, Ubuntu) from this clone:
#
#   bash packaging/deb/build.sh                # the checked-out commit (HEAD)
#   bash packaging/deb/build.sh <commit>       # another commit, tag or branch
#   bash packaging/deb/build.sh --worktree     # HEAD plus uncommitted changes
#   bash packaging/deb/build.sh -o <dir> ...   # where the .deb goes
#
# then: sudo apt install ./asus-turnpad_*.deb and, once as your user,
# asus-turnpad-setup. Needs: sudo apt install build-essential debhelper dh-python git
#
# The package is built from a copy exported with git archive in a temporary
# directory; the clone is never written to (--worktree only adds a git object).

set -euo pipefail

SRC=$(realpath "$(dirname "$0")/../..")
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/asus-turnpad/deb"
REV=HEAD
DIRTY=""
while (( $# )); do
    case $1 in
        -o) OUT=$2; shift 2 ;;
        --worktree) REV=$(git -C "$SRC" stash create); REV=${REV:-HEAD}; [[ $REV != HEAD ]] && DIRTY=".dirty"; shift ;;
        -h|--help) sed -n '3,15p' "$0"; exit 0 ;;
        *) REV=$1; shift ;;
    esac
done

for tool in dpkg-buildpackage dh dh_python3 git; do
    command -v "$tool" >/dev/null || { echo "$tool is missing: sudo apt install build-essential debhelper dh-python git"; exit 1; }
done

# Like the Arch package's pkgver (r<commits>.<hash>), after "0." because a
# Debian version starts with a digit. For --worktree the commit is HEAD's.
BASE=$(git -C "$SRC" rev-parse "$REV^{commit}")
[[ -n $DIRTY ]] && BASE=$(git -C "$SRC" rev-parse HEAD)
VERSION="0.r$(git -C "$SRC" rev-list --count "$BASE").$(git -C "$SRC" rev-parse --short=7 "$BASE")$DIRTY"

BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
TREE="$BUILD/asus-turnpad-$VERSION"
mkdir -p "$TREE"
git -C "$SRC" archive "$REV" | tar -x -C "$TREE"
cp -r "$TREE/packaging/deb/debian" "$TREE/debian"
cat > "$TREE/debian/changelog" <<EOF
asus-turnpad ($VERSION) unstable; urgency=medium

  * Built from commit $(git -C "$SRC" rev-parse "$BASE")${DIRTY:+ with uncommitted changes}.

 -- $(sed -n 's/^Maintainer: //p' "$TREE/debian/control")  $(git -C "$SRC" log -1 --format=%cD "$BASE")
EOF

(cd "$TREE" && dpkg-buildpackage --build=binary --no-sign)

mkdir -p "$OUT"
cp "$BUILD"/asus-turnpad_"$VERSION"_all.deb "$OUT/"
echo
echo "Built $OUT/asus-turnpad_${VERSION}_all.deb"
echo "Install: sudo apt install $OUT/asus-turnpad_${VERSION}_all.deb"
