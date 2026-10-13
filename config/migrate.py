from __future__ import annotations

import configparser
import importlib
import json
import os
from pathlib import Path

from config.schema import (
    ActivationConfig,
    DialPadConfig,
    GestureConfig,
    MacroStep,
    Profile,
    Segment,
    StepType,
    TouchGeometry,
    load_config,
    save_config,
)

_KEY_TYPE_EV_KEY = 1
_KEY_TYPE_EV_REL = 2
_EV_REL_WHEEL = 8
_EV_REL_WHEEL_HI_RES = 11

_DESKTOP_ID_MAP: dict[str, str] = {
    "darktable": "org.darktable.darktable.desktop",
    "firefox": "firefox.desktop",
    "code": "code.desktop",
    "/usr/share/code/code": "code.desktop",
    "gedit": "org.gnome.gedit.desktop",
    "nautilus": "org.gnome.Nautilus.desktop",
    "gimp": "org.gimp.GIMP.desktop",
    "inkscape": "org.inkscape.Inkscape.desktop",
    "blender": "org.blender.Blender.desktop",
    "vlc": "org.videolan.VLC.desktop",
    "evince": "org.gnome.Evince.desktop",
    "chromium": "chromium-browser.desktop",
    "chrome": "google-chrome.desktop",
    "libreoffice": "libreoffice-startcenter.desktop",
    "terminal": "org.gnome.Terminal.desktop",
    "konsole": "org.kde.konsole.desktop",
    "thunderbird": "thunderbird.desktop",
}


def _resolve_app_id(key: str) -> str | None:
    if key in _DESKTOP_ID_MAP:
        return _DESKTOP_ID_MAP[key]
    for known, desktop in _DESKTOP_ID_MAP.items():
        if known in key.lower():
            return desktop
    if "/" in key and not key.endswith(".desktop"):
        return None
    if key.endswith(".desktop"):
        return key
    return None


def _to_key_str(k) -> str:
    if isinstance(k, int):
        return str(k)
    return str(int(k))


def _to_key_int(k) -> int:
    if isinstance(k, int):
        return k
    return int(k)


def _key_is_rel(k) -> bool:
    v = _to_key_int(k)
    return 8 <= v <= 11


def _key_type(key):
    if isinstance(key, list):
        if any(_key_is_rel(k) for k in key):
            return _KEY_TYPE_EV_REL
        return _KEY_TYPE_EV_KEY
    return _KEY_TYPE_EV_KEY


def _build_macro(old_entry: dict) -> MacroStep | None:
    key = old_entry.get("key")
    keys: list[str] | None = None
    macro_type: StepType = StepType.KEYSTROKE

    if key is not None:
        ktype = _key_type(key)
        if ktype == _KEY_TYPE_EV_REL:
            macro_type = StepType.SCROLL
            keys = [_to_key_str(k) for k in key]
        elif isinstance(key, list):
            keys = [_to_key_str(k) for k in key]
            macro_type = StepType.KEYSTROKE
        else:
            key_int = _to_key_int(key)
            keys = [str(key_int)]
            if key_int == 115:
                macro_type = StepType.VOLUME
            elif key_int == 114:
                macro_type = StepType.VOLUME
            elif key_int == 225:
                macro_type = StepType.BRIGHTNESS
            elif key_int == 224:
                macro_type = StepType.BRIGHTNESS
            elif key_int in (113, 128, 208, 173, 165, 163, 161, 164, 162, 171, 172, 168, 169, 207):
                macro_type = StepType.MEDIA
            else:
                macro_type = StepType.KEYSTROKE

    command = old_entry.get("command")
    if command:
        macro_type = StepType.SHELL
        keys = None

    # In the legacy layout ``modifier`` constrained the *physical input*
    # which could trigger an action.  A radial segment is selected directly,
    # so there is no equivalent input gate.  In particular, emitting the old
    # modifier as part of the output turned a normal media action such as
    # Mute into an incorrect Shift+Mute chord.

    duration = old_entry.get("duration")

    value = old_entry.get("value")
    macro_value: int | None = None
    direction: str | None = None
    if macro_type is StepType.SCROLL and isinstance(value, list) and value:
        try:
            direction = "clockwise" if int(value[0]) >= 0 else "counterclockwise"
            macro_value = abs(int(value[1] if len(value) > 1 else value[0]))
        except (TypeError, ValueError):
            pass
    elif isinstance(value, int):
        macro_value = value
    elif isinstance(value, list) and value:
        try:
            macro_value = int(value[0])
        except (TypeError, ValueError):
            macro_value = None

    return MacroStep(
        type=macro_type,
        keys=keys,
        value=macro_value,
        direction=direction,
        duration=float(duration) if duration is not None else None,
        script=command,
    )


