#!/usr/bin/env bash

source non_sudo_check.sh

source install_common.sh "$@"

source install_paths.sh

source install_packages.sh

echo
echo "DialPad User Interface Installation"
echo
echo "You can choose whether to install the DialPad User Interface."
echo "This interface allows you to see what you do on DialPad visually."
echo

USER_INTERFACE=0

UI_DEFAULT=y
if [[ "${XDG_CURRENT_DESKTOP,,}" == *gnome* ]]; then
    # GNOME draws the dial with the Shell extension instead.
    UI_DEFAULT=n
fi

if ask "Do you want to install the DialPad User Interface?" "$UI_DEFAULT"; then

    # PySide6 from the distribution; not every release packages it
    # (Ubuntu 24.04 does not), and the window is then left out.
    detect_package_manager
    install_optional $(packages ui)

    if ! "$PYTHON" -c "import PySide6.QtWidgets, PySide6.QtSvg" >/dev/null 2>&1; then
        echo
        echo "PySide6 is not available from the packages of this distribution; the DialPad User Interface is not installed."
        if [ "$PACKAGE_MANAGER" == "rpm-ostree" ]; then
            echo "Layer it with: sudo rpm-ostree install $(packages ui), reboot and run install.sh again."
        fi
    else
        USER_INTERFACE=1

        sudo install dialpad_ui.py "$INSTALL_DIR_PATH"

        echo

        echo "Enabling DialPad User Interface in configuration..."

        if [ ! -f "$CONFIG_FILE_PATH" ]; then
            echo "[main]" | tee "$CONFIG_FILE_PATH" > /dev/null
        fi

        # check if the setting already exists
        if grep -q "socket_enabled" "$CONFIG_FILE_PATH"; then
            sed -i "s/socket_enabled.*/socket_enabled = 1/" "$CONFIG_FILE_PATH"
        else
            # add new setting under [main] section
            sed -i "/\[main\]/a socket_enabled = 1" "$CONFIG_FILE_PATH"
        fi
    fi
fi
