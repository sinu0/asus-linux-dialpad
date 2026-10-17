"""What the on-screen dial shows and where, without any toolkit.

Python twins of the logic in gnome/extension/dial.js (overlayPlacement,
besidePointer, effectiveLook, pillContent, pillPlacement, iconLayout,
pointerPlacement, openSubmenu, submenuPlacement, submenuLayout…) and of the state handling in gnome/extension/extension.js
(appearance from config.json, OverlayState and OverlayDetails). The dials outside GNOME Shell
(overlay/layer_shell.py) use them, so every desktop places and fades the
dial alike. tests/test_overlay_look.py runs the JavaScript originals in gjs
and compares; keep both in sync.

A view is a dict like the one in dial.js: {"state", "details", "appearance",
"accent", "skin"}. "state" keeps the camelCase keys of extension.js.
"""

from __future__ import annotations

import json
import math
import os
import re

from config.labels import icon_for_title

# Logical geometry, twins of the constants in dial.js.
DIAL_D = 360
DIAL_R = DIAL_D / 2
HINT_H = 46
ICON_R = 113
HIGHLIGHT_R = 152
GAUGE_R = 136
POINTER_GLOW_R = 15
POINTER_SIZE = 2 * POINTER_GLOW_R
ICON_SIZE = 20
CENTER_ICON_SIZE = 26
# A group's list beside the dial (the LIST_* constants of dial.js).
LIST_W = 232
LIST_ROW_H = 40
LIST_HEADER_H = 34
LIST_FOOTER_H = 22
LIST_PAD = 8
LIST_MARGIN = 12
LIST_ICON_SIZE = 18
LIST_ROWS_MAX = 7
LIST_SCALE_MIN = 0.6

# Timing and sizes from extension.js.
FADE_IN_MS = 120
FADE_OUT_MS = 260
# Visibility "fade": full this long after a touch, then fading slowly.
FADE_AFTER_MS = 1000
FADE_SLOW_MS = 600
PILL_ICON_SIZE = 18
# A group's list slides out from the dial.
LIST_OPEN_MS = 180
LIST_CLOSE_MS = 120
LIST_SLIDE = 24

DEFAULT_SKIN = "glass"
DEFAULT_ACCENT = (0.906, 0.725, 0.553, 1)
# The overlay section of config.json the dial reads, with the extension's
# defaults (DEFAULT_APPEARANCE in extension.js).
DEFAULT_APPEARANCE = {
    "scale": 1.0,
    "position": "lower",
    "hide_delay_ms": 1500,
    "show_hints": True,
    "show_pointer": True,
    "accent": "#e7b98d",
    "skin": DEFAULT_SKIN,
    "skin_light": "frost",
    "follow_system_style": False,
    "custom_x": 0.5,
    "custom_y": 0.5,
    "visibility": "full",
    "fade_opacity": 35,
    "pointer_side": "below-right",
    "pointer_gap": 24,
}

LOOK_POSITIONS = ("center", "lower", "bottom", "top", "custom", "pointer")
LOOK_VISIBILITIES = ("full", "fade", "pill")
# Position "pointer": the dial's side of the pointer and its distance in
# logical pixels (not multiplied by the scale).
POINTER_SIDES = ("below-right", "below-left", "above-right", "above-left", "right", "left", "above", "below")
POINTER_GAP = 24
POINTER_GAP_MAX = 400
# [vertical, horizontal] of each side: 1 below or right, -1 above or left.
_POINTER_DIRECTIONS = ((1, 1), (1, -1), (-1, 1), (-1, -1), (0, 1), (0, -1), (-1, 0), (1, 0))


# --- JavaScript arithmetic --------------------------------------------------

def js_round(value: float) -> int:
    """Math.round(): halves go up, also below zero."""
    return math.floor(value + 0.5)


def js_number(value) -> float:
    """Number(value): NaN for anything that is not a number; None stands
    for JSON null, which is 0."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return math.nan
    return math.nan


def _is_number(value) -> bool:
    """typeof value === 'number' (booleans are not numbers there)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _or(number: float, fallback: float) -> float:
    """number || fallback for a number: NaN and 0 take the fallback."""
    return fallback if number != number or number == 0 else number


_HEX6 = re.compile(r"^#?([0-9a-f]{6})$", re.IGNORECASE)


