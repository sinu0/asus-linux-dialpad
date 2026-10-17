#!/usr/bin/env bash

source non_sudo_check.sh

source install_common.sh "$@"

source install_paths.sh

source install_packages.sh

if [ -z "$LAYOUT_NAME" ]; then
    LAYOUT_NAME="asusvivobook16x"
fi
if [ -z "$USER_INTERFACE" ]; then
    USER_INTERFACE=1
fi

# install_unit <template> <installed name>: fills in the paths and the
# session environment and places the user service.
install_unit() {
    local template=$1
    local name=$2
    PYTHON=$PYTHON INSTALL_DIR_PATH=$INSTALL_DIR_PATH LAYOUT_NAME=$LAYOUT_NAME CONFIG_FILE_DIR_PATH="$CONFIG_FILE_DIR_PATH/" \
    DISPLAY=$DISPLAY WAYLAND_DISPLAY=$WAYLAND_DISPLAY XAUTHORITY=$XAUTHORITY XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
    XDG_SESSION_TYPE=$XDG_SESSION_TYPE DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS LOG_ENV_LINE=$LOG_ENV_LINE \
        envsubst '$PYTHON $INSTALL_DIR_PATH $LAYOUT_NAME $CONFIG_FILE_DIR_PATH $DISPLAY $WAYLAND_DISPLAY $XAUTHORITY $XDG_RUNTIME_DIR $XDG_SESSION_TYPE $DBUS_SESSION_BUS_ADDRESS $LOG_ENV_LINE' \
        < "$template" > "$SERVICE_INSTALL_DIR_PATH/$name"
}

# start_unit <name>: enables the service and (re)starts it now.
start_unit() {
    local name=$1
    if [ "$INSTALL_IN_CONTAINER" = "1" ]; then
        echo "Container install: $name placed, not started"
        return
    fi
    systemctl --user daemon-reload || { echo "Something went wrong when reloading the systemd user manager"; exit 1; }
    systemctl --user enable "$name" || { echo "Something went wrong when enabling $name"; exit 1; }
    systemctl --user restart "$name" || { echo "Something went wrong when starting $name"; exit 1; }
    echo "$name enabled and started"
}

echo "Systemctl service(s)"
echo

if ask "Do you want install systemctl service(s)?" y; then

    # python-systemd sends the driver's log to the journal (optional; the
    # service then logs nothing).
    detect_package_manager
    install_optional $(packages systemd)

    SERVICE=1

    echo
    echo "LAYOUT_NAME: $LAYOUT_NAME"
    echo "CONFIG_FILE_DIR_PATH: $CONFIG_FILE_DIR_PATH"
    echo
    echo "env var DISPLAY: $DISPLAY"
    echo "env var WAYLAND_DISPLAY: $WAYLAND_DISPLAY"
    echo "env var XAUTHORITY: $XAUTHORITY"
    echo "env var XDG_RUNTIME_DIR: $XDG_RUNTIME_DIR"
    echo "env var DBUS_SESSION_BUS_ADDRESS: $DBUS_SESSION_BUS_ADDRESS"
    echo "env var XDG_SESSION_TYPE: $XDG_SESSION_TYPE"

    # with no gdm is env var XDG_SESSION_TYPE tty - https://github.com/asus-linux-drivers/asus-numberpad-driver/issues/185
    if [ "$XDG_SESSION_TYPE" == "tty" ] || [ "$XDG_SESSION_TYPE" == "" ]; then
        echo
        echo "Env var XDG_SESSION_TYPE is: \"$XDG_SESSION_TYPE\""
        echo
        echo "Please, select your display manager:"
        echo
        PS3="Please enter your choice "
        OPTIONS=("x11" "wayland" "Quit")
        select SELECTED_OPT in "${OPTIONS[@]}"; do
            if [ "$SELECTED_OPT" = "Quit" ]; then
                exit 0
            fi
            if [ -n "$SELECTED_OPT" ]; then
                XDG_SESSION_TYPE=$SELECTED_OPT
                echo
                echo "(SET UP FOR DRIVER ONLY) env var XDG_SESSION_TYPE: $XDG_SESSION_TYPE"
                echo
                break
            fi
            echo "invalid option $REPLY"
        done
    fi

    echo

    if [ -n "$LOG" ]; then
        LOG_ENV_LINE="Environment=\"LOG=$LOG\""
    else
        LOG_ENV_LINE=""
    fi

    # Plasma brings its own session environment and session target.
    SESSION_KIND=$XDG_SESSION_TYPE
    if [ "$XDG_SESSION_TYPE" == "wayland" ] && \
       { [[ ":$XDG_CURRENT_DESKTOP:" == *:KDE:* ]] || [[ "$DESKTOP_SESSION" == plasma* ]]; }; then
        SESSION_KIND=plasma-wayland
    fi
    if [ "$XDG_SESSION_TYPE" != "x11" ]; then
        echo "Unfortunatelly you will not be able use feature: Disabling Touchpad (e.g. Fn+special key) disables DialPad aswell, at this moment is supported only X11"
    fi

    mkdir -p "$SERVICE_INSTALL_DIR_PATH"
    install_unit "$SLUG.$SESSION_KIND.service" "$DRIVER_SERVICE" || { echo "Something went wrong when placing $DRIVER_SERVICE"; exit 1; }
    echo "$DRIVER_SERVICE placed"
    start_unit "$DRIVER_SERVICE"

    # The legacy window is for X11; Wayland desktops get their dial from
    # install_overlay.sh.
    if [ "$USER_INTERFACE" -eq 1 ] && [ "$SESSION_KIND" == "x11" ]; then
        echo
        install_unit "$SLUG-ui.x11.service" "$UI_SERVICE" || { echo "Something went wrong when placing $UI_SERVICE"; exit 1; }
        echo "$UI_SERVICE placed"
        start_unit "$UI_SERVICE"
    fi
fi
