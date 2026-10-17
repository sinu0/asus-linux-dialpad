#!/usr/bin/env bash

# Builds Turnpad's Arch package from the latest commit on GitHub and installs
# it with pacman; the same command updates it. Extra arguments go to makepkg
# (for example --noconfirm).
#
# makepkg runs in a cache directory, not in this clone: it writes the new
# version into the PKGBUILD it builds from, which would leave the clone
# modified and get in the way of the next git pull.

set -euo pipefail

HERE=$(dirname "$(realpath "$0")")
BUILD="${XDG_CACHE_HOME:-$HOME/.cache}/asus-turnpad/makepkg"

mkdir -p "$BUILD"
cp "$HERE/PKGBUILD" "$HERE/asus-turnpad.install" "$BUILD/"
cd "$BUILD"
rm -f ./*.pkg.tar.*
makepkg -si "$@"

echo
if systemctl --user is-enabled asus-turnpad.service >/dev/null 2>&1; then
    systemctl --user restart asus-turnpad.service && echo "Driver restarted with the new version."
else
    echo "First install? Run asus-turnpad-setup once as your user, then log out and back in."
fi
