#!/usr/bin/env bash

# Installs the on-screen dial that suits the running desktop. Every desktop
# frontend reads the same D-Bus signals (io.github.asuslinuxdrivers.DialPad)
# and config.json; see ARCHITECTURE.md. A new frontend gets its own
# install_<desktop>_overlay.sh and a case here.

case "${XDG_CURRENT_DESKTOP,,}" in
    *gnome*)
        source install_gnome_extension.sh
        ;;
    *)
        # Other desktops use the legacy PySide window from
        # install_user_interface.sh.
        echo "No native on-screen dial for \"${XDG_CURRENT_DESKTOP:-this desktop}\" yet; using the DialPad User Interface window if installed."
        ;;
esac
