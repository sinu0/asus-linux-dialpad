"""Names and identifiers of the project, in one place.

The display name is free to change. The technical identifiers below are a
contract between separately installed parts (driver, settings app, Shell
extension, installer) and with existing user configuration; changing one
means changing its twin outside Python too. tests/test_identity.py checks
every twin, so a rename that misses one fails the tests.
"""

# Shown to people: window titles, launcher, installer messages.
APP_NAME = "Turnpad"
APP_SUMMARY = "Touchpad dial for ASUS laptops with a DialPad"

# Settings app (GApplication id, launcher and icon name).
# Twins: config_app/<APP_ID>.desktop, install.sh, uninstall.sh.
APP_ID = "io.github.asuslinuxdrivers.DialPadControl"

# Session D-Bus service of the driver.
# Twins: BUS_NAME/BUS_PATH in gnome/extension/extension.js.
DBUS_NAME = "io.github.asuslinuxdrivers.DialPad"
DBUS_PATH = "/io/github/asuslinuxdrivers/DialPad"
DBUS_INTERFACE = DBUS_NAME

# Directory under ~/.config with config.json and skins/.
# Twin: CONFIG_DIR in gnome/extension/extension.js.
CONFIG_DIR_NAME = "asus-dialpad"

# Twins: uuid in gnome/extension/metadata.json, install_gnome_extension.sh.
GNOME_EXTENSION_UUID = "dialpad@asus-linux-drivers"

# Twins: INSTALL_DIR_PATH defaults in the install_*.sh scripts.
INSTALL_DIR = "/usr/share/asus-dialpad-driver"