def _parse_old_segment(title: str, seg_data: dict) -> Segment:
    seg = Segment(title=title)

    seg.icon_url = seg_data.get("icon")
    seg.treshold = seg_data.get("treshold")

    val = seg_data.get("value")
    if isinstance(val, str):
        seg.value_command = val
    seg.unit = seg_data.get("unit")

    for old_entry in seg_data.get("clockwise", []):
        m = _build_macro(old_entry)
        if m:
            seg.macro_cw.append(m)

    for old_entry in seg_data.get("counterclockwise", []):
        m = _build_macro(old_entry)
        if m:
            seg.macro_ccw.append(m)

    for old_entry in seg_data.get("center", []):
        if isinstance(old_entry, dict):
            m = _build_macro(old_entry)
            if m:
                seg.macro_center.append(m)

    seg_command = seg_data.get("command")
    if isinstance(seg_command, str):
        seg.macro_center.append(MacroStep(
            type=StepType.SHELL,
            script=seg_command,
        ))

    return seg


def _parse_old_app_config(app_config: dict, app_id: str | None) -> Profile:
    multi_title = None
    for k in app_config:
        if k not in ("center", "clockwise", "counterclockwise"):
            multi_title = app_config
            break

    if multi_title:
        profile_name = "Default"
        if app_id:
            profile_name = app_id.removesuffix(".desktop").replace("-", " ").replace(".", " ").title()

        segments: list[Segment] = []
        for key, value in app_config.items():
            if key in ("center", "clockwise", "counterclockwise"):
                continue
            if isinstance(value, dict):
                segments.append(_parse_old_segment(key, value))

        return Profile(name=profile_name, app_id=app_id, segments=segments)

    profile_name = "Default"
    if app_id:
        profile_name = app_id.removesuffix(".desktop").replace("-", " ").replace(".", " ").title()

    segments: list[Segment] = []

    titled_entries: dict[str, dict] = {}

    rotation_directions = {
        "clockwise": "macro_cw",
        "counterclockwise": "macro_ccw",
    }

    for direction, macro_attr in rotation_directions.items():
        entries = app_config.get(direction, [])
        if not isinstance(entries, list):
            entries = [entries]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_title = entry.get("title")
            if entry_title:
                if entry_title not in titled_entries:
                    titled_entries[entry_title] = {}
                titled_entries[entry_title].setdefault(direction, []).append(entry)
            else:
                if not segments:
                    segments.append(Segment(title=profile_name))
                m = _build_macro(entry)
                if m:
                    getattr(segments[0], macro_attr).append(m)

    for title, dirs in titled_entries.items():
        seg = Segment(title=title)
        for cw_entry in dirs.get("clockwise", []):
            cw_entry_no_title = {k: v for k, v in cw_entry.items() if k != "title"}
            m = _build_macro(cw_entry_no_title)
            if m:
                seg.macro_cw.append(m)
            if seg.value_command is None:
                val = cw_entry.get("value")
                if isinstance(val, str):
                    seg.value_command = val
            if seg.unit is None:
                seg.unit = cw_entry.get("unit")
        for ccw_entry in dirs.get("counterclockwise", []):
            ccw_entry_no_title = {k: v for k, v in ccw_entry.items() if k != "title"}
            m = _build_macro(ccw_entry_no_title)
            if m:
                seg.macro_ccw.append(m)
            if seg.value_command is None:
                val = ccw_entry.get("value")
                if isinstance(val, str):
                    seg.value_command = val
            if seg.unit is None:
                seg.unit = ccw_entry.get("unit")
        segments.append(seg)

    center_macros = []
    for center_entry in app_config.get("center", []):
        if not isinstance(center_entry, dict):
            continue
        m = _build_macro(center_entry)
        if m:
            center_macros.append(m)

    if center_macros:
        if titled_entries:
            # In a radial menu the centre is used to enter/leave a selected
            # segment. Do not attach an old global centre shortcut to the
            # first segment, otherwise that segment can never be selected.
            segments.append(Segment(title="Center", macro_center=center_macros))
        else:
            if not segments:
                segments.append(Segment(title=profile_name))
            segments[0].macro_center.extend(center_macros)

    return Profile(name=profile_name, app_id=app_id, segments=segments)


