"""Skins of the on-screen dial.

Built-in skins live in ``gnome/extension/skins.json`` (shipped with the Shell
extension); each ``~/.config/asus-turnpad/skins/<id>.json`` adds or replaces
one. The format is described in ``SKINS.md``. Resolution mirrors
``resolveSkin()`` in ``gnome/extension/dial.js``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from config.schema import CONFIG_DIR

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILTIN_SKINS_FILE = PROJECT_ROOT / "gnome" / "extension" / "skins.json"
SKINS_DIR = CONFIG_DIR / "skins"
DEFAULT_SKIN = "glass"
MENU_STYLES = ("bubbles", "segments")
# Twins of DIAL_SHAPES, TILE_SHAPES and the limits in dial.js.
DIAL_SHAPES = ("circle", "square", "octagon", "knurled", "scalloped", "custom")
TILE_SHAPES = ("circle", "square", "diamond", "hexagon")
TILE_SIZE_MIN, TILE_SIZE_MAX = 0.75, 1.25
OUTLINE_POINTS_MIN, OUTLINE_POINTS_MAX = 3, 24
OUTLINE_RADIUS_MIN = 0.5
# Points may reach the corners of the dial's square (half its width is
# OUTLINE_BOX times the radius), so a full-size square fits.
OUTLINE_BOX = 1.08


def outline_limit(index: int, count: int) -> float:
    """Farthest a point at this position may go, as a fraction of the radius."""
    import math

    angle = index / count * 2 * math.pi - math.pi / 2
    return min(1.5, OUTLINE_BOX / max(abs(math.cos(angle)), abs(math.sin(angle))))
# A background picture is a PNG next to the skin file, named plainly.
IMAGE_NAME = re.compile(r"^[\w.-]+\.png$", re.IGNORECASE)
# Loaders note each skin file's directory here; never saved.
DIR_KEY = "__dir"

# Every colour a skin can set, in the order the editor shows them, with a
# label and what it paints. "shadow" is a number from 0 to 1, the rest are
# colours.
PALETTE_KEYS = (
    ("surfaceTop", "Disc, top", "Top of the disc gradient"),
    ("surfaceBottom", "Disc, bottom", "Bottom of the disc gradient and the hint bar"),
    ("rim", "Rim", "Thin outline of the disc, the centre and the hint bar"),
    ("bubble", "Function bubble", "Background of a function in the bubble menu"),
    ("segment", "Function sector", "Background of a function in the sector menu"),
    ("freeSlot", "Free slot", "Dot or sector where no function is assigned"),
    ("track", "Gauge track", "Unfilled part of the level gauge and the wheel"),
    ("detent", "Wheel notches", "Notches of endless functions such as Zoom"),
    ("centerTop", "Centre, top", "Top of the centre button gradient"),
    ("centerBottom", "Centre, bottom", "Bottom of the centre button gradient"),
    ("text", "Text", "Function and profile names"),
    ("muted", "Secondary text", "Hints such as “Release to select”"),
    ("icon", "Icons", "Function icons in the menu"),
    ("iconOnColor", "Icon on colour", "Icon of the highlighted function, drawn on its colour"),
    ("pointer", "Finger dot", "Dot that follows the finger around the ring"),
    ("shadow", "Shadow strength", "Opacity of the shadow under the disc, 0 to 1"),
)
COLOR_KEYS = tuple(key for key, _label, _help in PALETTE_KEYS if key != "shadow")

FALLBACK_SKIN = {
    "name": "Dark glass",
    "menu": "bubbles",
    "shape": "circle",
    "tile": "circle",
    "tileSize": 1,
    "palette": {
        "surfaceTop": [0.17, 0.175, 0.205, 0.97],
        "surfaceBottom": [0.085, 0.09, 0.105, 0.97],
        "rim": [1, 1, 1, 0.09],
        "bubble": [1, 1, 1, 0.07],
        "segment": [1, 1, 1, 0.06],
        "track": [1, 1, 1, 0.08],
        "detent": [1, 1, 1, 0.16],
        "freeSlot": [1, 1, 1, 0.14],
        "centerTop": [0.205, 0.21, 0.245, 1],
        "centerBottom": [0.125, 0.13, 0.15, 1],
        "text": [0.96, 0.95, 0.93, 1],
        "muted": [0.70, 0.69, 0.67, 1],
        "icon": [0.86, 0.85, 0.83, 0.85],
        "iconOnColor": [0.08, 0.08, 0.09, 1],
        "pointer": [1, 1, 1, 0.95],
        "shadow": 0.45,
    },
}

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$")


def parse_color(value, fallback):
    """[r, g, b(, a)] with 0–1 channels or "#rrggbb(aa)" → (r, g, b, a)."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            channels = [max(0.0, min(1.0, float(channel))) for channel in value[:4]]
        except (TypeError, ValueError):
            return tuple(fallback)
        if len(channels) == 3:
            channels.append(1.0)
        return tuple(channels)
    match = _HEX.match(str(value if value is not None else "").strip())
    if not match:
        return tuple(fallback)
    number = int(match.group(1), 16)
    alpha = int(match.group(2), 16) / 255 if match.group(2) else 1.0
    return ((number >> 16 & 255) / 255, (number >> 8 & 255) / 255, (number & 255) / 255, alpha)


