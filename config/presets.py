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
    "record": "#ff6b6b",
    "cut": "#ffb86b",
    "layers": "#7fd4c8",
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
#
# Shortcuts below are the applications' own defaults, checked against their
# sources or manuals (GIMP app/actions/*.c, Krita krita_default.shortcuts,
# Inkscape share/keys/inkscape.xml, darktable src/views/darkroom.c,
# Blender keymap_data/blender_default.py, the Kdenlive, Shotcut and
# Audacity shortcut references).

CTRL = "KEY_LEFTCTRL"
SHIFT = "KEY_LEFTSHIFT"
ALT = "KEY_LEFTALT"


def _turn(title, cw, ccw, tap=None, *, color, treshold=30):
    """A function whose rotation and tap send plain shortcuts."""
    return _segment(
        title,
        [keys(*cw[1:], title=cw[0])],
        [keys(*ccw[1:], title=ccw[0])],
        [keys(*tap[1:], title=tap[0])] if tap else None,
        color=color, treshold=treshold,
    )


def _tap(title, tap, *, color):
    """An action-only function: tapping its menu sector runs it."""
    return _segment(title, [], [], [keys(*tap[1:], title=tap[0])], color=color)


def brush_size() -> Segment:
    return _turn("Brush size", ("Larger brush", "KEY_RIGHTBRACE"), ("Smaller brush", "KEY_LEFTBRACE"),
                 color=COLORS["brush"], treshold=20)


def frame_step() -> Segment:
    return _turn("Frame", ("Next frame", "KEY_RIGHT"), ("Previous frame", "KEY_LEFT"),
                 ("Play / Pause", "KEY_SPACE"), color=COLORS["time"], treshold=15)


def shuttle() -> Segment:
    """J / K / L shuttle shared by Kdenlive, DaVinci Resolve and Shotcut."""
    return _turn("Shuttle", ("Play forward", "KEY_L"), ("Play reverse", "KEY_J"),
                 ("Stop", "KEY_K"), color=COLORS["time"], treshold=90)


def resolve_timeline_zoom() -> Segment:
    return _turn("Timeline zoom", ("Zoom in", CTRL, "KEY_EQUAL"), ("Zoom out", CTRL, "KEY_MINUS"),
                 ("Fit timeline", SHIFT, "KEY_Z"), color=COLORS["zoom"], treshold=45)


# GIMP 3
def gimp_profile_segments() -> list[Segment]:
    return [
        _turn("Brush size", ("Larger brush +10", SHIFT, "KEY_RIGHTBRACE"), ("Smaller brush -10", SHIFT, "KEY_LEFTBRACE"),
              color=COLORS["brush"], treshold=20),
        _turn("Opacity", ("More opaque", SHIFT, "KEY_DOT"), ("More transparent", SHIFT, "KEY_COMMA"),
              color=COLORS["light"], treshold=15),
        _turn("Zoom", ("Zoom in", "KEY_KPPLUS"), ("Zoom out", "KEY_KPMINUS"),
              ("Fit image", CTRL, SHIFT, "KEY_J"), color=COLORS["zoom"]),
        _turn("Layers", ("Layer below", "KEY_PAGEDOWN"), ("Layer above", "KEY_PAGEUP"),
              ("Top layer", "KEY_HOME"), color=COLORS["layers"], treshold=60),
        undo_redo([CTRL, "KEY_Y"]),
    ]


# Krita 5
def krita_profile_segments() -> list[Segment]:
    return [
        brush_size(),
        _turn("Opacity", ("More opaque", "KEY_O"), ("More transparent", "KEY_I"),
              color=COLORS["light"], treshold=20),
        _turn("Zoom", ("Zoom in", CTRL, "KEY_EQUAL"), ("Zoom out", CTRL, "KEY_MINUS"),
              ("Zoom 100 %", CTRL, "KEY_0"), color=COLORS["zoom"]),
        _turn("Rotate canvas", ("Rotate right", CTRL, "KEY_RIGHTBRACE"), ("Rotate left", CTRL, "KEY_LEFTBRACE"),
              ("Mirror view", "KEY_M"), color=COLORS["navigate"]),
        _turn("Layers", ("Next layer", "KEY_PAGEUP"), ("Previous layer", "KEY_PAGEDOWN"),
              color=COLORS["layers"], treshold=60),
        undo_redo(),
    ]


# Inkscape 1.x
def inkscape_profile_segments() -> list[Segment]:
    return [
        _turn("Zoom", ("Zoom in", "KEY_EQUAL"), ("Zoom out", "KEY_MINUS"),
              ("Fit page", "KEY_5"), color=COLORS["zoom"]),
        _turn("Rotate", ("Rotate clockwise", "KEY_RIGHTBRACE"), ("Rotate counter-clockwise", "KEY_LEFTBRACE"),
              color=COLORS["navigate"]),
        _turn("Scale", ("Grow selection", "KEY_DOT"), ("Shrink selection", "KEY_COMMA"),
              color=COLORS["brush"]),
        _turn("Arrange", ("Raise", "KEY_PAGEUP"), ("Lower", "KEY_PAGEDOWN"),
              color=COLORS["layers"], treshold=60),
        undo_redo(),
    ]