def migrate_old_format(
    layout_name: str = "",
    config_dir: str = "",
    layouts_path: str = "",
) -> DialPadConfig:
    geometry = TouchGeometry(
        width=250,
        height=250,
        circle_diameter=919,
        center_button_diameter=364,
        center_x=586,
        center_y=573,
    )

    activation = ActivationConfig()
    gesture = GestureConfig()
    profiles: list[Profile] = []

    if layout_name:
        try:
            mod = importlib.import_module(f"layouts.{layout_name}")
        except ModuleNotFoundError:
            if layouts_path:
                import sys
                sys.path.insert(0, layouts_path)
                mod = importlib.import_module(f"layouts.{layout_name}")
            else:
                mod = None
    else:
        mod = None

    if mod is not None:
        geometry = TouchGeometry(
            width=getattr(mod, "top_right_icon_width", 250),
            height=getattr(mod, "top_right_icon_height", 250),
            circle_diameter=getattr(mod, "circle_diameter", 919),
            center_button_diameter=getattr(mod, "center_button_diameter", 364),
            center_x=getattr(mod, "circle_center_x", 586),
            center_y=getattr(mod, "circle_center_y", 573),
        )

        app_shortcuts = getattr(mod, "app_shortcuts", {})
        for app_key, app_config in app_shortcuts.items():
            if not isinstance(app_config, dict):
                continue
            if app_key == "none":
                profile = _parse_old_app_config(app_config, None)
            else:
                app_id = _resolve_app_id(app_key)
                profile = _parse_old_app_config(app_config, app_id)
            profiles.append(profile)

    if config_dir:
        ini_path = os.path.join(config_dir, "dialpad_dev")
    else:
        ini_path = "dialpad_dev"

    if os.path.isfile(ini_path):
        parser = configparser.ConfigParser()
        parser.read(ini_path)

        section = "main"
        if parser.has_section(section):

            def _get(key, default):
                try:
                    return parser.get(section, key)
                except (configparser.NoSectionError, configparser.NoOptionError):
                    return default

            raw_time = _get("activation_time", "")
            if raw_time:
                try:
                    activation.activation_time = float(raw_time)
                except ValueError:
                    pass

            raw_co = _get("top_right_icon_coactivator_key", "")
            if raw_co:
                activation.coactivator_keys = raw_co.strip().split()

            raw_thresh = _get("default_treshold", "")
            if raw_thresh:
                try:
                    gesture.default_threshold = int(raw_thresh)
                except ValueError:
                    pass

            raw_slices = _get("slices_minimum_count", "")
            if raw_slices:
                try:
                    gesture.slices_minimum_count = int(raw_slices)
                except ValueError:
                    pass

            raw_inactivity = _get("disable_due_inactivity_time", "")
            if raw_inactivity:
                try:
                    gesture.disable_inactivity_time = int(raw_inactivity)
                except ValueError:
                    pass

    cfg = DialPadConfig(
        device_name=layout_name or "",
        geometry=geometry,
        activation=activation,
        gesture=gesture,
        profiles=profiles,
    )

    save_config(cfg)
    return cfg
