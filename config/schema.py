from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path

from config.identity import CONFIG_DIR_NAME

CONFIG_DIR = Path.home() / ".config" / CONFIG_DIR_NAME

CONFIG_FILE = CONFIG_DIR / "config.json"
DARKTABLE_APP_ID = "org.darktable.darktable.desktop"


PROFILE_MODES = ("multi", "single")
OVERLAY_POSITIONS = ("center", "lower", "bottom", "top")
SCROLL_AXES = ("vertical", "horizontal")


class StepType(str, Enum):
    KEYSTROKE = "keystroke"
    SCROLL = "scroll"
    MEDIA = "media"
    BRIGHTNESS = "brightness"
    VOLUME = "volume"
    DELAY = "delay"
    COMMAND = "command"
    SHELL = "shell"


@dataclass
class TouchGeometry:
    width: int
    height: int
    circle_diameter: int
    center_button_diameter: int
    center_x: int
    center_y: int


@dataclass
class ActivationConfig:
    activation_time: float = 1.0
    coactivator_keys: list[str] = field(default_factory=list)


@dataclass
class GestureConfig:
    default_threshold: int = 90
    slices_minimum_count: int = 4
    hysteresis: int = 5
    disable_inactivity_time: int = 120
    # Holding the centre this long inside a function returns to the menu;
    # a shorter tap runs the function's own centre action.
    center_hold_time: float = 0.5


@dataclass
class OverlayConfig:
    """Appearance of the GNOME Shell dial; read directly by the extension."""

    scale: float = 1.0
    position: str = "lower"
    hide_delay_ms: int = 1500
    show_hints: bool = True
    show_pointer: bool = True
    accent: str = "#e7b98d"
    # Built-in skin id (gnome/extension/skins.json) or the name of a file
    # in ~/.config/asus-dialpad/skins/ without ".json".
    skin: str = "glass"
    # With follow_system_style the dial uses skin_light while GNOME is in
    # light style and skin in dark style.
    skin_light: str = "frost"
    follow_system_style: bool = False
    # Functions whose rotation step is at least this many degrees show a
    # progress arc while turning instead of waiting silently.
    progress_above_degrees: int = 120


@dataclass
class MacroStep:
    type: StepType
    keys: list[str] | None = None
    value: int | None = None
    direction: str | None = None
    duration: float | None = None
    program: str | None = None
    args: list[str] | None = None
    script: str | None = None
    title: str | None = None
    # Scroll only: keys held while the wheel turns (Ctrl gives zoom) and
    # the wheel axis.
    modifiers: list[str] | None = None
    axis: str | None = None


@dataclass
class Segment:
    title: str
    icon_url: str | None = None
    treshold: int | None = None
    macro_cw: list[MacroStep] = field(default_factory=list)
    macro_ccw: list[MacroStep] = field(default_factory=list)
    macro_center: list[MacroStep] = field(default_factory=list)
    value_command: str | None = None
    unit: str | None = None
    enabled: bool = True
    color: str | None = None


@dataclass
class Profile:
    name: str
    app_id: str | None = None
    segments: list[Segment] = field(default_factory=list)
    # ASUS Dial offers a single-function mode (the dial always controls one
    # function) and a multi-function mode with the radial menu.
    mode: str = "multi"
    single_function: str | None = None
    sensitivity: float = 1.0
    scroll_speed: float = 1.0
    remember_last: bool = True

    def active_segments(self) -> list[Segment]:
        return [segment for segment in self.segments if segment.enabled]

    def single_segment(self) -> Segment | None:
        segments = self.active_segments()
        for segment in segments:
            if segment.title == self.single_function:
                return segment
        return segments[0] if segments else None


