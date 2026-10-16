#!/usr/bin/env bash

source install_paths.sh

if [[ "$XDG_CURRENT_DESKTOP" != *GNOME* ]]; then
    echo "GNOME desktop not detected; skipping GNOME extension installation."
elif ! command -v gnome-extensions >/dev/null 2>&1; then
    echo "gnome-extensions is not available; skipping GNOME extension installation."
else
    mkdir -p "$GNOME_EXTENSION_DIR"
    install -m 644 "$INSTALL_DIR_PATH/gnome/extension/extension.js" "$INSTALL_DIR_PATH/gnome/extension/dial.js" "$INSTALL_DIR_PATH/gnome/extension/layers.js" "$INSTALL_DIR_PATH/gnome/extension/skins.json" "$INSTALL_DIR_PATH/gnome/extension/metadata.json" "$INSTALL_DIR_PATH/gnome/extension/stylesheet.css" "$GNOME_EXTENSION_DIR/"

    # A newly installed extension is only known to GNOME Shell after the
    # next login; enabling it in settings makes the Shell load it then.
    if gnome-extensions enable "$GNOME_EXTENSION_UUID" 2>/dev/null; then
        echo "GNOME extension $GNOME_EXTENSION_UUID enabled"
    else
        gsettings set org.gnome.shell enabled-extensions \
            "$(python3 -c 'import ast, sys; items = ast.literal_eval(sys.argv[1] if sys.argv[1].startswith("[") else "[]"); items.append(sys.argv[2]) if sys.argv[2] not in items else None; print(items)' "$(gsettings get org.gnome.shell enabled-extensions | sed 's/^@as //')" "$GNOME_EXTENSION_UUID")"
        echo "GNOME extension $GNOME_EXTENSION_UUID will be enabled at the next login"
    fi

    if systemctl --user cat "$UI_SERVICE" >/dev/null 2>&1; then
        # GNOME draws the dial with the extension, not the legacy window.
        systemctl --user disable --now "$UI_SERVICE" || echo "WARNING: Could not disable and stop $UI_SERVICE."
    fi
fi
