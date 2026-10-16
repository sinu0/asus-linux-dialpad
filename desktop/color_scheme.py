"""The desktop's light/dark preference, on any desktop.

Reads org.freedesktop.appearance color-scheme from the XDG desktop portal
(GNOME, KDE, COSMIC, wlroots desktops with xdg-desktop-portal-gtk…) and
falls back to GNOME's gsettings when no portal answers. The GNOME Shell
extension has its own copy using gsettings, as it runs inside the Shell.
"""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PORTAL_INTERFACE = "org.freedesktop.portal.Settings"
NAMESPACE = "org.freedesktop.appearance"
KEY = "color-scheme"
GNOME_SCHEMA = "org.gnome.desktop.interface"

# Portal values: 0 no preference, 1 prefer dark, 2 prefer light.
PREFER_DARK = 1


class ColorScheme:
    """prefers_dark() now, and on_changed callbacks when it flips."""

    def __init__(self):
        self._bus = None
        self._portal_value = None
        self._gsettings = None
        self._callbacks: list[Callable[[], None]] = []
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            reply = self._bus.call_sync(
                PORTAL_NAME, PORTAL_PATH, PORTAL_INTERFACE, "ReadOne",
                GLib.Variant("(ss)", (NAMESPACE, KEY)), GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, 1000, None,
            )
            self._portal_value = int(reply.unpack()[0])
            self._bus.signal_subscribe(
                PORTAL_NAME, PORTAL_INTERFACE, "SettingChanged", PORTAL_PATH, None,
                Gio.DBusSignalFlags.NONE, self._on_portal_changed,
            )
        except (GLib.Error, TypeError, ValueError):
            self._portal_value = None
            self._watch_gsettings()

    def prefers_dark(self) -> bool:
        if self._portal_value is not None:
            return self._portal_value == PREFER_DARK
        if self._gsettings is not None:
            return self._gsettings.get_string(KEY) == "prefer-dark"
        return False

    def on_changed(self, callback: Callable[[], None]) -> None:
        self._callbacks.append(callback)

    def _notify(self):
        for callback in self._callbacks:
            callback()

    def _on_portal_changed(self, _connection, _sender, _path, _interface, _signal, parameters):
        namespace, key, value = parameters.unpack()
        if namespace == NAMESPACE and key == KEY:
            self._portal_value = int(value)
            self._notify()

    def _watch_gsettings(self):
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup(GNOME_SCHEMA, True) is None:
            return
        self._gsettings = Gio.Settings.new(GNOME_SCHEMA)
        self._gsettings.connect(f"changed::{KEY}", lambda *_args: self._notify())
