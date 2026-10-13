"""Built-in function library and application packs.

Mirrors the ASUS Dial / ProArt Creator Hub idea: a catalogue of ready
functions that can be dropped into any profile, plus pre-programmed packs
for popular creative and productivity applications.  Every preset is a
plain ``Segment`` and remains fully editable afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from config.schema import MacroStep, Profile, Segment, StepType

VOLUME_QUERY = "pactl get-sink-volume @DEFAULT_SINK@ | grep -oP '\\d+%' | head -n 1 | tr -d '%'"
BRIGHTNESS_QUERY = "brightnessctl -m | cut -d, -f4 | tr -d '%'"
KBD_LIGHT_QUERY = "brightnessctl -d '*kbd_backlight' -m | cut -d, -f4 | tr -d '%'"

COLORS = {
    "audio": "#6cb6ff",
    "light": "#f4c95d",
    "navigate": "#9ad17b",
    "zoom": "#e7b98d",
    "history": "#c99bff",
    "media": "#ff8f8f",
    "tabs": "#7fd4c8",
    "brush": "#ffad66",
    "time": "#8fa8ff",
}


_COLOR_KEYWORDS = (
    (("volume", "mute", "audio"), "audio"),
    (("bright", "light", "exposure"), "light"),
    (("scroll", "arrow", "photo"), "navigate"),
    (("zoom", "font", "rotate"), "zoom"),
    (("history", "undo", "redo", "back", "edit"), "history"),
    (("media", "track", "seek", "play", "shuttle"), "media"),
    (("tab", "workspace", "notif"), "tabs"),
    (("brush", "opacity", "scale", "label", "rating"), "brush"),
    (("frame", "timeline"), "time"),
)


def suggested_color(title: str, index: int = 0) -> str:
    """Colour for functions that have none, so older profiles look alike."""
    name = (title or "").lower()
    for words, key in _COLOR_KEYWORDS:
        if any(word in name for word in words):
            return COLORS[key]
    palette = list(COLORS.values())
    return palette[index % len(palette)]


def segment_color(segment: Segment, index: int = 0) -> str:
    return segment.color or suggested_color(segment.title, index)


def keys(*names: str, title: str | None = None) -> MacroStep:
    return MacroStep(type=StepType.KEYSTROKE, keys=list(names), title=title)


def scroll(
    direction: str,
    *,
    amount: int = 120,
    axis: str | None = None,
    modifiers: list[str] | None = None,
    title: str | None = None,
) -> MacroStep:
    return MacroStep(
        type=StepType.SCROLL,
        direction=direction,
        value=amount,
        axis=axis,
        modifiers=modifiers,
        title=title,
    )


def _segment(
    title: str,
    cw: list[MacroStep],
    ccw: list[MacroStep],
    center: list[MacroStep] | None = None,
    *,
    color: str | None = None,
    value_command: str | None = None,
    unit: str | None = None,
    treshold: int | None = None,
) -> Segment:
    return Segment(
        title=title,
        macro_cw=cw,
        macro_ccw=ccw,
        macro_center=center or [],
        color=color,
        value_command=value_command,
        unit=unit,
        treshold=treshold,
    )


# --- system ---------------------------------------------------------------

def volume() -> Segment:
    return _segment(
        "Volume",
        [MacroStep(type=StepType.VOLUME, direction="up", value=1, title="Louder")],
        [MacroStep(type=StepType.VOLUME, direction="down", value=1, title="Quieter")],
        [MacroStep(type=StepType.MEDIA, keys=["KEY_MUTE"], title="Mute")],
        color=COLORS["audio"], value_command=VOLUME_QUERY, unit="%", treshold=30,
    )


def brightness() -> Segment:
    return _segment(
        "Brightness",
        [MacroStep(type=StepType.BRIGHTNESS, direction="up", value=1, title="Brighter")],
        [MacroStep(type=StepType.BRIGHTNESS, direction="down", value=1, title="Dimmer")],
        color=COLORS["light"], value_command=BRIGHTNESS_QUERY, unit="%", treshold=30,
    )


def keyboard_light() -> Segment:
    return _segment(
        "Keyboard light",
        [keys("KEY_KBDILLUMUP", title="Brighter")],
        [keys("KEY_KBDILLUMDOWN", title="Dimmer")],
        color=COLORS["light"], value_command=KBD_LIGHT_QUERY, unit="%", treshold=60,
    )


def mute() -> Segment:
    return _segment(
        "Mute", [], [], [MacroStep(type=StepType.MEDIA, keys=["KEY_MUTE"], title="Mute audio")],
        color=COLORS["audio"],
    )


def workspaces() -> Segment:
    return _segment(
        "Workspaces",
        [keys("KEY_LEFTMETA", "KEY_PAGEDOWN", title="Next workspace")],
        [keys("KEY_LEFTMETA", "KEY_PAGEUP", title="Previous workspace")],
        [keys("KEY_LEFTMETA", title="Overview")],
        color=COLORS["tabs"], treshold=60,
    )


# --- navigation -----------------------------------------------------------

def vertical_scroll() -> Segment:
    return _segment(
        "Scroll",
        [scroll("clockwise", title="Scroll up")],
        [scroll("counterclockwise", title="Scroll down")],
        color=COLORS["navigate"],
    )


def horizontal_scroll() -> Segment:
    return _segment(
        "Horizontal scroll",
        [scroll("clockwise", axis="horizontal", title="Scroll right")],
        [scroll("counterclockwise", axis="horizontal", title="Scroll left")],
        color=COLORS["navigate"],
    )


def zoom_wheel(title: str = "Zoom") -> Segment:
    """Ctrl + wheel zooms in nearly every GTK, Qt and browser application."""
    return _segment(
        title,
        [scroll("clockwise", modifiers=["KEY_LEFTCTRL"], title="Zoom in")],
        [scroll("counterclockwise", modifiers=["KEY_LEFTCTRL"], title="Zoom out")],
        [keys("KEY_LEFTCTRL", "KEY_0", title="Reset zoom")],
        color=COLORS["zoom"], treshold=30,
    )


def zoom_keys(title: str = "Zoom") -> Segment:
    return _segment(
        title,
        [keys("KEY_LEFTCTRL", "KEY_EQUAL", title="Zoom in")],
        [keys("KEY_LEFTCTRL", "KEY_MINUS", title="Zoom out")],
        [keys("KEY_LEFTCTRL", "KEY_0", title="Reset zoom")],
        color=COLORS["zoom"], treshold=45,
    )


def tabs() -> Segment:
    return _segment(
        "Tabs",
        [keys("KEY_LEFTCTRL", "KEY_PAGEDOWN", title="Next tab")],
        [keys("KEY_LEFTCTRL", "KEY_PAGEUP", title="Previous tab")],
        color=COLORS["tabs"], treshold=60,
    )


def browser_history() -> Segment:
    return _segment(
        "Back / Forward",
        [keys("KEY_LEFTALT", "KEY_RIGHT", title="Forward")],
        [keys("KEY_LEFTALT", "KEY_LEFT", title="Back")],
        [keys("KEY_F5", title="Reload")],
        color=COLORS["history"], treshold=90,
    )


def arrows() -> Segment:
    return _segment(
        "Arrow keys",
        [keys("KEY_RIGHT", title="Right")],
        [keys("KEY_LEFT", title="Left")],
        [keys("KEY_ENTER", title="Enter")],
        color=COLORS["navigate"], treshold=30,
    )


# --- media ----------------------------------------------------------------

def tracks() -> Segment:
    return _segment(
        "Media",
        [MacroStep(type=StepType.MEDIA, keys=["KEY_NEXTSONG"], title="Next track")],
        [MacroStep(type=StepType.MEDIA, keys=["KEY_PREVIOUSSONG"], title="Previous track")],
        [MacroStep(type=StepType.MEDIA, keys=["KEY_PLAYPAUSE"], title="Play / Pause")],
        color=COLORS["media"], treshold=90,
    )


def seek(forward: list[str] | None = None, back: list[str] | None = None) -> Segment:
    return _segment(
        "Seek",
        [keys(*(forward or ["KEY_RIGHT"]), title="Forward")],
        [keys(*(back or ["KEY_LEFT"]), title="Back")],
        [keys("KEY_SPACE", title="Play / Pause")],
        color=COLORS["media"], treshold=30,
    )


# --- editing --------------------------------------------------------------

def undo_redo(redo: list[str] | None = None) -> Segment:
    return _segment(
        "Undo / Redo",
        [keys(*(redo or ["KEY_LEFTCTRL", "KEY_LEFTSHIFT", "KEY_Z"]), title="Redo")],
        [keys("KEY_LEFTCTRL", "KEY_Z", title="Undo")],
        color=COLORS["history"], treshold=45,
    )


def font_size() -> Segment:
    return _segment(
        "Font size",
        [keys("KEY_LEFTCTRL", "KEY_RIGHTBRACE", title="Larger")],
        [keys("KEY_LEFTCTRL", "KEY_LEFTBRACE", title="Smaller")],
        color=COLORS["zoom"], treshold=45,
    )


# --- creative -------------------------------------------------------------

def brush_size() -> Segment:
    return _segment(
        "Brush size",
        [keys("KEY_RIGHTBRACE", title="Larger brush")],
        [keys("KEY_LEFTBRACE", title="Smaller brush")],
        color=COLORS["brush"], treshold=20,
    )


def krita_opacity() -> Segment:
    return _segment(
        "Opacity",
        [keys("KEY_O", title="More opaque")],
        [keys("KEY_I", title="More transparent")],
        color=COLORS["brush"], treshold=30,
    )


def krita_rotate() -> Segment:
    return _segment(
        "Rotate canvas",
        [keys("KEY_LEFTCTRL", "KEY_RIGHTBRACE", title="Rotate right")],
        [keys("KEY_LEFTCTRL", "KEY_LEFTBRACE", title="Rotate left")],
        [keys("KEY_5", title="Reset rotation")],
        color=COLORS["zoom"], treshold=30,
    )


def inkscape_rotate() -> Segment:
    return _segment(
        "Rotate",
        [keys("KEY_RIGHTBRACE", title="Rotate clockwise")],
        [keys("KEY_LEFTBRACE", title="Rotate counter-clockwise")],
        color=COLORS["zoom"], treshold=30,
    )


def inkscape_scale() -> Segment:
    return _segment(
        "Scale",
        [keys("KEY_DOT", title="Grow selection")],
        [keys("KEY_COMMA", title="Shrink selection")],
        color=COLORS["brush"], treshold=30,
    )


def frame_step() -> Segment:
    return _segment(
        "Frame",
        [keys("KEY_RIGHT", title="Next frame")],
        [keys("KEY_LEFT", title="Previous frame")],
        [keys("KEY_SPACE", title="Play / Pause")],
        color=COLORS["time"], treshold=15,
    )


def resolve_shuttle() -> Segment:
    return _segment(
        "Shuttle",
        [keys("KEY_L", title="Play forward")],
        [keys("KEY_J", title="Play reverse")],
        [keys("KEY_K", title="Stop")],
        color=COLORS["time"], treshold=90,
    )


def resolve_timeline_zoom() -> Segment:
    return _segment(
        "Timeline zoom",
        [keys("KEY_LEFTCTRL", "KEY_EQUAL", title="Zoom in")],
        [keys("KEY_LEFTCTRL", "KEY_MINUS", title="Zoom out")],
        [keys("KEY_LEFTSHIFT", "KEY_Z", title="Fit timeline")],
        color=COLORS["zoom"], treshold=45,
    )


@dataclass(frozen=True)
class FunctionPreset:
    title: str
    category: str
    icon_name: str
    description: str
    factory: Callable[[], Segment]


FUNCTION_LIBRARY: tuple[FunctionPreset, ...] = (
    FunctionPreset("Volume", "System", "audio-volume-high-symbolic", "Turn to change volume, tap to mute", volume),
    FunctionPreset("Brightness", "System", "display-brightness-symbolic", "Screen brightness with live value", brightness),
    FunctionPreset("Keyboard light", "System", "keyboard-brightness-symbolic", "Keyboard backlight level", keyboard_light),
    FunctionPreset("Mute", "System", "audio-volume-muted-symbolic", "Tap the sector to toggle mute", mute),
    FunctionPreset("Workspaces", "System", "view-grid-symbolic", "Switch workspaces, tap for overview", workspaces),
    FunctionPreset("Scroll", "Navigation", "view-continuous-symbolic", "Smooth vertical scrolling", vertical_scroll),
    FunctionPreset("Horizontal scroll", "Navigation", "object-flip-horizontal-symbolic", "Timelines, wide tables and canvases", horizontal_scroll),
    FunctionPreset("Zoom", "Navigation", "zoom-in-symbolic", "Ctrl + wheel zoom, tap to reset", zoom_wheel),
    FunctionPreset("Tabs", "Navigation", "tab-new-symbolic", "Next / previous tab", tabs),
    FunctionPreset("Back / Forward", "Navigation", "go-previous-symbolic", "Browser history, tap to reload", browser_history),
    FunctionPreset("Arrow keys", "Navigation", "go-next-symbolic", "Left / right arrows, tap for Enter", arrows),
    FunctionPreset("Media", "Media", "media-playback-start-symbolic", "Next / previous track, tap to play", tracks),
    FunctionPreset("Seek", "Media", "media-seek-forward-symbolic", "Arrow-key seeking in players", seek),
    FunctionPreset("Undo / Redo", "Editing", "edit-undo-symbolic", "Step through history", undo_redo),
    FunctionPreset("Font size", "Editing", "format-text-larger-symbolic", "LibreOffice-style Ctrl+[ / Ctrl+]", font_size),
    FunctionPreset("Brush size", "Creative", "draw-freehand-symbolic", "[ and ] in GIMP, Krita, Photoshop", brush_size),
    FunctionPreset("Frame", "Creative", "media-skip-forward-symbolic", "Frame stepping in video editors", frame_step),
    FunctionPreset("Timeline zoom", "Creative", "zoom-fit-best-symbolic", "Ctrl+= / Ctrl+- timeline zoom", resolve_timeline_zoom),
)

LIBRARY_CATEGORIES = ("System", "Navigation", "Media", "Editing", "Creative")


def default_segments() -> list[Segment]:
    """ASUS Dial-like system defaults used for the fallback profile."""
    return [volume(), brightness(), vertical_scroll(), zoom_wheel(), undo_redo(), tracks()]


@dataclass(frozen=True)
class AppPack:
    name: str
    hints: tuple[str, ...]
    factory: Callable[[], list[Segment]]


APP_PACKS: tuple[AppPack, ...] = (
    AppPack("Browser", ("firefox", "chrom", "brave", "vivaldi", "microsoft-edge", "epiphany", "librewolf", "zen_browser", "zen-browser"),
            lambda: [vertical_scroll(), zoom_wheel(), tabs(), browser_history(), volume()]),
    AppPack("GIMP", ("gimp",),
            lambda: [brush_size(), zoom_wheel(), undo_redo(["KEY_LEFTCTRL", "KEY_Y"]), vertical_scroll(), horizontal_scroll()]),
    AppPack("Krita", ("krita",),
            lambda: [brush_size(), krita_opacity(), zoom_wheel(), krita_rotate(), undo_redo()]),
    AppPack("Inkscape", ("inkscape",),
            lambda: [zoom_wheel(), inkscape_rotate(), inkscape_scale(), undo_redo(), vertical_scroll()]),
    AppPack("Blender", ("blender",),
            lambda: [frame_step(), _rename(vertical_scroll(), "Zoom view"), undo_redo(), horizontal_scroll()]),
    AppPack("Kdenlive", ("kdenlive",),
            lambda: [frame_step(), zoom_wheel("Timeline zoom"), undo_redo(), volume()]),
    AppPack("DaVinci Resolve", ("resolve", "davinci"),
            lambda: [frame_step(), resolve_timeline_zoom(), resolve_shuttle(), undo_redo()]),
    AppPack("LibreOffice", ("libreoffice",),
            lambda: [vertical_scroll(), zoom_wheel(), font_size(), undo_redo(["KEY_LEFTCTRL", "KEY_Y"])]),
    AppPack("Code editor", ("code", "codium", "zed", "gnome.textedit", "kate"),
            lambda: [vertical_scroll(), zoom_keys(), _rename(tabs(), "Editor tabs"), undo_redo(), horizontal_scroll()]),
    AppPack("Spotify", ("spotify",),
            lambda: [tracks(), volume(), seek(["KEY_LEFTSHIFT", "KEY_RIGHT"], ["KEY_LEFTSHIFT", "KEY_LEFT"])]),
    AppPack("Video player", ("vlc", "mpv", "celluloid", "totem", "showtime", "haruna", "smplayer"),
            lambda: [seek(), volume(), tracks()]),
)


def _rename(segment: Segment, title: str) -> Segment:
    segment.title = title
    return segment


def pack_for_app(app_id: str | None) -> AppPack | None:
    """Return the pre-programmed pack whose hint occurs in the app id."""
    if not app_id:
        return None
    lowered = app_id.lower()
    for pack in APP_PACKS:
        if any(hint in lowered for hint in pack.hints):
            return pack
    return None


def profile_for_app(name: str, app_id: str) -> Profile:
    """Create an application profile, pre-programmed when a pack matches."""
    from config.schema import DARKTABLE_APP_ID, darktable_profile

    if app_id == DARKTABLE_APP_ID:
        return darktable_profile()
    pack = pack_for_app(app_id)
    return Profile(name=name, app_id=app_id, segments=pack.factory() if pack else [])
