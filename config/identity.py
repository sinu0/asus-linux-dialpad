"""Names and identifiers of the project, in one place.

The display name is free to change. The technical identifiers below are a
contract between separately installed parts (driver, settings app, Shell
extension, installer) and with existing user configuration; changing one
means changing its twin outside Python too. tests/test_identity.py checks
every twin, so a rename that misses one fails the tests.

Installs from before the rename (asus-dialpad-driver) are moved over by
install_migrate.sh.
"""

# Shown to people: window titles, launcher, installer messages.
APP_NAME = "Turnpad"
APP_SUMMARY = "Touchpad dial for ASUS laptops with a DialPad"
ISSUES_URL = "https://github.com/sinu0/asus-linux-dialpad/issues"

# Technical name: install and config directories, services, log names.
# Twin: install_paths.sh.
SLUG = "asus-turnpad"

# Settings app (GApplication id, launcher and icon name).
# Twins: config_app/<APP_ID>.desktop, install_paths.sh.
APP_ID = "io.github.sinu0.AsusTurnpad"

# Session D-Bus service of the driver.
# Twins: BUS_NAME/BUS_PATH in gnome/extension/extension.js.
DBUS_NAME = "io.github.sinu0.AsusTurnpad.Driver"
DBUS_PATH = "/io/github/sinu0/AsusTurnpad/Driver"
DBUS_INTERFACE = DBUS_NAME

# Directory under ~/.config with config.json, skins/ and the driver state.
# Twins: CONFIG_DIR in gnome/extension/extension.js, install_paths.sh.
CONFIG_DIR_NAME = SLUG

# Twins: uuid in gnome/extension/metadata.json, install_paths.sh.
GNOME_EXTENSION_UUID = "asus-turnpad@sinu0.github.io"

# Twin: install_paths.sh.
INSTALL_DIR = "/opt/asus-turnpad"

# Socket for the legacy PySide overlay, in $XDG_RUNTIME_DIR.
SOCKET_NAME = f"{SLUG}.sock"


def socket_path() -> str:
    import os
    import tempfile

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(runtime_dir, SOCKET_NAME)
