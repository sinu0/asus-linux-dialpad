"""Brightness of the DialPad light, optionally following the keyboard's.

While the DialPad is on, its light takes eight levels, sent like the on/off
commands as values 0x41 (dimmest) to 0x48 (brightest). Level 0 switches the
light off while the dial keeps working: the light is only a display, the
driver reads the touches itself.

KeyboardBacklight reads the keyboard backlight from UPower on the system bus
and reports changes, so the keyboard brightness key dims, brightens or
switches off the DialPad light too.
"""

from __future__ import annotations

import logging
from typing import Callable

from config.identity import SLUG

log = logging.getLogger(SLUG)

LEVELS = 8
_FIRST_LEVEL_VALUE = 0x41
_LIGHT_ON = "0x01"
_LIGHT_OFF = "0x00"

UPOWER_NAME = "org.freedesktop.UPower"
UPOWER_PATH = "/org/freedesktop/UPower/KbdBacklight"
UPOWER_INTERFACE = "org.freedesktop.UPower.KbdBacklight"


def commands_for_level(level: int) -> list[str]:
    """Touchpad commands for a level from 0 (off) to LEVELS.

    A level above 0 first switches the light on, so it also works after 0.
    """
    level = max(0, min(LEVELS, int(level)))
    if level == 0:
        return [_LIGHT_OFF]
    return [_LIGHT_ON, f"0x{_FIRST_LEVEL_VALUE + level - 1:02x}"]


def level_for_keyboard(value: int, maximum: int) -> int:
    """Keyboard light off is DialPad light off; its other levels (often 1-3)
    spread over the DialPad's 1-LEVELS."""
    if maximum <= 0:
        return LEVELS
    if value <= 0:
        return 0
    # A keyboard light that is only on or off means full brightness.
    fraction = 1.0 if maximum == 1 else min(1.0, (value - 1) / (maximum - 1))
    return 1 + round(fraction * (LEVELS - 1))


class KeyboardBacklight:
    """The keyboard backlight as seen by UPower; level() is None without one.

    on_change(level) runs in the GLib main loop of the process (the D-Bus
    service thread of the driver) whenever the keyboard brightness changes.
    """

    def __init__(self, on_change: Callable[[int], None] | None = None):
        self._bus = None
        self._value: int | None = None
        self._maximum: int | None = None
        try:
            from gi.repository import Gio

            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self._maximum = self._call("GetMaxBrightness")
            self.refresh()
            if on_change is not None and self._maximum:
                self._bus.signal_subscribe(
                    UPOWER_NAME, UPOWER_INTERFACE, None, UPOWER_PATH, None,
                    Gio.DBusSignalFlags.NONE, self._on_signal, on_change,
                )
        except Exception as error:
            log.info("Keyboard backlight not available through UPower: %s", error)
            self._bus = None

    def _call(self, method: str) -> int:
        from gi.repository import Gio

        reply = self._bus.call_sync(
            UPOWER_NAME, UPOWER_PATH, UPOWER_INTERFACE, method,
            None, None, Gio.DBusCallFlags.NONE, 500, None,
        )
        return int(reply.unpack()[0])

    def refresh(self) -> None:
        if self._bus is None:
            return
        try:
            self._value = self._call("GetBrightness")
        except Exception as error:
            log.debug("Reading the keyboard backlight failed: %s", error)

    def level(self) -> int | None:
        if self._value is None or not self._maximum:
            return None
        return level_for_keyboard(self._value, self._maximum)

    def _on_signal(self, _connection, _sender, _path, _interface, signal, parameters, on_change):
        # UPower sends BrightnessChanged and BrightnessChangedWithSource for
        # the same change; react once per new value.
        if signal not in ("BrightnessChanged", "BrightnessChangedWithSource"):
            return
        value = int(parameters.unpack()[0])
        if value == self._value:
            return
        self._value = value
        try:
            on_change(self.level())
        except Exception:
            log.exception("Keyboard backlight callback failed")