def color_to_hex(color) -> str:
    """(r, g, b, a) → "#rrggbb", or "#rrggbbaa" when not opaque."""
    red, green, blue, alpha = (round(max(0.0, min(1.0, channel)) * 255) for channel in color)
    text = f"#{red:02x}{green:02x}{blue:02x}"
    return text if alpha == 255 else f"{text}{alpha:02x}"


def _read(path: Path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def builtin_skins() -> dict:
    skins = _read(BUILTIN_SKINS_FILE)
    if not isinstance(skins, dict):
        return {DEFAULT_SKIN: FALLBACK_SKIN}
    return {key: {**skin, DIR_KEY: str(BUILTIN_SKINS_FILE.parent)} for key, skin in skins.items() if isinstance(skin, dict)}


def user_skins(directory: Path | None = None) -> dict:
    directory = directory or SKINS_DIR
    skins = {}
    if not directory.is_dir():
        return skins
    for path in sorted(directory.glob("*.json")):
        skin = _read(path)
        if isinstance(skin, dict):
            skins[path.stem] = {**skin, DIR_KEY: str(directory)}
    return skins


def without_private_keys(skin: dict) -> dict:
    """The skin as it is saved: no loader notes such as its directory."""
    return {key: value for key, value in skin.items() if not str(key).startswith("__")}


def load_skins(directory: Path | None = None) -> dict:
    """Built-in skins followed by the user's; a user file wins on the same id."""
    skins = dict(builtin_skins())
    skins.update(user_skins(directory))
    return skins


def resample_outline(points: list[float], count: int) -> list[float]:
    """The same outline with another number of points (linear in angle)."""
    count = max(OUTLINE_POINTS_MIN, min(OUTLINE_POINTS_MAX, count))
    source = len(points)
    result = []
    for index in range(count):
        position = index / count * source
        left = int(position) % source
        right = (left + 1) % source
        weight = position - int(position)
        result.append(round(points[left] * (1 - weight) + points[right] * weight, 2))
    return result


def mirror_index(index: int, count: int) -> int:
    """The point mirrored across the vertical axis through the top point."""
    return (count - index) % count


def resolve_outline(outline) -> dict | None:
    """{"points": [radius fractions clockwise from the top], "smooth": bool} or None."""
    if not isinstance(outline, dict) or not isinstance(outline.get("points"), list):
        return None
    try:
        points = [float(point) for point in outline["points"]]
    except (TypeError, ValueError):
        return None
    if not OUTLINE_POINTS_MIN <= len(points) <= OUTLINE_POINTS_MAX or any(point != point for point in points):
        return None
    return {
        "points": [
            max(OUTLINE_RADIUS_MIN, min(outline_limit(index, len(points)), point))
            for index, point in enumerate(points)
        ],
        "smooth": outline.get("smooth") is not False,
    }


def resolve_skin(skins: dict, skin_id: str) -> dict:
    """{"menu", "shape", "tile", "tileSize", "outline", "background",
    "palette": {key: (r, g, b, a) | shadow float}}.

    Follows "base" links, then fills anything missing from the fallback, so a
    partial or broken skin still paints. "background" is {"path", "opacity"}
    with the picture found next to the skin file, or None.
    """
    chain = []
    current = skins.get(skin_id) or skins.get(DEFAULT_SKIN)
    while isinstance(current, dict) and current not in chain and len(chain) < 8:
        chain.insert(0, current)
        current = skins.get(current.get("base"))

    menu = FALLBACK_SKIN["menu"]
    shape, tile, tile_size = FALLBACK_SKIN["shape"], FALLBACK_SKIN["tile"], FALLBACK_SKIN["tileSize"]
    outline = background = None
    palette = {
        key: (value if key == "shadow" else parse_color(value, (1, 1, 1, 1)))
        for key, value in FALLBACK_SKIN["palette"].items()
    }
    for skin in chain:
        if skin.get("menu") in MENU_STYLES:
            menu = skin["menu"]
        if skin.get("shape") in DIAL_SHAPES:
            shape = skin["shape"]
        if skin.get("tile") in TILE_SHAPES:
            tile = skin["tile"]
        if isinstance(skin.get("tileSize"), (int, float)) and not isinstance(skin.get("tileSize"), bool):
            tile_size = max(TILE_SIZE_MIN, min(TILE_SIZE_MAX, float(skin["tileSize"])))
        outline = resolve_outline(skin.get("outline")) or outline
        if "background" in skin and skin["background"] is None:
            background = None
        elif isinstance(skin.get("background"), dict) and skin.get(DIR_KEY):
            image = str(skin["background"].get("image") or "")
            if IMAGE_NAME.match(image):
                try:
                    opacity = max(0.0, min(1.0, float(skin["background"].get("opacity", 1))))
                except (TypeError, ValueError):
                    opacity = 1.0
                background = {"path": str(Path(skin[DIR_KEY]) / image), "opacity": opacity}
        colours = skin.get("palette") if isinstance(skin.get("palette"), dict) else {}
        for key in palette:
            if key not in colours:
                continue
            if key == "shadow":
                try:
                    palette["shadow"] = max(0.0, min(1.0, float(colours["shadow"])))
                except (TypeError, ValueError):
                    pass
            else:
                palette[key] = parse_color(colours[key], palette[key])
    if shape == "custom" and outline is None:
        shape = "circle"
    return {
        "menu": menu, "shape": shape, "tile": tile, "tileSize": tile_size,
        "outline": outline, "background": background, "palette": palette,
    }


def skin_name(skins: dict, skin_id: str) -> str:
    skin = skins.get(skin_id)
    return str(skin.get("name") or skin_id) if isinstance(skin, dict) else skin_id


def is_builtin(skin_id: str) -> bool:
    return skin_id in builtin_skins()


def new_skin_id(name: str, existing) -> str:
    """A file-name-safe id from the skin name that clashes with nothing."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "skin"
    candidate, index = base, 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def save_user_skin(skin_id: str, skin: dict, directory: Path | None = None) -> Path:
    directory = directory or SKINS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{skin_id}.json"
    temporary = path.with_suffix(".json.tmp")
    with open(temporary, "w") as handle:
        json.dump(skin, handle, indent=4)
        handle.write("\n")
    # Atomic, like config.json: the Shell extension watches this directory.
    temporary.replace(path)
    return path


def delete_user_skin(skin_id: str, directory: Path | None = None) -> None:
    path = (directory or SKINS_DIR) / f"{skin_id}.json"
    if path.exists():
        path.unlink()


def format_description() -> str:
    """The skin file format in plain words, for SKINS.md and AI prompts."""
    lines = [
        "A skin is one JSON object:",
        '- "name": shown in the settings app.',
        '- "description": optional, one line.',
        '- "base": optional id of another skin (built-in: '
        + ", ".join(builtin_skins())
        + "); colours left out are taken from it.",
        '- "menu": "bubbles" (round icon buttons) or "segments" (a ring of sectors).',
        '- "shape": outline of the disc: ' + ", ".join(f'"{shape}"' for shape in DIAL_SHAPES) + ".",
        '- "outline": for "shape": "custom": {"points": [...], "smooth": true|false}. 3 to 24 numbers, '
        "the distance of each point from the centre as a fraction of the radius, at equal angles clockwise "
        "from the top; 0.5 to 1.08 (up to 1.5 towards the corners, e.g. [1, 1.41, 1, 1.41, 1, 1.41, 1, 1.41] "
        "with smooth false is a square).",
        '- "tile": shape of each function in the bubble menu: ' + ", ".join(f'"{tile}"' for tile in TILE_SHAPES) + ".",
        f'- "tileSize": {TILE_SIZE_MIN} to {TILE_SIZE_MAX}, 1 is the standard size.',
        '- "background": {"image": "name.png", "opacity": 0 to 1}: a PNG in the skins folder that covers '
        "the disc, cut to its shape; null removes the base skin's picture.",
        '- "palette": colours as "#rrggbb" or "#rrggbbaa" (aa = opacity, 00–ff), '
        "or [r, g, b, a] with channels from 0 to 1:",
    ]
    lines += [f'  - "{key}": {help_text}' for key, _label, help_text in PALETTE_KEYS]
    lines.append(
        "Function colours (Volume blue, Zoom champagne…) and the accent colour are "
        "set per function, not by the skin; keep icons and text readable on the disc."
    )
    return "\n".join(lines)


def ai_prompt(skin: dict) -> str:
    """Instructions an assistant needs to edit or invent a skin."""
    return (
        "Design a skin for the on-screen dial of Turnpad, the ASUS DialPad driver "
        "(a radial menu drawn over the desktop, 360 px across).\n\n"
        + format_description()
        + "\n\nReply with only the JSON object. Start from this skin and change it as I describe:\n\n"
        + json.dumps(skin, indent=4)
        + "\n\nMy idea: "
    )