# darktable 5
def darktable_profile_segments() -> list[Segment]:
    return [
        _turn("Zoom", ("Zoom in", CTRL, SHIFT, "KEY_EQUAL"), ("Zoom out", CTRL, "KEY_MINUS"),
              ("Fit image", ALT, "KEY_3"), color=COLORS["zoom"]),
        _turn("Photo", ("Next image", "KEY_SPACE"), ("Previous image", "KEY_BACKSPACE"),
              ("Close-up", ALT, "KEY_1"), color=COLORS["navigate"], treshold=60),
        _turn("Rating", ("Five stars", "KEY_5"), ("Clear rating", "KEY_0"),
              ("Reject", "KEY_R"), color=COLORS["light"], treshold=90),
        _turn("Colour label", ("Green label", "KEY_F3"), ("Red label", "KEY_F1"),
              ("Yellow label", "KEY_F2"), color=COLORS["media"], treshold=90),
        undo_redo([CTRL, "KEY_Y"]),
    ]


# Blender 4/5
def blender_profile_segments() -> list[Segment]:
    return [
        frame_step(),
        _turn("Keyframe", ("Next keyframe", "KEY_DOWN"), ("Previous keyframe", "KEY_UP"),
              ("Insert keyframe", "KEY_I"), color=COLORS["light"], treshold=45),
        _turn("Zoom view", ("Zoom in", CTRL, "KEY_EQUAL"), ("Zoom out", CTRL, "KEY_MINUS"),
              ("View all", "KEY_HOME"), color=COLORS["zoom"]),
        undo_redo(),
    ]


# Kdenlive 24/25
def kdenlive_profile_segments() -> list[Segment]:
    return [
        frame_step(),
        shuttle(),
        _turn("Edit points", ("Next snap point", ALT, "KEY_RIGHT"), ("Previous snap point", ALT, "KEY_LEFT"),
              ("Cut clip", SHIFT, "KEY_R"), color=COLORS["cut"], treshold=45),
        _turn("Timeline zoom", ("Zoom in", CTRL, "KEY_EQUAL"), ("Zoom out", CTRL, "KEY_MINUS"),
              color=COLORS["zoom"]),
        undo_redo(),
    ]


# DaVinci Resolve 19/20
def resolve_profile_segments() -> list[Segment]:
    return [
        frame_step(),
        shuttle(),
        _turn("Edit points", ("Next edit", "KEY_DOWN"), ("Previous edit", "KEY_UP"),
              ("Split clip", CTRL, "KEY_BACKSLASH"), color=COLORS["cut"], treshold=45),
        resolve_timeline_zoom(),
        undo_redo(),
    ]


# Shotcut
def shotcut_profile_segments() -> list[Segment]:
    return [
        frame_step(),
        shuttle(),
        _turn("Edit points", ("Next edit", ALT, "KEY_RIGHT"), ("Previous edit", ALT, "KEY_LEFT"),
              ("Split at playhead", "KEY_S"), color=COLORS["cut"], treshold=45),
        _turn("Timeline zoom", ("Zoom in", "KEY_EQUAL"), ("Zoom out", "KEY_MINUS"),
              ("Fit timeline", "KEY_0"), color=COLORS["zoom"]),
        undo_redo([CTRL, "KEY_Y"]),
    ]


# Audacity 3
def audacity_profile_segments() -> list[Segment]:
    return [
        _turn("Cursor", ("Jump right", "KEY_DOT"), ("Jump left", "KEY_COMMA"),
              ("Play / Stop", "KEY_SPACE"), color=COLORS["time"], treshold=20),
        _turn("Zoom", ("Zoom in", CTRL, "KEY_1"), ("Zoom out", CTRL, "KEY_3"),
              ("Fit to width", CTRL, "KEY_F"), color=COLORS["zoom"]),
        _turn("Clips", ("Next clip", ALT, "KEY_DOT"), ("Previous clip", ALT, "KEY_COMMA"),
              ("Split", CTRL, "KEY_I"), color=COLORS["cut"], treshold=60),
        undo_redo([CTRL, "KEY_Y"]),
        volume(),
    ]


# OBS Studio ships without hotkeys. The profile sends unused combinations;
# assign each once in OBS: Settings -> Hotkeys (the same key may be used for
# a start and a stop action).
OBS_HOTKEYS = {
    "record": (CTRL, SHIFT, "KEY_F9"),
    "stream": (CTRL, SHIFT, "KEY_F10"),
    "pause": (CTRL, SHIFT, "KEY_F11"),
    "mic": (CTRL, SHIFT, "KEY_F12"),
    "replay": (CTRL, SHIFT, "KEY_F8"),
}


