#!/usr/bin/env bash

# Installs the on-screen dial that suits the running desktop. Every desktop
# frontend reads the same D-Bus signals (io.github.sinu0.AsusTurnpad.Driver)
# and config.json; see ARCHITECTURE.md. A new frontend gets its own
# install_<desktop>_overlay.sh and a case here.
#
#   GNOME                       Shell extension (install_gnome_extension.sh)
#   other Wayland desktops      layer-shell dial (install_layer_shell_overlay.sh):
#                               KDE Plasma 6, Hyprland, sway, niri, COSMIC
#   X11                         legacy PySide window (install_user_interface.sh)

case "${XDG_CURRENT_DESKTOP,,}" in
    *gnome*)
        source install_gnome_extension.sh
        ;;
    *)
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            source install_layer_shell_overlay.sh
        else
            # X11 has no layer-shell; the legacy window of
            # install_user_interface.sh shows the dial there.
            echo "No native on-screen dial for ${XDG_CURRENT_DESKTOP:-this desktop} on ${XDG_SESSION_TYPE:-this session}; using the DialPad User Interface window if installed."
        fi
        ;;
esac
