#!/usr/bin/env bash

# The layer-shell dial (overlay/layer_shell.py) on a headless compositor in
# a clean Arch Linux container, compared with the GNOME extension's painting:
#
#   docker run --rm -v "$PWD:/src:ro" archlinux:latest \
#       bash /src/tests/layer_shell_in_container.sh /src sway [output-dir]
#
# Installs the compositor, GTK 4, gtk4-layer-shell, grim and fonts, then
# runs tests/layer_shell_check.py as an unprivileged user in a private D-Bus
# session with a scratch HOME. Pictures and logs go to output-dir (default
# /tmp/layer-shell-test). Compositors: sway (kwin is planned: it needs a
# screenshot path grim can use).
#
# TURNPAD_SKIP_PACKAGES=1 skips pacman for an image that has them already.

set -euo pipefail

SRC=$(realpath "${1:?usage: layer_shell_in_container.sh <clone of asus-turnpad> [sway] [output-dir]}")
COMPOSITOR=${2:-sway}
OUTPUT=${3:-/tmp/layer-shell-test}
TESTER=tester

case "$COMPOSITOR" in
    sway) compositor_packages=(sway grim wtype) ;;
    *) echo "unknown compositor: $COMPOSITOR (supported: sway)"; exit 2 ;;
esac

if [ -z "${TURNPAD_SKIP_PACKAGES:-}" ]; then
    echo "== packages"
    pacman -Syu --noconfirm --needed "${compositor_packages[@]}" gtk4 gtk4-layer-shell \
        python python-gobject python-cairo python-pillow librsvg gjs dbus \
        adwaita-icon-theme adwaita-fonts >/tmp/pacman.log 2>&1 || { tail -30 /tmp/pacman.log; exit 1; }
fi
pacman -Q "${compositor_packages[@]}" gtk4 gtk4-layer-shell 2>/dev/null || true

id "$TESTER" >/dev/null 2>&1 || useradd -m "$TESTER"
SCRATCH=$(mktemp -d /tmp/turnpad-layer-shell.XXXXXX)
mkdir -p "$SCRATCH/home" "$SCRATCH/runtime" "$OUTPUT"
chmod 700 "$SCRATCH/runtime"
chown -R "$TESTER:" "$SCRATCH" "$OUTPUT"

echo "== $COMPOSITOR"
status=0
runuser -u "$TESTER" -- env -i PATH=/usr/bin:/bin LANG=C.UTF-8 HOME="$SCRATCH/home" \
    XDG_RUNTIME_DIR="$SCRATCH/runtime" XDG_CONFIG_HOME="$SCRATCH/home/.config" \
    dbus-run-session -- python3 "$SRC/tests/layer_shell_check.py" "$COMPOSITOR" "$OUTPUT" || status=$?
rm -rf "$SCRATCH"
exit $status
