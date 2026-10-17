#!/usr/bin/env bash

# Moves an install from before the rename (asus-dialpad-driver, D-Bus
# io.github.asuslinuxdrivers.DialPad) to the current names, and removes the
# Python environment that installs had before they used distribution
# packages only. Safe to run on every install: each step only acts when the
# old item still exists.
#
#   migrate_legacy_config   ~/.config/asus-dialpad -> ~/.config/asus-turnpad,
#                           driver state from the old install directory
#   migrate_legacy_logs     /var/log/asus-dialpad-driver -> /var/log/asus-turnpad
#   remove_legacy_venv      /opt/asus-turnpad/.env
#   remove_legacy_install   services, extension, launcher, program, udev
#                           rules and module lists under the old names; the
#                           old Python environment and services that ran it;
#                           the legacy window's service on Wayland

source install_paths.sh

LEGACY_INSTALL_DIR_PATH="/usr/share/asus-dialpad-driver"
LEGACY_CONFIG_DIR_PATH="${XDG_CONFIG_HOME:-$HOME/.config}/asus-dialpad"
LEGACY_LOGS_DIR_PATH="/var/log/asus-dialpad-driver"
LEGACY_APP_ID="io.github.asuslinuxdrivers.DialPadControl"
LEGACY_GNOME_EXTENSION_UUID="dialpad@asus-linux-drivers"
# Python environment built with pip by earlier versions of install.sh.
LEGACY_VENV_PATH="$INSTALL_DIR_PATH/.env"

migrate_legacy_config() {
    if [ -d "$LEGACY_CONFIG_DIR_PATH" ] && [ ! -e "$CONFIG_FILE_DIR_PATH" ]; then
        mv "$LEGACY_CONFIG_DIR_PATH" "$CONFIG_FILE_DIR_PATH"
        echo "Moved settings from $LEGACY_CONFIG_DIR_PATH to $CONFIG_FILE_DIR_PATH"
    fi
    mkdir -p "$CONFIG_FILE_DIR_PATH"
    if [ -f "$LEGACY_INSTALL_DIR_PATH/$CONFIG_FILE_NAME" ] && [ ! -f "$CONFIG_FILE_PATH" ]; then
        cp "$LEGACY_INSTALL_DIR_PATH/$CONFIG_FILE_NAME" "$CONFIG_FILE_PATH"
        echo "Copied driver state to $CONFIG_FILE_PATH"
    fi
}

migrate_legacy_logs() {
    if [ -d "$LEGACY_LOGS_DIR_PATH" ] && [ ! -e "$LOGS_DIR_PATH" ]; then
        sudo mv "$LEGACY_LOGS_DIR_PATH" "$LOGS_DIR_PATH"
    fi
}

remove_legacy_venv() {
    if [ -d "$LEGACY_VENV_PATH" ]; then
        sudo rm -rf "$LEGACY_VENV_PATH"
        echo "Removed the old Python environment $LEGACY_VENV_PATH"
    fi
}

remove_legacy_install() {
    local unit
    for unit in "asus_dialpad_driver@$USER.service" "asus_dialpad_driver_ui@$USER.service"; do
        if systemctl --user cat "$unit" >/dev/null 2>&1; then
            systemctl --user disable --now "$unit" >/dev/null 2>&1
            echo "Stopped and disabled $unit"
        fi
    done
    rm -f "$SERVICE_INSTALL_DIR_PATH/asus_dialpad_driver@.service" "$SERVICE_INSTALL_DIR_PATH/asus_dialpad_driver_ui@.service"
    # Services that ran the old environment's Python; install_service.sh
    # places new ones.
    for unit in "$DRIVER_SERVICE" "$UI_SERVICE"; do
        if grep -qF "$LEGACY_VENV_PATH/" "$SERVICE_INSTALL_DIR_PATH/$unit" 2>/dev/null; then
            systemctl --user disable --now "$unit" >/dev/null 2>&1
            rm -f "$SERVICE_INSTALL_DIR_PATH/$unit"
            echo "Removed $unit (it ran $LEGACY_VENV_PATH)"
        fi
    done
    # The legacy window's service for Wayland sessions (templates
    # asus-turnpad-ui.wayland/plasma-wayland.service, removed); Wayland
    # desktops now get the Shell extension or the layer-shell dial. Only the
    # X11 one sets XAUTHORITY.
    if grep -qF "dialpad_ui.py" "$SERVICE_INSTALL_DIR_PATH/$UI_SERVICE" 2>/dev/null &&
       ! grep -qF "XAUTHORITY=" "$SERVICE_INSTALL_DIR_PATH/$UI_SERVICE"; then
        systemctl --user disable --now "$UI_SERVICE" >/dev/null 2>&1
        rm -f "$SERVICE_INSTALL_DIR_PATH/$UI_SERVICE"
        echo "Removed $UI_SERVICE (the legacy window on Wayland)"
    fi
    systemctl --user daemon-reload

    if command -v gnome-extensions >/dev/null 2>&1; then
        gnome-extensions disable "$LEGACY_GNOME_EXTENSION_UUID" >/dev/null 2>&1
    fi
    rm -rf "$HOME/.local/share/gnome-shell/extensions/$LEGACY_GNOME_EXTENSION_UUID"
    rm -f "$HOME/.local/share/applications/$LEGACY_APP_ID.desktop"
    rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/$LEGACY_APP_ID.svg"

    if [ -d "$LEGACY_INSTALL_DIR_PATH" ]; then
        sudo rm -rf "$LEGACY_INSTALL_DIR_PATH"
        echo "Removed $LEGACY_INSTALL_DIR_PATH"
    fi
    remove_legacy_venv

    local rules_dir
    for rules_dir in /usr/lib/udev/rules.d /etc/udev/rules.d; do
        sudo rm -f "$rules_dir/99-asus-dialpad-driver-uinput.rules" \
            "$rules_dir/99-asus-dialpad-driver-i2c-dev.rules" \
            "$rules_dir/70-asus-dialpad-driver-hidraw.rules"
    done
    sudo rm -f /etc/modules-load.d/uinput-asus-dialpad-driver.conf \
        /etc/modules-load.d/i2c-dev-asus-dialpad-driver.conf
    rm -f /tmp/dialpad.sock 2>/dev/null
}