@dataclass
class DialPadConfig:
    version: int = 2
    device_name: str = ""
    geometry: TouchGeometry = field(default_factory=lambda: TouchGeometry(
        width=250,
        height=250,
        circle_diameter=919,
        center_button_diameter=364,
        center_x=586,
        center_y=573,
    ))
    activation: ActivationConfig = field(default_factory=ActivationConfig)
    gesture: GestureConfig = field(default_factory=GestureConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    profiles: list[Profile] = field(default_factory=list)


def _default_segments() -> list[Segment]:
    from config.presets import default_segments

    return default_segments()


def darktable_colour_labels_segment() -> Segment:
    """Optional Darktable colour-label control for the profile editor."""
    return Segment(
        title="Colour label",
        macro_cw=[
            MacroStep(type=StepType.KEYSTROKE, keys=["KEY_F3"], title="Green label"),
        ],
        macro_ccw=[
            MacroStep(type=StepType.KEYSTROKE, keys=["KEY_F1"], title="Red label"),
        ],
        macro_center=[
            MacroStep(type=StepType.KEYSTROKE, keys=["KEY_F2"], title="Yellow label"),
        ],
    )


def darktable_profile() -> Profile:
    """Return the darktable profile from the pre-programmed packs."""
    from config.presets import darktable_profile_segments

    return Profile(name="Darktable", app_id=DARKTABLE_APP_ID, segments=darktable_profile_segments())


def _default_config() -> DialPadConfig:
    return DialPadConfig(
        device_name="",
        profiles=[
            Profile(
                name="Default",
                app_id=None,
                segments=_default_segments(),
            ),
            darktable_profile(),
        ],
    )


def _clamp(value, minimum, maximum, default):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def _encoder(obj):
    if isinstance(obj, DialPadConfig):
        return {
            "version": obj.version,
            "device_name": obj.device_name,
            "geometry": _encoder(obj.geometry),
            "activation": _encoder(obj.activation),
            "gesture": _encoder(obj.gesture),
            "overlay": _encoder(obj.overlay),
            "profiles": [_encoder(p) for p in obj.profiles],
        }
    if isinstance(obj, (TouchGeometry, ActivationConfig, GestureConfig, OverlayConfig)):
        return {item.name: getattr(obj, item.name) for item in fields(obj)}
    if isinstance(obj, Profile):
        result: dict = {
            "name": obj.name,
            "segments": [_encoder(s) for s in obj.segments],
        }
        if obj.app_id is not None:
            result["app_id"] = obj.app_id
        result["mode"] = obj.mode
        if obj.single_function:
            result["single_function"] = obj.single_function
        result["sensitivity"] = obj.sensitivity
        result["scroll_speed"] = obj.scroll_speed
        result["remember_last"] = obj.remember_last
        return result
    if isinstance(obj, Segment):
        result: dict = {
            "title": obj.title,
            "macro_cw": [_encoder(m) for m in obj.macro_cw],
            "macro_ccw": [_encoder(m) for m in obj.macro_ccw],
        }
        if obj.icon_url is not None:
            result["icon_url"] = obj.icon_url
        if obj.treshold is not None:
            result["treshold"] = obj.treshold
        if obj.macro_center:
            result["macro_center"] = [_encoder(m) for m in obj.macro_center]
        if obj.value_command is not None:
            result["value_command"] = obj.value_command
        if obj.unit is not None:
            result["unit"] = obj.unit
        if not obj.enabled:
            result["enabled"] = False
        if obj.color:
            result["color"] = obj.color
        return result
    if isinstance(obj, MacroStep):
        result: dict = {"type": obj.type.value}
        for attr in (
            "keys", "value", "direction", "duration", "program", "args",
            "script", "title", "modifiers", "axis",
        ):
            val = getattr(obj, attr)
            if val is not None:
                result[attr] = val
        return result
    raise TypeError(f"Unserializable object: {type(obj)}")


def _known(d: dict, cls: type) -> dict:
    names = {item.name for item in fields(cls)}
    return {key: value for key, value in d.items() if key in names}


def _decoder(d: dict, cls: type):
    if cls is DialPadConfig:
        return DialPadConfig(
            version=d.get("version", 2),
            device_name=d.get("device_name", ""),
            geometry=_decoder(d["geometry"], TouchGeometry),
            activation=_decoder(d.get("activation", {}), ActivationConfig),
            gesture=_decoder(d.get("gesture", {}), GestureConfig),
            overlay=_decoder(d.get("overlay", {}), OverlayConfig),
            profiles=[_decoder(p, Profile) for p in d.get("profiles", [])],
        )
    if cls is TouchGeometry:
        return TouchGeometry(**_known(d, TouchGeometry))
    if cls is ActivationConfig:
        return ActivationConfig(**_known(d, ActivationConfig))
    if cls is GestureConfig:
        return GestureConfig(**_known(d, GestureConfig))
    if cls is OverlayConfig:
        overlay = OverlayConfig(**_known(d, OverlayConfig))
        overlay.scale = _clamp(overlay.scale, 0.6, 1.6, 1.0)
        if overlay.position not in OVERLAY_POSITIONS:
            overlay.position = "lower"
        if not isinstance(overlay.skin, str) or not overlay.skin.strip():
            overlay.skin = "glass"
        if not isinstance(overlay.skin_light, str) or not overlay.skin_light.strip():
            overlay.skin_light = "frost"
        overlay.follow_system_style = bool(overlay.follow_system_style)
        return overlay
    if cls is Profile:
        mode = d.get("mode", "multi")
        return Profile(
            name=d["name"],
            app_id=d.get("app_id"),
            segments=[_decoder(s, Segment) for s in d.get("segments", [])],
            mode=mode if mode in PROFILE_MODES else "multi",
            single_function=d.get("single_function"),
            sensitivity=_clamp(d.get("sensitivity", 1.0), 0.25, 4.0, 1.0),
            scroll_speed=_clamp(d.get("scroll_speed", 1.0), 0.25, 4.0, 1.0),
            remember_last=bool(d.get("remember_last", True)),
        )
    if cls is Segment:
        return Segment(
            title=d["title"],
            icon_url=d.get("icon_url"),
            treshold=d.get("treshold"),
            macro_cw=[_decoder(m, MacroStep) for m in d.get("macro_cw", [])],
            macro_ccw=[_decoder(m, MacroStep) for m in d.get("macro_ccw", [])],
            macro_center=[_decoder(m, MacroStep) for m in d.get("macro_center", [])],
            value_command=d.get("value_command"),
            unit=d.get("unit"),
            enabled=bool(d.get("enabled", True)),
            color=d.get("color"),
        )
    if cls is MacroStep:
        values = _known(d, MacroStep)
        values["type"] = StepType(d["type"])
        return MacroStep(**values)
    raise TypeError(f"Unknown class: {cls}")


def load_config() -> DialPadConfig:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        cfg = _default_config()
        save_config(cfg)
        return cfg

    with open(CONFIG_FILE) as f:
        data = json.load(f)

    return _decoder(data, DialPadConfig)


def save_config(cfg: DialPadConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Write atomically: the driver and the Shell extension watch this file
    # and must never read a half-written document.
    temporary = CONFIG_FILE.with_suffix(".json.tmp")
    with open(temporary, "w") as f:
        json.dump(_encoder(cfg), f, indent=2)
        f.write("\n")
    temporary.replace(CONFIG_FILE)