def obs_profile_segments() -> list[Segment]:
    return [
        _tap("Record", ("Start / stop recording", *OBS_HOTKEYS["record"]), color=COLORS["record"]),
        _tap("Stream", ("Start / stop streaming", *OBS_HOTKEYS["stream"]), color=COLORS["history"]),
        _tap("Pause", ("Pause / resume recording", *OBS_HOTKEYS["pause"]), color=COLORS["light"]),
        _tap("Mic", ("Mute / unmute microphone", *OBS_HOTKEYS["mic"]), color=COLORS["audio"]),
        _tap("Replay", ("Save replay", *OBS_HOTKEYS["replay"]), color=COLORS["navigate"]),
        volume(),
    ]


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
    FunctionPreset("Font size", "Editing", "font-x-generic-symbolic", "LibreOffice-style Ctrl+[ / Ctrl+]", font_size),
    FunctionPreset("Brush size", "Creative", "document-edit-symbolic", "[ and ] in GIMP, Krita, Photoshop", brush_size),
    FunctionPreset("Frame", "Creative", "media-skip-forward-symbolic", "Frame stepping in video editors", frame_step),
    FunctionPreset("Timeline zoom", "Creative", "zoom-fit-best-symbolic", "Ctrl+= / Ctrl+- timeline zoom", resolve_timeline_zoom),
    FunctionPreset("Shuttle", "Creative", "media-seek-forward-symbolic", "J / K / L in video editors", shuttle),
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
    # Desktop ID used when the profile is added without the app installed.
    app_id: str = ""
    category: str = "Other"
    note: str = ""


# Creator applications first: the ProArt spirit of the laptop.
APP_PACKS: tuple[AppPack, ...] = (
    AppPack("GIMP", ("gimp",), gimp_profile_segments, "org.gimp.GIMP.desktop", "Photo & graphics"),
    AppPack("Krita", ("krita",), krita_profile_segments, "org.kde.krita.desktop", "Photo & graphics"),
    AppPack("Inkscape", ("inkscape",), inkscape_profile_segments, "org.inkscape.Inkscape.desktop", "Photo & graphics"),
    AppPack("darktable", ("darktable",), darktable_profile_segments, "org.darktable.darktable.desktop", "Photo & graphics"),
    AppPack("Blender", ("blender",), blender_profile_segments, "org.blender.Blender.desktop", "3D"),
    AppPack("Kdenlive", ("kdenlive",), kdenlive_profile_segments, "org.kde.kdenlive.desktop", "Video"),
    AppPack("DaVinci Resolve", ("resolve", "davinci"), resolve_profile_segments,
            "com.blackmagicdesign.resolve.desktop", "Video"),
    AppPack("Shotcut", ("shotcut",), shotcut_profile_segments, "org.shotcut.Shotcut.desktop", "Video"),
    AppPack("Audacity", ("audacity",), audacity_profile_segments, "org.audacityteam.Audacity.desktop", "Audio"),
    AppPack("OBS Studio", ("obsproject", "obs-studio"), obs_profile_segments, "com.obsproject.Studio.desktop",
            "Audio", "Assign Ctrl+Shift+F8 to F12 in OBS: Settings, Hotkeys"),
    AppPack("Browser", ("firefox", "chrom", "brave", "vivaldi", "microsoft-edge", "epiphany", "librewolf", "zen_browser", "zen-browser"),
            lambda: [vertical_scroll(), zoom_wheel(), tabs(), browser_history(), volume()],
            "firefox.desktop", "Everyday"),
    AppPack("LibreOffice", ("libreoffice",),
            lambda: [vertical_scroll(), zoom_wheel(), font_size(), undo_redo([CTRL, "KEY_Y"])],
            "libreoffice-writer.desktop", "Everyday"),
    AppPack("Code editor", ("code", "codium", "zed", "gnome.textedit", "kate"),
            lambda: [vertical_scroll(), _reset_with(zoom_keys(), "Reset zoom", CTRL, "KEY_KP0"),
                     _rename(tabs(), "Editor tabs"), undo_redo(), horizontal_scroll()],
            "code.desktop", "Everyday"),
    AppPack("Spotify", ("spotify",),
            lambda: [tracks(), volume(), seek([SHIFT, "KEY_RIGHT"], [SHIFT, "KEY_LEFT"])],
            "spotify.desktop", "Everyday"),
    AppPack("Video player", ("vlc", "mpv", "celluloid", "totem", "showtime", "haruna", "smplayer"),
            lambda: [seek(), volume(), tracks()], "vlc.desktop", "Everyday"),
)


def _reset_with(segment: Segment, title: str, *names: str) -> Segment:
    """Replace a function's tap action (VS Code resets zoom with Ctrl+Numpad 0)."""
    segment.macro_center = [keys(*names, title=title)]
    return segment


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
    pack = pack_for_app(app_id)
    return Profile(name=name, app_id=app_id, segments=pack.factory() if pack else [])


def profile_for_pack(pack: AppPack) -> Profile:
    """Profile for a pack without the application installed."""
    return Profile(name=pack.name, app_id=pack.app_id, segments=pack.factory())
