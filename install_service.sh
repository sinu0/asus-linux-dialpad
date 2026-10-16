#!/usr/bin/env bash

source non_sudo_check.sh

source install_paths.sh

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
    INSTALL_DIR_PATH=$INSTALL_DIR_PATH LAYOUT_NAME=$LAYOUT_NAME CONFIG_FILE_DIR_PATH="$CONFIG_FILE_DIR_PATH/" \
    DISPLAY=$DISPLAY WAYLAND_DISPLAY=$WAYLAND_DISPLAY XAUTHORITY=$XAUTHORITY XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
    XDG_SESSION_TYPE=$XDG_SESSION_TYPE DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS LOG_ENV_LINE=$LOG_ENV_LINE \
        envsubst '$INSTALL_DIR_PATH $LAYOUT_NAME $CONFIG_FILE_DIR_PATH $DISPLAY $WAYLAND_DISPLAY $XAUTHORITY $XDG_RUNTIME_DIR $XDG_SESSION_TYPE $DBUS_SESSION_BUS_ADDRESS $LOG_ENV_LINE' \
        < "$template" > "$SERVICE_INSTALL_DIR_PATH/$name"
}

# start_unit <name>: enables the service and (re)starts it now.
start_unit() {
    local name=$1
    systemctl --user daemon-reload || { echo "Something went wrong when reloading the systemd user manager"; exit 1; }
    systemctl --user enable "$name" || { echo "Something went wrong when enabling $name"; exit 1; }
    systemctl --user restart "$name" || { echo "Something went wrong when starting $name"; exit 1; }
    echo "$name enabled and started"
}

echo "Systemctl service(s)"
echo

if ask "Do you want install systemctl service(s)?" y; then

    # check rpm-ostree FIRST before dnf/yum (for BazziteOS/Fedora Atomic/Silverblue)
    # because dnf may exist as a wrapper that blocks usage on immutable systems
    # https://github.com/asus-linux-drivers/asus-numberpad-driver/pull/280
    if [[ $(command -v rpm-ostree 2>/dev/null) ]] && grep -qi "ostree" /etc/os-release 2>/dev/null; then

        PACKAGES="systemd-devel python3-systemd"
        MISSING_PACKAGES=""
        for pkg in $PACKAGES; do
            if ! rpm -q "$pkg" >/dev/null 2>&1; then
                MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
            fi
        done

        if [ -n "$MISSING_PACKAGES" ]; then
            sudo rpm-ostree --allow-inactive install $MISSING_PACKAGES
        fi
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get -y install libsystemd-dev python3-systemd
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman --noconfirm --needed -S systemd python-systemd
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf -y install systemd-devel python3-systemd
    elif command -v yum >/dev/null 2>&1; then
        sudo yum -y install systemd-devel python3-systemd
    elif command -v zypper >/dev/null 2>&1; then
        sudo zypper --non-interactive install systemd-devel python3-systemd
    elif command -v xbps-install >/dev/null 2>&1; then
        sudo xbps-install -Suy systemd python3-systemd
    elif command -v emerge >/dev/null 2>&1; then
        sudo emerge sys-apps/systemd dev-python/python-systemd
    elif command -v eopkg >/dev/null 2>&1; then
        sudo eopkg install -y systemd-devel python-systemd
    else
        echo "Not detected package manager. Driver may not work properly because required packages have not been installed. Please create an issue (https://github.com/sinu0/asus-linux-dialpad/issues)."
    fi

    venv_pip install -r requirements.systemd.txt

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

    if [ "$USER_INTERFACE" -eq 1 ]; then
        echo
        install_unit "$SLUG-ui.$SESSION_KIND.service" "$UI_SERVICE" || { echo "Something went wrong when placing $UI_SERVICE"; exit 1; }
        echo "$UI_SERVICE placed"
        start_unit "$UI_SERVICE"
    fi
fi
