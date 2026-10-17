#!/usr/bin/env bash

source non_sudo_check.sh

source install_common.sh "$@"

source install_paths.sh

source install_migrate.sh

source install_security_check.sh

# A distribution package (packaging/arch) installs to /usr/share; two
# installs would start two drivers.
if [ -d /usr/share/asus-turnpad ]; then
    echo "Turnpad is installed as a package (/usr/share/asus-turnpad)."
    echo "Update it with your package manager, or remove it first (Arch: sudo pacman -R asus-turnpad-git)."
    exit 1
fi

echo

START_TIME=${EPOCHREALTIME::-7}

migrate_legacy_logs

source install_logs.sh

echo

# log output from every installing attempt aswell
LOGS_INSTALL_LOG_FILE_NAME=install-"$(date +"%d-%m-%Y-%H-%M-%S")".log
LOGS_INSTALL_LOG_FILE_PATH="$LOGS_DIR_PATH/$LOGS_INSTALL_LOG_FILE_NAME"

# The installer's exit status, not the one of tee below.
set -o pipefail


{
    # determine plasma version
    # https://github.com/asus-linux-drivers/asus-numberpad-driver/pull/255
    if command -v kinfo >/dev/null 2>&1; then
        PLASMA_VER=$(kinfo 2>/dev/null | awk -F': ' '/KDE Plasma Version/ {print $2}' | cut -d. -f1)
    else
        PLASMA_VER=6  # default to plasma 6 for modern systems
    fi

    # check rpm-ostree FIRST before dnf/yum (for BazziteOS/Fedora Atomic/Silverblue)
    # because dnf may exist as a wrapper that blocks usage on immutable systems
    # https://github.com/asus-linux-drivers/asus-numberpad-driver/pull/280
    if command -v rpm-ostree >/dev/null 2>&1 && grep -qi "ostree" /etc/os-release 2>/dev/null; then

        PACKAGE_MANAGER="rpm-ostree"

        # note: systemd packages are installed separately in install_service.sh if user chooses systemd
        PACKAGES="curl i2c-tools python3-devel python3-pyatspi wayland-protocols-devel gcc pkg-config libxkbcommon-devel cairo-devel cairo-gobject-devel glib2-devel gobject-introspection-devel dbus-devel"

        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            PACKAGES="$PACKAGES xinput libxcb-devel"
        fi

        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            PACKAGES="$PACKAGES wayland-devel"
        fi

        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            PACKAGES="$PACKAGES qt$PLASMA_VER-qttools"
        fi

        MISSING_PACKAGES=""
        for pkg in $PACKAGES; do
            if ! rpm -q "$pkg" >/dev/null 2>&1; then
                MISSING_PACKAGES="$MISSING_PACKAGES $pkg"
            fi
        done

        if [ -n "$MISSING_PACKAGES" ]; then
            sudo rpm-ostree install --allow-inactive $MISSING_PACKAGES
        fi
    elif command -v apt-get >/dev/null 2>&1; then
        PACKAGE_MANAGER="apt"
        sudo apt-get -y install ibus libevdev2 curl i2c-tools python3-dev python3-virtualenv python3-pyatspi libxml2-utils libxkbcommon-dev libdbus-1-dev gcc pkg-config \
            libglib2.0-dev libgirepository-2.0-dev libcairo2-dev gettext-base \
            python3-gi python3-gi-cairo python3-cairo gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-rsvg-2.0
        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            sudo apt-get -y install xinput
        fi
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            sudo apt-get -y install libwayland-dev
        fi
        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            sudo apt-get -y install qdbus-qt$PLASMA_VER
        fi
    elif command -v pacman >/dev/null 2>&1; then
        PACKAGE_MANAGER="pacman"
        sudo pacman --noconfirm --needed -S ibus libevdev curl i2c-tools python python-virtualenv python-pyatspi python-dbus python-gobject gtk4 libadwaita dbus libxml2 libxkbcommon gcc pkgconf \
            gobject-introspection cairo gettext python-cairo librsvg
        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            sudo pacman --noconfirm --needed -S xorg-xinput
        fi
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            sudo pacman --noconfirm --needed -S wayland
        fi
        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            sudo pacman --noconfirm --needed -S qt$PLASMA_VER-tools
        fi
    elif command -v dnf >/dev/null 2>&1; then
        PACKAGE_MANAGER="dnf"
        sudo dnf -y install ibus libevdev curl i2c-tools python3-devel python3-virtualenv python3-pyatspi libxml2 libxkbcommon-devel dbus-devel gcc pkg-config \
            glib2-devel gobject-introspection-devel cairo-devel cairo-gobject-devel gettext-envsubst \
            python3-gobject python3-cairo gtk4 libadwaita librsvg2
        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            sudo dnf -y install xinput
        fi
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            sudo dnf -y install wayland-devel
        fi
        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            sudo dnf -y install qt$PLASMA_VER-qttools
        fi
    elif command -v yum >/dev/null 2>&1; then
        PACKAGE_MANAGER="yum"
        sudo yum -y install ibus libevdev curl i2c-tools python3-devel python3-pyatspi virtualenv libxml2 libxkbcommon-devel dbus-devel gcc python-pkgconfig
        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            sudo yum -y install xinput
        fi
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            sudo yum -y install wayland-devel
        fi
        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            sudo yum -y install qt$PLASMA_VER-qttools
        fi
    elif command -v zypper >/dev/null 2>&1; then
        PACKAGE_MANAGER="zypper"
        sudo zypper --non-interactive install ibus libevdev2 curl i2c-tools python3-devel python3-virtualenv python3-pyatspi libxml2 libxkbcommon-devel dbus-1-devel gcc pkg-config
        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            sudo zypper --non-interactive install xinput
        fi
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            sudo zypper --non-interactive install wayland-devel
        fi
        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            sudo zypper --non-interactive install qt$PLASMA_VER-tools-qdbus
        fi
    elif command -v xbps-install >/dev/null 2>&1; then
        PACKAGE_MANAGER="xbps-install"
        sudo xbps-install -Suy ibus-devel libevdev-devel curl i2c-tools python3-devel python3-virtualenv python3-pyatspi libxml2 libxkbcommon-devel dbus-devel gcc pkg-config
        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            sudo xbps-install -Suy xinput
        fi
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            sudo xbps-install -Suy wayland-devel
        fi
        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            sudo xbps-install -Suy qt$PLASMA_VER-tools
        fi
    elif command -v emerge >/dev/null 2>&1; then
        PACKAGE_MANAGER="portage"
        sudo emerge app-i18n/ibus dev-libs/libevdev net-misc/curl sys-apps/i2c-tools dev-lang/python dev-python/virtualenv dev-python/pyatspi dev-libs/libxml2 x11-libs/libxkbcommon sys-apps/dbus sys-devel/gcc virtual/pkgconfig
        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            sudo emerge x11-apps/xinput
        fi
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            sudo emerge dev-libs/wayland
        fi
        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            sudo emerge dev-qt/qdbus
        fi
    elif command -v eopkg >/dev/null 2>&1; then
        PACKAGE_MANAGER="eopkg"
        sudo eopkg install -y ibus libevdev curl i2c-tools python3-devel python3-virtualenv python3-pyatspi libxml2-devel libxkbcommon-devel dbus-devel gcc pkg-config
        if [ "$XDG_SESSION_TYPE" == "x11" ]; then
            sudo eopkg install -y xinput
        fi
        if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
            sudo eopkg install -y wayland-devel
        fi
        if [[ "$DESKTOP_SESSION" == plasma* ]]; then
            sudo eopkg install -y qt$PLASMA_VER-tools
        fi
    else
        echo "WARNING: Not detected package manager. Driver may not work properly because required packages have not been installed. Please create an issue (https://github.com/sinu0/asus-turnpad/issues)."
    fi

    if [[ $? != 0 ]]; then
        echo "Error: Something went wrong during installing packages"

        if [[ "$PACKAGE_MANAGER" == "rpm-ostree" && -n "$MISSING_PACKAGES" ]]; then
            echo
            echo "Common issue:"
            echo "  - Not enough disk space (run: sudo rpm-ostree cleanup -b && sudo ostree admin cleanup)"
            echo
        fi

        if ! ask "Do you want to continue anyway?" n; then
            exit 1
        fi
    else
        if [[ "$PACKAGE_MANAGER" == "rpm-ostree" && -n "$MISSING_PACKAGES" ]]; then
            echo
            echo "You must reboot before continuing the installation. After reboot run this script again."
            echo
            if ask "Do you want to reboot now?" n; then
                sudo /sbin/reboot
            fi
            exit 0
        fi
    fi

    # https://github.com/asus-linux-drivers/asus-numberpad-driver/pull/255
    if [ "$DESKTOP_SESSION" == plasma* ] && \
   ! command -v qdbus >/dev/null 2>&1 && \
   ! command -v qdbus6 >/dev/null 2>&1; then
        echo
        echo "WARNING: You are using Plasma desktop environment and qdbus is not available after installation. Manual intervention is required for the driver to function properly." >&2
    fi

    echo

    source install_user_groups.sh

    echo

    if [ "$INSTALL_IN_CONTAINER" = "1" ]; then
        echo "Container install: skipping the touchpad check"
    else
        source install_device_check.sh
    fi

    echo

    # do not install __pycache__
    if [[ -d layouts/__pycache__ ]]; then
        sudo rm -rf layouts/__pycache__
    fi

    # Settings and driver state of an install from before the rename.
    migrate_legacy_config

    sudo mkdir -p "$INSTALL_DIR_PATH/layouts" "$INSTALL_DIR_PATH/config" "$INSTALL_DIR_PATH/config_app" "$INSTALL_DIR_PATH/desktop" "$INSTALL_DIR_PATH/overlay" "$INSTALL_DIR_PATH/gnome/extension"
    sudo install dialpad.py "$INSTALL_DIR_PATH"
    sudo install dialpad_dbus.py "$INSTALL_DIR_PATH"
    sudo install dial_gesture.py "$INSTALL_DIR_PATH"
    sudo install -m 644 backlight.py launch.py layout_detect.py laptop_touchpad_dialpad_layouts.csv "$INSTALL_DIR_PATH"
    sudo install -t "$INSTALL_DIR_PATH/layouts" layouts/*.py
    sudo install -m 644 -t "$INSTALL_DIR_PATH/config" config/*.py
    sudo install -m 644 -t "$INSTALL_DIR_PATH/desktop" desktop/*.py
    sudo install -m 644 -t "$INSTALL_DIR_PATH/overlay" overlay/*.py
    sudo install -m 755 config_app/main.py "$INSTALL_DIR_PATH/config_app/main.py"
    sudo install -m 644 config_app/__init__.py config_app/outline_editor.py config_app/icon.svg config_app/style.css "config_app/$APP_ID.desktop" "$INSTALL_DIR_PATH/config_app/"
    sudo install -m 644 gnome/extension/extension.js gnome/extension/dial.js gnome/extension/layers.js gnome/extension/skins.json gnome/extension/metadata.json gnome/extension/stylesheet.css "$INSTALL_DIR_PATH/gnome/extension/"

    mkdir -p "$(dirname "$LAUNCHER_PATH")" "$(dirname "$ICON_PATH")"
    sed "s|@INSTALL_DIR@|$INSTALL_DIR_PATH|g" "config_app/$APP_ID.desktop" > "$LAUNCHER_PATH"
    install -m 644 config_app/icon.svg "$ICON_PATH"

    if [[ -f "$CONFIG_FILE_PATH" ]]; then
        if ask "In system remains config file from previous installation. Do you want replace that config with default config?" n; then
            # default will be autocreated, that is why is removed
            rm -f "$CONFIG_FILE_PATH"
            if [[ $? != 0 ]]; then
                echo "$CONFIG_FILE_PATH cannot be removed correctly..."
                exit 1
            fi
        fi
    else
        echo "Default config will be autocreated during the first run and available for futher modifications here:"
        echo "$CONFIG_FILE_PATH"
    fi

    echo

    PYTHON=$(command -v python3)
    if [ -z "$PYTHON" ]; then
        echo "Python3 not found in PATH."
        exit 1
    fi

    # xcffib (https://pypi.org/project/xcffib/) requires python >=3.10
    if ! $PYTHON -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"; then
        PYTHON_VERSION=$($PYTHON -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
        echo "Python >= 3.10 is required (found $PYTHON_VERSION)."
        echo "Please install Python 3.10 or higher before continuing."
        exit 1
    fi

    # openSUSE compatibility
    # https://github.com/asus-linux-drivers/asus-numberpad-driver/issues/296
    if [ ! -f /usr/include/xkbcommon/xkbcommon.h ] && [ -f /usr/include/libxkbcommon/xkbcommon/xkbcommon.h ]; then
        sudo ln -s /usr/include/libxkbcommon/xkbcommon /usr/include/xkbcommon
    fi
    if [ ! -f /usr/include/wayland-client-core.h ] && [ -f /usr/include/wayland/wayland-client-core.h ]; then
        sudo ln -sf /usr/include/wayland/* /usr/include/
    fi

    # create Python virtual environment (owned by root like the program)
    # System site packages bring distribution-only modules such as pyatspi.
    sudo virtualenv --python="$PYTHON" --system-site-packages "$INSTALL_DIR_PATH/.env"
    venv_pip install --upgrade pip
    venv_pip install --upgrade setuptools

    # https://github.com/asus-linux-drivers/asus-dialpad-driver/issues/43
    # https://github.com/sde1000/python-xkbcommon/issues/26
    constraints=()
    if pkg-config --exists xkbcommon && ! pkg-config --atleast-version=1.5 xkbcommon; then
        constraints+=("xkbcommon<1.1")
    fi

    # Ubuntu 22.04 and other systems with only gobject-introspection-1.0
    if ! pkg-config --exists girepository-2.0; then
        constraints+=("PyGObject<3.52")
    fi

    if [ ${#constraints[@]} -gt 0 ]; then
        # A file, not <(...): sudo closes the descriptor of a substitution.
        CONSTRAINTS_FILE=$(mktemp)
        printf '%s\n' "${constraints[@]}" > "$CONSTRAINTS_FILE"
        venv_pip install -r requirements.txt -c "$CONSTRAINTS_FILE" || PIP_FAILED=1
        rm -f "$CONSTRAINTS_FILE"
    else
        venv_pip install -r requirements.txt || PIP_FAILED=1
    fi

    if [ "$XDG_SESSION_TYPE" == "x11" ]; then
        venv_pip install -r requirements.x11.txt || PIP_FAILED=1
    fi

    if [ "$XDG_SESSION_TYPE" == "wayland" ]; then
        venv_pip install -r requirements.wayland.txt || PIP_FAILED=1
    fi

    if [ -n "$PIP_FAILED" ]; then
        echo
        echo "Error: installing the Python libraries failed (see the pip output above)."
        echo "Usually a development package is missing; please create an issue with this log: https://github.com/sinu0/asus-turnpad/issues"
        exit 1
    fi

    # The program directory is read-only for the user, so compile it once.
    sudo "$INSTALL_DIR_PATH/.env/bin/python3" -m compileall -q -x '/\.env/' "$INSTALL_DIR_PATH"

    echo

    if [ -z "$LAYOUT_NAME" ]; then

      source install_layout_auto_suggestion.sh

      echo

      if [ -z "$LAYOUT_NAME" ] && [ "$INTERACTIVE" != "1" ]; then
        LAYOUT_NAME="proartp16"
        echo "No known layout for this laptop; using $LAYOUT_NAME."
        echo "Run Calibration -> Guided calibration in the Turnpad app after installing."
      fi

      if [ -z "$LAYOUT_NAME" ]; then

        source install_layout_select.sh

        echo
      fi
    fi

    source install_coactivator_select.sh

    echo

    source install_user_interface.sh

    echo

    # The old services, extension and files go just before the new ones start.
    remove_legacy_install

    echo

    source install_service.sh

    echo

    source install_overlay.sh

    echo

    # The settings app uses Adw.ViewSwitcherSidebar (Libadwaita 1.9, GNOME 50).
    if ! python3 -c 'import gi, sys; gi.require_version("Adw", "1"); from gi.repository import Adw; sys.exit(0 if hasattr(Adw, "ViewSwitcherSidebar") else 1)' 2>/dev/null; then
        echo "WARNING: the Turnpad settings app needs Libadwaita 1.9 or newer (GNOME 50 or newer); it will not start on this system."
        echo "The driver works; its settings are then kept in $CONFIG_FILE_DIR_PATH/config.json."
        echo
    fi

    echo "Installation finished successfully"
    echo
    echo "Next steps:"
    echo "  1. Log out and back in (new user groups and the GNOME extension load at login)."
    echo "  2. Hold the illuminated corner icon of the touchpad to switch the DialPad on."
    echo "  3. Open \"Turnpad\" from the applications menu to set up functions;"
    echo "     on a laptop that is not listed, run Calibration -> Guided calibration."

    echo

    if [ "$INTERACTIVE" = "1" ] && ask "Reboot now instead of logging out?" n; then
        sudo /sbin/reboot
    fi

    echo

    exit 0
} 2>&1 | sudo tee "$LOGS_INSTALL_LOG_FILE_PATH"
