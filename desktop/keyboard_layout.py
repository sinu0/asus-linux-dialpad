"""The keyboard layouts the desktop is set to, as XKB rule names (RMLVO).

On Wayland the driver normally reads the compositor's keymap through
pywayland. Without pywayland (it needs a compiler to install) it compiles a
keymap from these names instead: GNOME's input sources, else the system
layout from localectl (X11 Layout), else XKB_DEFAULT_* from the
environment, else "us". GNOME's sources keep their order, so a source's
index is its layout index, as the driver's GNOME layout switching expects.
"""

from __future__ import annotations

import ast
import logging
import os
import subprocess

from config.identity import SLUG

log = logging.getLogger(SLUG)

GNOME_SCHEMA = "org.gnome.desktop.input-sources"
# XKB groups in one keymap; GNOME Shell splits longer lists the same way.
MAX_LAYOUTS = 4
FALLBACK = {"layout": "us"}
NAME_KEYS = ("rules", "model", "layout", "variant", "options")


def _gvariant_list(text):
    """A gsettings list ("[('xkb', 'pl')]", "@as []") as Python."""
    text = (text or "").strip()
    if text.startswith("@"):
        text = text.split(" ", 1)[1] if " " in text else ""
    try:
        value = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return []
    return list(value) if isinstance(value, (list, tuple)) else []


def from_gnome(sources_text, options_text=""):
    """Names from `gsettings get org.gnome.desktop.input-sources sources`
    (and xkb-options); None without an xkb source. Input methods (ibus)
    keep their place with "us", so indices still match GNOME's."""
    sources = [s for s in _gvariant_list(sources_text) if isinstance(s, (list, tuple)) and len(s) == 2]
    if not any(kind == "xkb" for kind, _ in sources):
        return None
    layouts, variants = [], []
    for kind, source_id in sources[:MAX_LAYOUTS]:
        layout, _, variant = str(source_id).partition("+") if kind == "xkb" else ("us", "", "")
        layouts.append(layout)
        variants.append(variant)
    names = {"layout": ",".join(layouts)}
    if any(variants):
        names["variant"] = ",".join(variants)
    options = [str(o) for o in _gvariant_list(options_text)]
    if options:
        names["options"] = ",".join(options)
    return names


def from_localectl(text):
    """Names from `localectl status` (X11 Layout/Model/Variant/Options)."""
    fields = {}
    for line in (text or "").splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().startswith("X11 "):
            fields[key.strip()[4:].lower()] = value.strip()
    if not fields.get("layout"):
        return None
    return {key: fields[key] for key in ("model", "layout", "variant", "options") if fields.get(key)}


def from_environment(environ):
    """Names from XKB_DEFAULT_RULES/MODEL/LAYOUT/VARIANT/OPTIONS."""
    if not environ.get("XKB_DEFAULT_LAYOUT"):
        return None
    return {key: environ[f"XKB_DEFAULT_{key.upper()}"] for key in NAME_KEYS if environ.get(f"XKB_DEFAULT_{key.upper()}")}


def _output(command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=5, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def gnome_names():
    sources = _output(["gsettings", "get", GNOME_SCHEMA, "sources"])
    if sources is None:
        return None
    return from_gnome(sources, _output(["gsettings", "get", GNOME_SCHEMA, "xkb-options"]) or "")


def rule_names(environ=None):
    """(names, where they came from); names are keyword arguments for
    xkb.Context.keymap_new_from_names()."""
    environ = os.environ if environ is None else environ
    for source, read in (
        ("GNOME input sources", gnome_names),
        ("localectl", lambda: from_localectl(_output(["localectl", "status"]))),
        ("XKB_DEFAULT_* environment", lambda: from_environment(environ)),
    ):
        try:
            names = read()
        except Exception:
            log.debug("Reading the keyboard layout from %s failed", source, exc_info=True)
            names = None
        if names:
            return names, source
    return dict(FALLBACK), "default"
