#!/usr/bin/env bash

# Installs Turnpad with install.sh in a clean distribution container, checks
# the result and uninstalls it again. CI runs it for Fedora and Ubuntu:
#
#   docker run --rm -v "$PWD:/src:ro" fedora:latest bash /src/tests/install_in_container.sh /src
#
# A container has no DialPad, kernel modules or user services, so install.sh
# runs with INSTALL_IN_CONTAINER=1 (see install_common.sh); everything that
# differs between distributions is tested: package names, the Python
# environment built by pip, the installed files, the user service file and
# the libraries the driver and the settings app import.

set -euo pipefail

SRC=$(realpath "${1:?usage: install_in_container.sh <clone of asus-turnpad>}")
TESTER=tester
APP=/opt/asus-turnpad

echo "== prepare $(. /etc/os-release && echo "$PRETTY_NAME")"
if command -v apt-get >/dev/null; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq sudo python3 >/dev/null
elif command -v dnf >/dev/null; then
    dnf -y -q install sudo python3 >/dev/null
elif command -v pacman >/dev/null; then
    pacman -Syu --noconfirm --needed sudo python >/dev/null
fi
id "$TESTER" >/dev/null 2>&1 || useradd -m "$TESTER"
echo "$TESTER ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/"$TESTER"
HOME_DIR=$(getent passwd "$TESTER" | cut -d: -f6)
rm -rf "$HOME_DIR/turnpad"
cp -a "$SRC" "$HOME_DIR/turnpad"
rm -rf "$HOME_DIR/turnpad/.git"
chown -R "$TESTER:" "$HOME_DIR/turnpad"

as_tester() {
    # A GNOME Wayland session as install.sh sees it; the layout is given so
    # the installer does not look the laptop up online.
    sudo -u "$TESTER" -H env INSTALL_IN_CONTAINER=1 LAYOUT_NAME=proartp16 \
        XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=GNOME XDG_RUNTIME_DIR=/tmp \
        bash -c "cd ~/turnpad && $1"
}

echo "== install.sh"
as_tester "bash install.sh" > /tmp/install.log 2>&1 || { tail -40 /tmp/install.log; echo "install.sh failed"; exit 1; }
grep -q "Installation finished successfully" /tmp/install.log || { tail -40 /tmp/install.log; exit 1; }

echo "== files"
for path in "$APP/dialpad.py" "$APP/layout_detect.py" "$APP/config_app/main.py" "$APP/gnome/extension/skins.json" \
    "$APP/.env/bin/python3" "$HOME_DIR/.config/systemd/user/asus-turnpad.service" \
    "$HOME_DIR/.local/share/applications/io.github.sinu0.AsusTurnpad.desktop" \
    /etc/udev/rules.d/70-asus-turnpad-i2c-dev.rules /etc/modules-load.d/asus-turnpad.conf; do
    test -e "$path" || { echo "missing: $path"; exit 1; }
done
grep -q "ExecStart=$APP/.env/bin/python3 $APP/dialpad.py proartp16 $HOME_DIR/.config/asus-turnpad/" \
    "$HOME_DIR/.config/systemd/user/asus-turnpad.service"
id -nG "$TESTER" | tr ' ' '\n' | grep -qx input

echo "== the driver's libraries in its Python environment"
"$APP/.env/bin/python3" - <<'EOF'
import sys
sys.path.insert(0, "/opt/asus-turnpad")
import libevdev, pyinotify, xkbcommon.xkb, pywayland.client, dbus, systemd.journal, periphery
from pyinotify import ThreadedNotifier
import backlight, dial_gesture, dialpad_dbus, launch, layout_detect
import config.schema, config.legacy_adapter
print("driver imports ok")
EOF

echo "== the settings app's libraries (it runs with the system python3)"
python3 - <<'EOF'
import sys
sys.path.insert(0, "/opt/asus-turnpad")
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Rsvg", "2.0")
from gi.repository import Adw, Gtk, Rsvg
import cairo
version = (Adw.get_major_version(), Adw.get_minor_version())
print("GTK %d.%d, Libadwaita %d.%d" % (Gtk.get_major_version(), Gtk.get_minor_version(), *version))
assert version >= (1, 9), "the settings app needs Libadwaita 1.9 (Adw.ViewSwitcherSidebar)"
assert hasattr(Adw, "ViewSwitcherSidebar")
import config_app.main, overlay.painter, config.skins
assert config.skins.load_skins()
print("settings app imports ok")
EOF

echo "== uninstall.sh"
as_tester "bash uninstall.sh" > /tmp/uninstall.log 2>&1 || { tail -30 /tmp/uninstall.log; echo "uninstall.sh failed"; exit 1; }
for path in "$APP" "$HOME_DIR/.config/systemd/user/asus-turnpad.service" \
    "$HOME_DIR/.local/share/applications/io.github.sinu0.AsusTurnpad.desktop" \
    /etc/udev/rules.d/70-asus-turnpad-i2c-dev.rules /etc/modules-load.d/asus-turnpad.conf; do
    test ! -e "$path" || { echo "left behind: $path"; exit 1; }
done
test -d "$HOME_DIR/.config/asus-turnpad" || { echo "settings were removed"; exit 1; }
echo "== install test passed"
