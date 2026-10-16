"""Skins of the on-screen dial.

Built-in skins live in ``gnome/extension/skins.json`` (shipped with the Shell
extension); each ``~/.config/asus-dialpad/skins/<id>.json`` adds or replaces
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
    return skins if isinstance(skins, dict) else {DEFAULT_SKIN: FALLBACK_SKIN}


def user_skins(directory: Path | None = None) -> dict:
    directory = directory or SKINS_DIR
    skins = {}
    if not directory.is_dir():
        return skins
    for path in sorted(directory.glob("*.json")):
        skin = _read(path)
        if isinstance(skin, dict):
            skins[path.stem] = skin
    return skins


def load_skins(directory: Path | None = None) -> dict:
    """Built-in skins followed by the user's; a user file wins on the same id."""
    skins = dict(builtin_skins())
    skins.update(user_skins(directory))
    return skins


def resolve_skin(skins: dict, skin_id: str) -> dict:
    """{"menu": ..., "palette": {key: (r, g, b, a) | shadow float}}.

    Follows "base" links, then fills anything missing from the fallback, so a
    partial or broken skin still paints.
    """
    chain = []
    current = skins.get(skin_id) or skins.get(DEFAULT_SKIN)
    while isinstance(current, dict) and current not in chain and len(chain) < 8:
        chain.insert(0, current)
        current = skins.get(current.get("base"))

    menu = FALLBACK_SKIN["menu"]
    palette = {
        key: (value if key == "shadow" else parse_color(value, (1, 1, 1, 1)))
        for key, value in FALLBACK_SKIN["palette"].items()
    }
    for skin in chain:
        if skin.get("menu") in MENU_STYLES:
            menu = skin["menu"]
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
    return {"menu": menu, "palette": palette}


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
        "Design a skin for the on-screen dial of the ASUS DialPad driver "
        "(a round radial menu drawn over the desktop, 360 px across).\n\n"
        + format_description()
        + "\n\nReply with only the JSON object. Start from this skin and change it as I describe:\n\n"
        + json.dumps(skin, indent=4)
        + "\n\nMy idea: "
    )
