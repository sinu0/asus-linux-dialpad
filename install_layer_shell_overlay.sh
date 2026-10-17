#!/usr/bin/env bash

# The on-screen dial for Wayland desktops with layer-shell: KDE Plasma 6,
# Hyprland, sway, niri, COSMIC (overlay/layer_shell.py, see ARCHITECTURE.md).
# Sourced by install_overlay.sh after install_service.sh, whose install_unit
# and start_unit place and start the user service $OVERLAY_SERVICE.
#
# gtk4-layer-shell is optional (Ubuntu 24.04 does not package it): without
# it the dial is left out and the driver works as before.

source install_paths.sh

source install_packages.sh

echo "On-screen dial for ${XDG_CURRENT_DESKTOP:-this desktop} (layer-shell)"
echo

detect_package_manager
install_optional $(packages layershell)

if ! "$PYTHON" -c 'import gi; gi.require_version("Gtk4LayerShell", "1.0")' >/dev/null 2>&1; then
    echo "gtk4-layer-shell is not available from the packages of this distribution; the on-screen dial is not installed (the driver works without it)."
    if [ "$PACKAGE_MANAGER" == "rpm-ostree" ]; then
        echo "Layer it with: sudo rpm-ostree install $(packages layershell), reboot and run install.sh again."
    fi
elif [ "$SERVICE" != "1" ]; then
    echo "Without the user services, start the dial in your session yourself:"
    echo "  $PYTHON $INSTALL_DIR_PATH/overlay/layer_shell.py"
else
    mkdir -p "$SERVICE_INSTALL_DIR_PATH"
    install_unit "$OVERLAY_SERVICE" "$OVERLAY_SERVICE" || { echo "Something went wrong when placing $OVERLAY_SERVICE"; exit 1; }
    echo "$OVERLAY_SERVICE placed"
    start_unit "$OVERLAY_SERVICE"
    echo "It starts with every graphical login (graphical-session.target). On sway or Hyprland"
    echo "without a session manager, start it from the compositor's config instead:"
    echo "  exec systemctl --user import-environment WAYLAND_DISPLAY && systemctl --user start $OVERLAY_SERVICE"
fi
