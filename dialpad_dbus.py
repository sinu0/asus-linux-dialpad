#!/usr/bin/env python3
"""Session D-Bus interface for the DialPad driver."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import logging
import math
import threading
import time
from typing import Any

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib


BUS_NAME = "io.github.asuslinuxdrivers.DialPad"
OBJECT_PATH = "/io/github/asuslinuxdrivers/DialPad"
INTERFACE_NAME = BUS_NAME
_STARTUP_TIMEOUT_SECONDS = 2.0
_INT32_MIN = -(2**31)
_INT32_MAX = 2**31 - 1
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1

LOG = logging.getLogger(__name__)


class _DialPadObject(dbus.service.Object):
    """The D-Bus object delegates request handling to its service owner."""

    def __init__(self, service: "DialPadDBusService", bus_name: dbus.service.BusName):
        super().__init__(bus_name, OBJECT_PATH)
        self._service = service

    @dbus.service.signal(INTERFACE_NAME, signature="bsasasidsbbb")
    def OverlayState(
        self,
        enabled: dbus.Boolean,
        title: dbus.String,
        titles: dbus.Array,
        icons: dbus.Array,
        value: dbus.Int32,
        value_angle_start: dbus.Double,
        unit: dbus.String,
        center_pressed: dbus.Boolean,
        value_show_only_progress: dbus.Boolean,
        touching: dbus.Boolean,
    ) -> None:
        pass

    @dbus.service.signal(INTERFACE_NAME, signature="s")
    def OverlayDetails(self, details_json: dbus.String) -> None:
        """Presentation details as JSON: profile, colours, hints, pointer."""

    @dbus.service.signal(INTERFACE_NAME, signature="s")
    def CalibrationProgress(self, state_json: dbus.String) -> None:
        """Guided calibration state as JSON (step, message, error, result…)."""

    @dbus.service.method(INTERFACE_NAME, in_signature="", out_signature="b")
    def CancelCalibration(self) -> dbus.Boolean:
        return dbus.Boolean(
            self._service._call_bool_callback(self._service._on_cancel_calibration, "CancelCalibration")
        )

    @dbus.service.method(INTERFACE_NAME, in_signature="", out_signature="s")
    def GetOverlayDetails(self) -> dbus.String:
        return dbus.String(self._service._details_json())

    @dbus.service.method(INTERFACE_NAME, in_signature="s", out_signature="")
    def SetActiveApplication(self, application: str) -> None:
        self._service._set_active_application(str(application))

    @dbus.service.method(INTERFACE_NAME, in_signature="", out_signature="a{sv}")
    def GetStatus(self) -> dbus.Dictionary:
        return self._service._get_status()

    @dbus.service.method(INTERFACE_NAME, in_signature="", out_signature="b")
    def ReloadConfig(self) -> dbus.Boolean:
        return dbus.Boolean(self._service._reload_config())

    @dbus.service.method(INTERFACE_NAME, in_signature="", out_signature="b")
    def StartCalibration(self) -> dbus.Boolean:
        return dbus.Boolean(self._service._start_calibration())


class DialPadDBusService:
    """Owns the DialPad session service and its private GLib main-loop thread."""

    def __init__(
        self,
        on_active_application: Callable[[str], Any],
        on_reload_config: Callable[[], Any],
        on_start_calibration: Callable[[], Any],
        status_provider: Callable[[], Mapping[str, Any]],
        on_cancel_calibration: Callable[[], Any] | None = None,
    ) -> None:
        self._on_cancel_calibration = on_cancel_calibration
        self._on_active_application = on_active_application
        self._on_reload_config = on_reload_config
        self._on_start_calibration = on_start_calibration
        self._status_provider = status_provider
        self._lock = threading.RLock()
        self._startup_complete = threading.Event()
        self._stop_requested = False
        self._started = False
        self._thread: threading.Thread | None = None
        self._main_loop: GLib.MainLoop | None = None
        self._bus: dbus.bus.BusConnection | None = None
        self._bus_name: dbus.service.BusName | None = None
        self._object: _DialPadObject | None = None
        self._overlay_state: dict[str, Any] = {
            "enabled": False,
            "title": "",
            "titles": [],
            "icons": [],
            "value": 0,
            "value_angle_start": 0.0,
            "unit": "",
            "center_pressed": False,
            "value_show_only_progress": False,
            "touching": False,
        }
        # Extra presentation data kept outside the fixed OverlayState
        # signature so that older Shell extensions keep working.
        self._details: dict[str, Any] = {
            "profile": "",
            "mode": "multi",
            "colors": [],
            "color": "",
            "hints": {},
            "hold_returns": True,
            "pointer": -1,
        }

    def _details_json(self) -> str:
        with self._lock:
            return json.dumps(self._details)

    def start(self) -> bool:
        """Start the D-Bus service without making a session bus mandatory."""
        with self._lock:
            if self._started:
                return True
            if self._thread is not None:
                LOG.warning("DialPad D-Bus service is already starting")
                return False
            if self._stop_requested:
                return False

            self._startup_complete = threading.Event()
            thread = threading.Thread(
                target=self._run_main_loop,
                name="dialpad-dbus",
                daemon=True,
            )
            self._thread = thread

        thread.start()
        if not self._startup_complete.wait(_STARTUP_TIMEOUT_SECONDS):
            LOG.error("Timed out starting the DialPad D-Bus service")
            self.stop()
            return False

        with self._lock:
            return self._started

    def stop(self) -> None:
        """Stop the D-Bus loop and release the session name when possible."""
        with self._lock:
            self._stop_requested = True
            main_loop = self._main_loop
            thread = self._thread

        if main_loop is not None:
            try:
                main_loop.quit()
            except Exception:
                LOG.exception("Failed to stop the DialPad D-Bus main loop")

        if thread is not None and thread is not threading.current_thread():
            thread.join(_STARTUP_TIMEOUT_SECONDS)
            if thread.is_alive():
                LOG.warning("DialPad D-Bus thread did not stop before the timeout")

    def emit_overlay_state(self, payload: dict) -> None:
        """Merge a partial state update and schedule a full OverlayState signal."""
        data: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
        with self._lock:
            state = self._overlay_state
            was_enabled = state["enabled"]

            details = data.get("details")
            details_json = None
            if isinstance(details, Mapping):
                self._details.update(
                    (str(key), value) for key, value in details.items()
                )
                try:
                    details_json = json.dumps(self._details)
                except (TypeError, ValueError):
                    LOG.warning("Dropping non-serialisable overlay details")
                    details_json = None
            # A details-only update (for example the finger pointer) must not
            # re-send the whole overlay state.
            details_only = set(data.keys()) <= {"details", "ts"}

            if "enabled" in data:
                state["enabled"] = self._as_bool(data["enabled"])
            if "title" in data:
                state["title"] = self._as_text(data["title"])
            if "titles" in data:
                state["titles"] = self._as_text_list(data["titles"])
            if "icons" in data:
                state["icons"] = self._as_text_list(data["icons"])
            if "value" in data:
                state["value"] = self._as_int32(data["value"])
            if "value_angle_start" in data:
                state["value_angle_start"] = self._as_float(data["value_angle_start"])
            if "unit" in data:
                state["unit"] = self._as_text(data["unit"])
            if "center_pressed" in data:
                state["center_pressed"] = self._as_bool(data["center_pressed"])
            if "value_show_only_progress" in data:
                state["value_show_only_progress"] = self._as_bool(
                    data["value_show_only_progress"]
                )
            if data.get("input") == "center":
                state["center_pressed"] = self._as_bool(data.get("value"))
            if "touching" in data:
                state["touching"] = self._as_bool(data["touching"])
            # Progress-only mode belongs to the update that asked for it;
            # a menu or function change must not inherit it.
            if (
                ("title" in data or "titles" in data)
                and "value_show_only_progress" not in data
            ):
                state["value_show_only_progress"] = False

            if was_enabled and not state["enabled"]:
                state.update(
                    title="",
                    value=0,
                    value_angle_start=0.0,
                    unit="",
                    center_pressed=False,
                    value_show_only_progress=False,
                    touching=False,
                )

            values = None if details_only else self._normalize_overlay_payload(state)
            dbus_object = self._object if self._started else None

        if dbus_object is None or (values is None and details_json is None):
            return

        try:
            GLib.idle_add(self._emit_overlay_state, dbus_object, values, details_json)
        except Exception:
            LOG.exception("Failed to schedule the DialPad overlay state signal")

    def emit_calibration_progress(self, state: Mapping[str, Any]) -> None:
        with self._lock:
            dbus_object = self._object if self._started else None
        if dbus_object is None:
            return
        try:
            payload = json.dumps(dict(state))
        except (TypeError, ValueError):
            LOG.warning("Dropping non-serialisable calibration state")
            return

        def emit() -> bool:
            try:
                dbus_object.CalibrationProgress(dbus.String(payload))
            except Exception:
                LOG.exception("Failed to emit the calibration progress signal")
            return GLib.SOURCE_REMOVE

        GLib.idle_add(emit)

    def _run_main_loop(self) -> None:
        bus: dbus.bus.BusConnection | None = None
        bus_name: dbus.service.BusName | None = None
        dbus_object: _DialPadObject | None = None
        main_loop: GLib.MainLoop | None = None

        try:
            DBusGMainLoop(set_as_default=True)
            bus = dbus.SessionBus()
            bus_name = dbus.service.BusName(BUS_NAME, bus=bus, do_not_queue=True)
            if bus.get_name_owner(BUS_NAME) != bus.get_unique_name():
                raise RuntimeError("the DialPad D-Bus name is already owned")
            dbus_object = _DialPadObject(self, bus_name)
            main_loop = GLib.MainLoop()

            with self._lock:
                should_run = not self._stop_requested
                if should_run:
                    self._bus = bus
                    self._bus_name = bus_name
                    self._object = dbus_object
                    self._main_loop = main_loop
                    self._started = True
                self._startup_complete.set()

            if should_run:
                main_loop.run()
        except Exception:
            LOG.exception("DialPad D-Bus service is unavailable")
        finally:
            if dbus_object is not None:
                try:
                    dbus_object.remove_from_connection()
                except Exception:
                    LOG.exception("Failed to remove the DialPad D-Bus object")

            if bus is not None:
                try:
                    bus.release_name(BUS_NAME)
                except Exception:
                    LOG.exception("Failed to release the DialPad D-Bus name")

            with self._lock:
                if self._thread is threading.current_thread():
                    self._started = False
                    self._main_loop = None
                    self._object = None
                    self._bus_name = None
                    self._bus = None
                    self._thread = None
                self._startup_complete.set()

    def _emit_overlay_state(
        self,
        dbus_object: _DialPadObject,
        values: tuple[Any, ...] | None,
        details_json: str | None = None,
    ) -> bool:
        with self._lock:
            is_current_object = self._started and self._object is dbus_object

        if not is_current_object:
            return GLib.SOURCE_REMOVE

        try:
            # Details first: the overlay repaints on OverlayState and must
            # already know the colours and hints of the new state.
            if details_json is not None:
                dbus_object.OverlayDetails(dbus.String(details_json))
            if values is not None:
                dbus_object.OverlayState(*values)
        except Exception:
            LOG.exception("Failed to emit the DialPad overlay state signal")
        return GLib.SOURCE_REMOVE

    def _set_active_application(self, application: str) -> None:
        callback = self._on_active_application
        if callback is None:
            return
        try:
            callback(application)
        except Exception:
            LOG.exception("SetActiveApplication callback failed")

    def _reload_config(self) -> bool:
        return self._call_bool_callback(self._on_reload_config, "ReloadConfig")

    def _start_calibration(self) -> bool:
        return self._call_bool_callback(self._on_start_calibration, "StartCalibration")

    def _call_bool_callback(self, callback: Callable[[], Any], name: str) -> bool:
        if callback is None:
            return False
        try:
            return bool(callback())
        except Exception:
            LOG.exception("%s callback failed", name)
            return False

    def _get_status(self) -> dbus.Dictionary:
        provider = self._status_provider
        if provider is None:
            return dbus.Dictionary(signature="sv")

        try:
            status = provider()
        except Exception:
            LOG.exception("GetStatus provider failed")
            return dbus.Dictionary(signature="sv")

        if not isinstance(status, Mapping):
            LOG.warning("GetStatus provider returned a non-mapping value")
            return dbus.Dictionary(signature="sv")

        result: dict[dbus.String, Any] = {}
        for key, value in status.items():
            try:
                key_text = str(key)
            except Exception:
                LOG.warning("GetStatus provider returned a non-stringable key")
                continue

            if isinstance(value, bool):
                result[dbus.String(key_text)] = dbus.Boolean(value)
            elif isinstance(value, str):
                result[dbus.String(key_text)] = dbus.String(value)
            elif isinstance(value, int):
                result[dbus.String(key_text)] = dbus.Int64(
                    max(_INT64_MIN, min(value, _INT64_MAX))
                )
            elif isinstance(value, float) and math.isfinite(value):
                result[dbus.String(key_text)] = dbus.Double(value)

        return dbus.Dictionary(result, signature="sv")

    @staticmethod
    def _normalize_overlay_payload(payload: dict) -> tuple[Any, ...]:
        data: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
        return (
            dbus.Boolean(DialPadDBusService._as_bool(data.get("enabled", False))),
            dbus.String(DialPadDBusService._as_text(data.get("title", ""))),
            dbus.Array(
                [dbus.String(item) for item in DialPadDBusService._as_text_list(data.get("titles", []))],
                signature="s",
            ),
            dbus.Array(
                [dbus.String(item) for item in DialPadDBusService._as_text_list(data.get("icons", []))],
                signature="s",
            ),
            dbus.Int32(DialPadDBusService._as_int32(data.get("value", 0))),
            dbus.Double(DialPadDBusService._as_float(data.get("value_angle_start", 0.0))),
            dbus.String(DialPadDBusService._as_text(data.get("unit", ""))),
            dbus.Boolean(DialPadDBusService._as_bool(data.get("center_pressed", False))),
            dbus.Boolean(
                DialPadDBusService._as_bool(data.get("value_show_only_progress", False))
            ),
            dbus.Boolean(DialPadDBusService._as_bool(data.get("touching", False))),
        )

    @staticmethod
    def _as_bool(value: Any) -> bool:
        return bool(value)

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        try:
            return str(value)
        except Exception:
            return ""

    @staticmethod
    def _as_text_list(value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return [DialPadDBusService._as_text(item) for item in value]

    @staticmethod
    def _as_int32(value: Any) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            return 0
        return max(_INT32_MIN, min(number, _INT32_MAX))

    @staticmethod
    def _as_float(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        return number if math.isfinite(number) else 0.0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = DialPadDBusService(
        on_active_application=lambda _application: None,
        on_reload_config=lambda: True,
        on_start_calibration=lambda: True,
        status_provider=lambda: {"running": True},
    )
    try:
        if service.start():
            service.emit_overlay_state({"enabled": False})
            time.sleep(0.05)
    finally:
        service.stop()
