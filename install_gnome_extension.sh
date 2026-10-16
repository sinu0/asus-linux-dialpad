#!/usr/bin/env bash

if [ -z "$INSTALL_DIR_PATH" ]; then
    INSTALL_DIR_PATH="/usr/share/asus-dialpad-driver"
fi

if [[ "$XDG_CURRENT_DESKTOP" != *GNOME* ]]; then
    echo "GNOME desktop not detected; skipping GNOME extension installation."
elif ! command -v gnome-extensions >/dev/null 2>&1; then
    echo "gnome-extensions is not available; skipping GNOME extension installation."
else
    EXTENSION_DIR="$HOME/.local/share/gnome-shell/extensions/dialpad@asus-linux-drivers"
    mkdir -p "$EXTENSION_DIR"
    install -m 644 "$INSTALL_DIR_PATH/gnome/extension/extension.js" "$INSTALL_DIR_PATH/gnome/extension/dial.js" "$INSTALL_DIR_PATH/gnome/extension/layers.js" "$INSTALL_DIR_PATH/gnome/extension/skins.json" "$INSTALL_DIR_PATH/gnome/extension/metadata.json" "$INSTALL_DIR_PATH/gnome/extension/stylesheet.css" "$EXTENSION_DIR/"

    if gnome-extensions enable dialpad@asus-linux-drivers; then
        if ! systemctl --user disable --now "asus_dialpad_driver_ui@$USER.service"; then
            echo "WARNING: Could not disable and stop the legacy DialPad UI service."
        fi
    else
        echo "WARNING: Could not enable the GNOME DialPad extension."
    fi
fi