def parse_color(text, fallback):
    """parseColor() in dial.js: "#rrggbb" → (r, g, b, 1), else fallback."""
    match = _HEX6.match(str(text if text is not None else "").strip())
    if not match:
        return fallback
    value = int(match.group(1), 16)
    return ((value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255, 1)


# --- appearance and look ----------------------------------------------------

def load_appearance(overlay) -> dict:
    """The overlay section of config.json over the defaults, with scale and
    hide delay kept in range (_loadAppearance() in extension.js)."""
    appearance = dict(DEFAULT_APPEARANCE)
    if isinstance(overlay, dict):
        for key in DEFAULT_APPEARANCE:
            if overlay.get(key) is not None:
                appearance[key] = overlay[key]
    appearance["scale"] = max(0.6, min(1.6, _or(js_number(appearance["scale"]), 1)))
    appearance["hide_delay_ms"] = max(0, min(10000, _or(js_number(appearance["hide_delay_ms"]), 0)))
    return appearance


def skin_id(appearance: dict, prefers_dark: bool) -> str:
    """The skin to show: skin_light while the desktop is light with
    follow_system_style, otherwise skin (_applySkin() in extension.js)."""
    light = bool(appearance.get("follow_system_style")) and not prefers_dark
    chosen = appearance.get("skin_light") if light else appearance.get("skin")
    return str(chosen or DEFAULT_SKIN)


def beside_pointer(monitor, pointer, side, gap, width, height, middle) -> dict:
    """besidePointer(): a box next to the pointer ([x, y] on the monitor),
    on the given side or the first one with room, kept on the monitor."""
    px, py = pointer
    v, h = _POINTER_DIRECTIONS[POINTER_SIDES.index(side) if side in POINTER_SIDES else 0]
    if v and h:
        candidates = ((v, h), (v, -h), (-v, h), (-v, -h))
    elif v:
        candidates = ((v, 0), (-v, 0), (0, 1), (0, -1))
    else:
        candidates = ((0, h), (0, -h), (1, 0), (-1, 0))
    mw, mh = monitor["width"], monitor["height"]

    def clamp(value, maximum):
        return max(0, min(maximum, js_round(value)))

    best = None
    for cv, ch in candidates:
        wanted_x = px + gap if ch > 0 else px - gap - width if ch < 0 else px - width / 2
        wanted_y = py + gap if cv > 0 else py - gap - height if cv < 0 else py - middle
        # Room on the side's own axes; the other one may be pushed in.
        fits = ((not ch or (wanted_x >= 0 and wanted_x + width <= mw))
                and (not cv or (wanted_y >= 0 and wanted_y + height <= mh)))
        x = clamp(wanted_x, mw - width)
        y = clamp(wanted_y, mh - height)
        # How far the pointer is outside the box, up to the gap.
        away = min(gap, max(x - px, px - x - width, y - py, py - y - height))
        if best is None or away > best[2] or (away == best[2] and fits and not best[3]):
            best = (x, y, away, fits)
    return {"x": best[0], "y": best[1]}


def overlay_placement(monitor, scale, position, custom=None, pointer=None,
                      side=POINTER_SIDES[0], gap=POINTER_GAP) -> dict:
    """overlayPlacement(): where the dial goes on a monitor ({"width",
    "height"} in logical pixels), relative to the monitor's corner;
    pointer: [x, y] on the monitor for position "pointer"."""
    width = js_round(DIAL_D * scale)
    height = js_round((DIAL_D + HINT_H) * scale)
    mw, mh = monitor["width"], monitor["height"]

    def clamp(value, maximum):
        return max(0, min(maximum, js_round(value)))

    if position == "pointer" and pointer:
        placed = beside_pointer(monitor, pointer, side, gap, width, height, width / 2)
        return {**placed, "width": width, "height": height}
    if position == "custom" and custom:
        return {
            "x": clamp(mw * custom[0] - width / 2, mw - width),
            "y": clamp(mh * custom[1] - width / 2, mh - height),
            "width": width,
            "height": height,
        }
    centred = (mh - width) / 2
    lower = centred + min(84, mh * 0.08)
    positions = {
        "center": centred,
        "lower": lower,
        "bottom": max(lower, mh - height - js_round(mh * 0.06)),
        "top": min(centred, js_round(mh * 0.08)),
    }
    wanted = js_round(positions.get(position, positions["lower"]) if isinstance(position, str) else positions["lower"])
    return {
        "x": js_round((mw - width) / 2),
        "y": max(0, min(mh - height, wanted)),
        "width": width,
        "height": height,
    }


def submenu_size(count, hints=True) -> dict:
    """submenuSize(): a group's list with count functions, shadow margin
    included (unscaled)."""
    rows = max(1, min(LIST_ROWS_MAX, count))
    return {
        "width": LIST_W + 2 * LIST_MARGIN,
        "height": LIST_HEADER_H + rows * LIST_ROW_H + 2 * LIST_PAD + (LIST_FOOTER_H if hints else 0)
        + 2 * LIST_MARGIN,
    }


def submenu_placement(monitor, dial, scale, size, prefer_right=True) -> dict:
    """submenuPlacement(): the list beside the dial (an overlay_placement()),
    on the preferred side when it has room, smaller rather than over the
    dial, never past an edge."""
    # The shadow margin may overlap the dial's own empty margin.
    reach = size["width"] - LIST_MARGIN
    room = {
        "right": (monitor["width"] - dial["x"] - dial["width"]) / reach,
        "left": dial["x"] / reach,
    }
    preferred, other = ("right", "left") if prefer_right else ("left", "right")
    side = preferred
    if room[preferred] < scale:
        side = other if room[other] >= scale or room[other] > room[preferred] else preferred
    fitted = max(LIST_SCALE_MIN, min(scale, room[side], monitor["height"] / size["height"]))
    width = js_round(size["width"] * fitted)
    height = js_round(size["height"] * fitted)
    inset = js_round(LIST_MARGIN * fitted)

    def clamp(value, maximum):
        return max(0, min(maximum, js_round(value)))

    x = dial["x"] + dial["width"] - inset if side == "right" else dial["x"] - width + inset
    return {
        "x": clamp(x, monitor["width"] - width),
        "y": clamp(dial["y"] + dial["width"] / 2 - height / 2, monitor["height"] - height),
        "width": width,
        "height": height,
        "side": side,
        "scale": fitted,
    }


def effective_look(appearance, look) -> dict:
    """effectiveLook(): config.json defaults with the profile's and
    function's overrides from the driver on top; invalid values fall back."""
    levels = [look if isinstance(look, dict) else {}, appearance or {}, {}]

    def pick(key, valid, fallback):
        for level in levels:
            if key in level and valid(level[key]):
                return level[key]
        return fallback

    def fraction(value):
        return _is_number(value) and 0 <= value <= 1

    def member(choices):
        return lambda value: isinstance(value, str) and value in choices

    return {
        "position": pick("position", member(LOOK_POSITIONS), "lower"),
        "custom": [pick("custom_x", fraction, 0.5), pick("custom_y", fraction, 0.5)],
        "visibility": pick("visibility", member(LOOK_VISIBILITIES), "full"),
        "fadeOpacity": pick("fade_opacity", lambda value: _is_number(value) and 0 <= value <= 100, 35) / 100,
        "pointerSide": pick("pointer_side", member(POINTER_SIDES), POINTER_SIDES[0]),
        "pointerGap": pick("pointer_gap", lambda value: _is_number(value) and 0 <= value <= POINTER_GAP_MAX,
                           POINTER_GAP),
    }


def pill_placement(monitor, scale, look, width, height, pointer=None) -> dict:
    """pillPlacement(): the pill sits where the dial's centre would be, or
    on the dial's side of the pointer."""
    if look["position"] == "pointer" and pointer:
        return beside_pointer(monitor, pointer, look["pointerSide"], look["pointerGap"], width, height, height / 2)
    cx, cy = monitor["width"] * look["custom"][0], monitor["height"] * look["custom"][1]
    if look["position"] != "custom":
        dial = overlay_placement(monitor, scale, look["position"])
        cx, cy = dial["x"] + dial["width"] / 2, dial["y"] + dial["width"] / 2

    def clamp(value, maximum):
        return max(0, min(maximum, js_round(value)))

    return {"x": clamp(cx - width / 2, monitor["width"] - width), "y": clamp(cy - height / 2, monitor["height"] - height)}


# --- driver state -----------------------------------------------------------

def new_state() -> dict:
    return {
        "enabled": False,
        "title": "",
        "titles": [],
        "icons": [],
        "menuTitles": [],
        "menuIcons": [],
        "value": 0,
        "valueAngleStart": 0.0,
        "unit": "",
        "centerPressed": False,
        "valueShowOnlyProgress": False,
        "touching": False,
    }


def new_details() -> dict:
    return {
        "profile": "",
        "mode": "multi",
        "colors": [],
        "color": "",
        "hints": {},
        "hold_returns": True,
        "pointer": -1,
        "look": {},
        "icon": "",
        "parent": "",
        "submenu": None,
    }


def apply_overlay_state(state: dict, values) -> None:
    """Store an OverlayState signal (its unpacked tuple) like
    _onOverlayState() in extension.js; drivers that send fewer than ten
    fields keep the dial up while enabled."""
    legacy = len(values) < 10
    values = list(values) + [None] * (10 - len(values))
    enabled, title, titles, icons, value, angle, unit, pressed, progress, touching = values[:10]
    state["enabled"] = bool(enabled)
    state["title"] = title or ""
    state["titles"] = list(titles or [])
    state["icons"] = list(icons or [])
    if any(state["titles"]):
        state["menuTitles"] = list(state["titles"])
        state["menuIcons"] = list(state["icons"])
    state["value"] = value or 0
    state["valueAngleStart"] = angle or 0.0
    state["unit"] = unit or ""
    state["centerPressed"] = bool(pressed)
    state["valueShowOnlyProgress"] = bool(progress)
    state["touching"] = state["enabled"] if legacy else bool(touching)


def merge_details(details: dict, text: str) -> None:
    """Merge an OverlayDetails JSON payload; broken payloads are ignored."""
    try:
        update = json.loads(text)
    except (TypeError, ValueError):
        return
    if isinstance(update, dict):
        details.update(update)


def make_view(state: dict, details: dict, appearance: dict, skin: dict) -> dict:
    """A view as dial.js expects it; skin from config.skins.resolve_skin()."""
    return {
        "state": state,
        "details": details,
        "appearance": appearance,
        "accent": parse_color(appearance.get("accent"), DEFAULT_ACCENT),
        "skin": skin,
    }


# --- state helpers (dial.js) -------------------------------------------------

def segment_state(state) -> dict:
    menu = any(state["titles"])
    titles = state["titles"] if menu else state["menuTitles"]
    icons = state["icons"] if menu else state["menuIcons"]
    return {"titles": titles, "icons": icons, "count": max(len(titles), 4)}


def is_selected_mode(state) -> bool:
    return bool(state["title"]) and state["title"] != "Menu" and not any(state["titles"])


def segment_color(view, index):
    colors = view["details"].get("colors") or []
    return parse_color(colors[index] if 0 <= index < len(colors) else None, view["accent"])


def js_string(value) -> str:
    """String(value ?? '') for the JSON values the driver sends."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format_value(value)
    return str(value)


def open_submenu(view):
    """openSubmenu(): the group whose list is open beside the menu, or None:
    {title, index (its sector), items, icons, colors (parsed), selected,
    first (top visible row), rows (visible), preferRight}."""
    state, details = view["state"], view["details"]
    submenu = details.get("submenu")
    if not isinstance(submenu, dict) or not isinstance(submenu.get("items"), list) or not submenu["items"]:
        return None
    if not state["enabled"] or is_selected_mode(state) or not any(state["titles"]):
        return None
    items = [js_string(item) for item in submenu["items"]]
    count = len(items)
    icons = submenu.get("icons") if isinstance(submenu.get("icons"), list) else []
    colors = submenu.get("colors") if isinstance(submenu.get("colors"), list) else []
    number = js_number(submenu.get("selected"))
    selected = max(0, min(count - 1, js_round(_or(number, 0))))
    rows = min(LIST_ROWS_MAX, count)
    first = max(0, min(count - rows, selected - rows // 2))
    titles = segment_state(state)["titles"]
    title = js_string(submenu.get("title"))
    index = titles.index(title) if title in titles else -1
    sectors = max(len(titles), 4)
    return {
        "title": title,
        "index": index,
        "items": items,
        "icons": [js_string(icons[position] if position < len(icons) else None) for position in range(count)],
        "colors": [parse_color(colors[position] if position < len(colors) else None, view["accent"])
                   for position in range(count)],
        "selected": selected,
        "first": first,
        "rows": rows,
        # A sector on the right half of the dial opens its list to the right.
        "preferRight": index < 0 or (index + 0.5) / sectors <= 0.5,
    }


def active_title(view) -> str:
    """activeTitle(): the group of an open list, else the title."""
    submenu = open_submenu(view)
    if submenu:
        return submenu["title"]
    return "" if view["state"]["title"] == "Menu" else view["state"]["title"]


def function_color(view):
    return parse_color(view["details"].get("color"), view["accent"])


def active_color(view):
    submenu = open_submenu(view)
    if submenu:
        return submenu["colors"][submenu["selected"]]
    titles = segment_state(view["state"])["titles"]
    title = view["state"]["title"]
    return segment_color(view, titles.index(title)) if title in titles else view["accent"]


def _configured_icon(icons, index):
    return (icons[index] if 0 <= index < len(icons) else "") or ""


def pill_content(view) -> dict:
    """pillContent(): the selected function and its value, the function
    under the finger in the menu, or the profile."""
    state, details = view["state"], view["details"]
    segments = segment_state(state)

    def configured(title):
        titles = segments["titles"]
        return _configured_icon(segments["icons"], titles.index(title) if title in titles else -1)

    submenu = open_submenu(view)
    if submenu:
        return {"title": state["title"], "value": f"{submenu['selected'] + 1}/{len(submenu['items'])}",
                "configured": submenu["icons"][submenu["selected"]], "color": submenu["colors"][submenu["selected"]]}
    if is_selected_mode(state):
        value = f"{format_value(state['value'])}{state['unit']}" if not state["valueShowOnlyProgress"] and state["unit"] else ""
        icon = details["icon"] if isinstance(details.get("icon"), str) else configured(state["title"])
        return {"title": state["title"], "value": value, "configured": icon, "color": function_color(view)}
    if state["title"] and state["title"] != "Menu":
        return {"title": state["title"], "value": "", "configured": configured(state["title"]),
                "color": active_color(view)}
    return {"title": details.get("profile") or "Dial", "value": "", "configured": "", "color": view["accent"]}


def format_value(value) -> str:
    """A number as JavaScript prints it in a template string."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e21:
        return str(int(value))
    return str(value)


def icon_name_for(title: str) -> str:
    """iconNameFor() in dial.js; the rules live in config.labels."""
    return icon_for_title(title)


def icon_source(title: str, configured: str) -> str:
    """The icon to show (_gicon() in extension.js): a configured theme icon
    name or absolute path that exists, else the one for the title."""
    if configured and (not configured.startswith("/") or os.path.exists(configured)):
        return configured
    return icon_name_for(title)


def icon_layout(view) -> dict:
    """iconLayout(): menu and centre icons relative to the dial's top left
    corner, scaled and rounded like the extension's icon actors."""
    state, skin = view["state"], view["skin"]
    segments = segment_state(state)
    titles, icons, count = segments["titles"], segments["icons"], segments["count"]
    active = active_title(view)
    submenu = open_submenu(view)
    scale = view["appearance"]["scale"]
    selected = is_selected_mode(state)
    slice_angle = 2 * math.pi / count
    size = js_round(ICON_SIZE * scale)
    menu = []
    for index in range(count):
        title = titles[index] if index < len(titles) else ""
        if not title:
            continue
        angle = (index + 0.5) * slice_angle - math.pi / 2
        menu.append({
            "title": title,
            "configured": _configured_icon(icons, index),
            "x": js_round((DIAL_R + math.cos(angle) * ICON_R) * scale - size / 2),
            "y": js_round((DIAL_R + math.sin(angle) * ICON_R) * scale - size / 2),
            "size": size,
            "color": skin["palette"]["iconOnColor"] if title == active else skin["palette"]["icon"],
        })

    center = None
    hovered = bool(state["title"]) and state["title"] != "Menu" and not selected
    if selected or hovered:
        index = titles.index(state["title"]) if state["title"] in titles else -1
        center_size = js_round(CENTER_ICON_SIZE * scale)
        offset = 34 if selected else 26
        configured = _configured_icon(icons, index)
        if submenu:
            configured = submenu["icons"][submenu["selected"]]
        # A function of a group is not in the menu; the driver sends its icon.
        elif selected and isinstance(view["details"].get("icon"), str):
            configured = view["details"]["icon"]
        center = {
            "title": state["title"],
            "configured": configured,
            "x": js_round(DIAL_R * scale - center_size / 2),
            "y": js_round((DIAL_R - offset) * scale - center_size / 2),
            "size": center_size,
            "color": function_color(view) if selected else active_color(view),
        }
    return {"menu": menu, "menuVisible": not selected, "center": center}


def pointer_placement(view):
    """pointerPlacement(): centre of the finger dot in unscaled dial units
    and its colour, or None when no dot is shown."""
    # A missing value is undefined in JavaScript: NaN, unlike null (0).
    pointer = js_number(view["details"].get("pointer", math.nan))
    if not view["appearance"].get("show_pointer") or not view["state"]["touching"] or not pointer >= 0:
        return None
    selected = is_selected_mode(view["state"])
    radius = GAUGE_R if selected else HIGHLIGHT_R
    angle = pointer * math.pi / 180 - math.pi / 2
    return {
        "x": DIAL_R + math.cos(angle) * radius,
        "y": DIAL_R + math.sin(angle) * radius,
        "color": function_color(view) if selected else view["skin"]["palette"]["pointer"],
    }


def content_key(view) -> str:
    """contentKey(): everything the content layer depends on besides the
    skin and the overlay settings; equal keys paint equal content."""
    state, details = view["state"], view["details"]
    return json.dumps([
        state["enabled"], state["title"], state["titles"], state["menuTitles"], state["value"],
        state["valueAngleStart"], state["unit"], state["centerPressed"], state["valueShowOnlyProgress"],
        details.get("profile"), details.get("mode"), details.get("colors"), details.get("color"),
        details.get("hints"), details.get("parent"), details.get("submenu"),
    ], default=str)


def _list_row(row) -> dict:
    """listRow(): top left corner of a row of the list and its size, unscaled."""
    return {
        "x": LIST_MARGIN + LIST_PAD,
        "y": LIST_MARGIN + LIST_HEADER_H + row * LIST_ROW_H,
        "width": LIST_W - 2 * LIST_PAD,
        "height": LIST_ROW_H - 4,
    }


def list_row_faded(submenu, row) -> bool:
    """listRowFaded(): rows hidden above or below fade the row at that edge."""
    return ((row == 0 and submenu["first"] > 0)
            or (row == submenu["rows"] - 1 and submenu["first"] + submenu["rows"] < len(submenu["items"])))


def submenu_layout(view, scale=None):
    """submenuLayout(): the list's icons relative to its top left corner,
    scaled (scale from submenu_placement()); None without an open list."""
    submenu = open_submenu(view)
    if not submenu:
        return None
    scale = view["appearance"]["scale"] if scale is None else scale
    palette = view["skin"]["palette"]
    size = js_round(LIST_ICON_SIZE * scale)
    rows = []
    for row in range(submenu["rows"]):
        position = submenu["first"] + row
        box = _list_row(row)
        r, g, b, a = palette["iconOnColor"] if position == submenu["selected"] else palette["icon"]
        rows.append({
            "title": submenu["items"][position],
            "configured": submenu["icons"][position],
            "x": js_round((box["x"] + 22) * scale - size / 2),
            "y": js_round((box["y"] + box["height"] / 2) * scale - size / 2),
            "size": size,
            "color": [r, g, b, a * (0.4 if list_row_faded(submenu, row) else 1)],
        })
    return {"rows": rows}


def submenu_key(view, side) -> str:
    """submenuKey(): everything the list's picture depends on besides the
    skin and the scale."""
    submenu = open_submenu(view)
    return json.dumps([submenu, side, view["appearance"].get("show_hints"), view["details"].get("colors")]
                      if submenu else None, default=str)


# --- easing (Clutter.AnimationMode) ------------------------------------------

def ease_out_quad(t: float) -> float:
    return t * (2 - t)


def ease_in_quad(t: float) -> float:
    return t * t


def ease_in_out_quad(t: float) -> float:
    return 2 * t * t if t < 0.5 else -1 + (4 - 2 * t) * t


def ease_out_cubic(t: float) -> float:
    return (t - 1) ** 3 + 1
