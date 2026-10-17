#!/usr/bin/env bash

# Runs the settings app on the oldest GTK and Libadwaita it supports:
# tests/test_settings_layout.py (every page and the main dialogs at monitor
# sizes from 1080p to 4K, in a headless mutter) in a clean container.
# Ubuntu 24.04 has GTK 4.14 and Libadwaita 1.5, Debian 13 has 4.18 and 1.7:
#
#   podman run --rm -v "$PWD:/src:ro" ubuntu:24.04 bash /src/tests/settings_in_container.sh /src
#
# Nothing is installed from the clone; the app runs from it on a demo
# configuration with HOME in a temporary directory.

set -euo pipefail

SRC=$(realpath "${1:?usage: settings_in_container.sh <clone of asus-turnpad>}")

echo "== prepare $(. /etc/os-release && echo "$PRETTY_NAME")"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
    python3 python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-rsvg-2.0 \
    gir1.2-graphene-1.0 mutter dbus dbus-daemon adwaita-icon-theme fonts-cantarell >/dev/null

export HOME XDG_RUNTIME_DIR PYTHONDONTWRITEBYTECODE=1
HOME=$(mktemp -d)
XDG_RUNTIME_DIR=$(mktemp -d)
cd "$SRC"
python3 - <<'EOF'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
print("GTK %d.%d, Libadwaita %d.%d" % (Gtk.get_major_version(), Gtk.get_minor_version(),
                                       Adw.get_major_version(), Adw.get_minor_version()))
EOF
command -v mutter dbus-run-session >/dev/null || { echo "mutter or dbus-run-session missing"; exit 1; }

echo "== settings app at every page and dialog"
# The test skips itself without mutter; here that would be a failure.
python3 -m unittest -v tests.test_settings_layout 2>&1 | tee /tmp/settings-test.log
grep -q "skipped" /tmp/settings-test.log && { echo "the test was skipped"; exit 1; }
echo "== settings test passed"
