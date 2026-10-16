"""Cairo painting of the on-screen dial, independent of any toolkit.

A port of gnome/extension/dial.js (keep geometry and drawing order in sync)
used by the settings app previews and meant for overlays on other desktops:
they get the same look by calling paint_dial() on any Cairo context. Icons
are drawn by a callback, e.g. overlay.gtk_icons.draw_icon for GTK.
"""

import math

import cairo

from config.labels import icon_for_title
from config.skins import parse_color

DIAL_D = 360
DIAL_R = DIAL_D / 2
OUTER_R = 162
ICON_R = 113
BUBBLE_R = 27
HIGHLIGHT_R = 152
GAUGE_R = 136
GAUGE_W = 11
CENTER_R = 70
ICON_SIZE = 20
CENTER_ICON_SIZE = 26
GAUGE_START = 0.75 * math.pi
GAUGE_SWEEP = 1.5 * math.pi
# The disc with its shadow, the area a preview has to fit.
PAINTED_D = 2 * (OUTER_R + 20)
FONT = "Adwaita Sans"
DEFAULT_ACCENT = (0.906, 0.725, 0.553, 1)


def _rgb(text, fallback=DEFAULT_ACCENT):
    return parse_color(text, fallback)


def _no_icon(_cr, _name, _x, _y, _size, _color):
    pass


class DialView:
    """What to paint: menu titles and colours, the highlighted or selected
    function and a resolved skin from config.skins.resolve_skin()."""

    def __init__(self, skin, titles, colors, accent="#e7b98d", icons=None, title="",
                 selected=False, value=None, unit="", profile="", pointer=None):
        self.skin = skin
        self.palette = skin["palette"]
        self.titles = list(titles)
        self.colors = [_rgb(color) for color in colors]
        self.icons = list(icons or [""] * len(self.titles))
        self.accent = _rgb(accent)
        self.title = title or ""
        self.selected = selected
        self.value = value
        self.unit = unit or ""
        self.profile = profile or ""
        self.pointer = pointer

    @property
    def count(self):
        return max(len(self.titles), 4)

    def color_of(self, title):
        if title in self.titles:
            index = self.titles.index(title)
            if index < len(self.colors):
                return self.colors[index]
        return self.accent


def paint_dial(cr, view, x, y, size, draw_icon=None):
    """Paint the dial scaled to fit a size × size square at x, y.

    draw_icon(cr, icon_name, x, y, size, rgba) paints a symbolic icon; without
    it the dial has no icons.
    """
    draw_icon = draw_icon or _no_icon
    scale = size / PAINTED_D
    cr.save()
    cr.translate(x + size / 2 - DIAL_R * scale, y + size / 2 - DIAL_R * scale)
    cr.scale(scale, scale)
    _surface(cr, view)
    if view.selected:
        _gauge(cr, view)
    elif view.skin["menu"] == "segments":
        _segments(cr, view)
    else:
        _bubbles(cr, view)
    if not view.selected:
        _menu_icons(cr, view, draw_icon)
    _center(cr, view, draw_icon)
    cr.restore()


def hit_function(view, x, y, size):
    """Index of the menu function under a point of the preview, or None."""
    scale = size / PAINTED_D
    dx, dy = (x - size / 2) / scale, (y - size / 2) / scale
    distance = math.hypot(dx, dy)
    if not CENTER_R <= distance <= OUTER_R:
        return None
    angle = (math.degrees(math.atan2(dy, dx)) + 90) % 360
    index = min(int(angle // (360 / view.count)), view.count - 1)
    return index if index < len(view.titles) and view.titles[index] else None


def _slices(view):
    slice_angle = 2 * math.pi / view.count
    for index in range(view.count):
        label = view.titles[index] if index < len(view.titles) else ""
        start = index * slice_angle - math.pi / 2
        yield index, label, bool(label) and label == view.title, start, start + slice_angle, start + slice_angle / 2


def _wedge(cr, inner, outer, start, end):
    cr.new_path()
    cr.move_to(DIAL_R + math.cos(start) * inner, DIAL_R + math.sin(start) * inner)
    cr.arc(DIAL_R, DIAL_R, outer, start, end)
    cr.arc_negative(DIAL_R, DIAL_R, inner, end, start)
    cr.close_path()


def _radial(cr, x, y, inner, outer, alpha):
    gradient = cairo.RadialGradient(x, y, inner, x, y, outer)
    gradient.add_color_stop_rgba(0, 0, 0, 0, alpha)
    gradient.add_color_stop_rgba(1, 0, 0, 0, 0)
    cr.arc(x, y, outer, 0, 2 * math.pi)
    cr.set_source(gradient)
    cr.fill()


def _linear(cr, top, bottom, first, second):
    gradient = cairo.LinearGradient(DIAL_R, top, DIAL_R, bottom)
    gradient.add_color_stop_rgba(0, *first)
    gradient.add_color_stop_rgba(1, *second)
    return gradient


def _surface(cr, view):
    palette = view.palette
    _radial(cr, DIAL_R, DIAL_R + 4, OUTER_R - 6, OUTER_R + 16, palette["shadow"])
    cr.arc(DIAL_R, DIAL_R, OUTER_R, 0, 2 * math.pi)
    cr.set_source(_linear(cr, DIAL_R - OUTER_R, DIAL_R + OUTER_R, palette["surfaceTop"], palette["surfaceBottom"]))
    cr.fill()
    cr.arc(DIAL_R, DIAL_R, OUTER_R - 0.5, 0, 2 * math.pi)
    cr.set_line_width(1)
    cr.set_source_rgba(*palette["rim"])
    cr.stroke()


def _bubbles(cr, view):
    palette = view.palette
    cr.set_line_cap(1)  # round
    for index, label, active, start, end, mid in _slices(view):
        x = DIAL_R + math.cos(mid) * ICON_R
        y = DIAL_R + math.sin(mid) * ICON_R
        if not label:
            cr.new_path()
            cr.arc(x, y, 3, 0, 2 * math.pi)
            cr.set_source_rgba(*palette["freeSlot"])
            cr.fill()
            continue
        color = view.color_of(label)
        if active:
            _wedge(cr, CENTER_R + 8, OUTER_R - 3, start + 0.06, end - 0.06)
            cr.set_source_rgba(color[0], color[1], color[2], 0.07)
            cr.fill()
            cr.new_path()
            cr.set_line_width(4)
            cr.set_source_rgba(*color)
            cr.arc(DIAL_R, DIAL_R, HIGHLIGHT_R, start + 0.1, end - 0.1)
            cr.stroke()
        cr.new_path()
        cr.arc(x, y, BUBBLE_R, 0, 2 * math.pi)
        if active:
            cr.set_source_rgba(*color)
            cr.fill()
        else:
            cr.set_source_rgba(*palette["bubble"])
            cr.fill()
            cr.arc(x, y, BUBBLE_R - 0.75, mid + math.pi - 0.55, mid + math.pi + 0.55)
            cr.set_line_width(1.5)
            cr.set_source_rgba(color[0], color[1], color[2], 0.75)
            cr.stroke()
    _pointer(cr, view, HIGHLIGHT_R, palette["pointer"])


def _segments(cr, view):
    palette = view.palette
    inner, outer = CENTER_R + 8, OUTER_R - 6
    for _index, label, active, start, end, _mid in _slices(view):
        start, end = start + 0.02, end - 0.02
        _wedge(cr, inner, outer, start, end)
        if not label:
            cr.set_source_rgba(*palette["freeSlot"])
            cr.fill()
            continue
        color = view.color_of(label)
        cr.set_source_rgba(*(color if active else palette["segment"]))
        cr.fill()
        if not active:
            cr.new_path()
            cr.arc(DIAL_R, DIAL_R, inner + 3, start + 0.04, end - 0.04)
            cr.set_line_width(3)
            cr.set_source_rgba(*color)
            cr.stroke()
    _pointer(cr, view, HIGHLIGHT_R, palette["pointer"])


def _menu_icons(cr, view, draw_icon):
    for index, label, active, _start, _end, mid in _slices(view):
        if not label:
            continue
        x = DIAL_R + math.cos(mid) * ICON_R - ICON_SIZE / 2
        y = DIAL_R + math.sin(mid) * ICON_R - ICON_SIZE / 2
        name = view.icons[index] if index < len(view.icons) and view.icons[index] else icon_for_title(label)
        draw_icon(cr, name, x, y, ICON_SIZE, view.palette["iconOnColor" if active else "icon"])


def _gauge(cr, view):
    palette = view.palette
    color = view.color_of(view.title)
    cr.set_line_cap(1)
    cr.set_line_width(GAUGE_W)
    if view.unit == "%" and view.value is not None:
        cr.new_path()
        cr.set_source_rgba(*palette["track"])
        cr.arc(DIAL_R, DIAL_R, GAUGE_R, GAUGE_START, GAUGE_START + GAUGE_SWEEP)
        cr.stroke()
        fraction = max(0, min(1, view.value / 100))
        if fraction > 0.005:
            cr.set_source_rgba(*color)
            cr.arc(DIAL_R, DIAL_R, GAUGE_R, GAUGE_START, GAUGE_START + fraction * GAUGE_SWEEP)
            cr.stroke()
    else:
        cr.new_path()
        cr.set_source_rgba(*palette["track"])
        cr.arc(DIAL_R, DIAL_R, GAUGE_R, 0, 2 * math.pi)
        cr.stroke()
        cr.set_line_width(2)
        for index in range(24):
            angle = index / 24 * 2 * math.pi
            cr.move_to(DIAL_R + math.cos(angle) * (GAUGE_R - 3), DIAL_R + math.sin(angle) * (GAUGE_R - 3))
            cr.line_to(DIAL_R + math.cos(angle) * (GAUGE_R + 3), DIAL_R + math.sin(angle) * (GAUGE_R + 3))
        cr.set_source_rgba(*palette["detent"])
        cr.stroke()
    _pointer(cr, view, GAUGE_R, color)


def _pointer(cr, view, radius, color):
    if view.pointer is None:
        return
    angle = math.radians(view.pointer) - math.pi / 2
    x = DIAL_R + math.cos(angle) * radius
    y = DIAL_R + math.sin(angle) * radius
    glow = cairo.RadialGradient(x, y, 2, x, y, 15)
    glow.add_color_stop_rgba(0, color[0], color[1], color[2], 0.55)
    glow.add_color_stop_rgba(1, color[0], color[1], color[2], 0)
    cr.new_path()
    cr.arc(x, y, 15, 0, 2 * math.pi)
    cr.set_source(glow)
    cr.fill()
    cr.arc(x, y, 5.5, 0, 2 * math.pi)
    cr.set_source_rgba(*view.palette["pointer"])
    cr.fill()


def _center(cr, view, draw_icon):
    palette = view.palette
    _radial(cr, DIAL_R, DIAL_R + 2, CENTER_R - 4, CENTER_R + 10, palette["shadow"] * 0.75)
    cr.arc(DIAL_R, DIAL_R, CENTER_R, 0, 2 * math.pi)
    cr.set_source(_linear(cr, DIAL_R - CENTER_R, DIAL_R + CENTER_R, palette["centerTop"], palette["centerBottom"]))
    cr.fill()
    cr.arc(DIAL_R, DIAL_R, CENTER_R - 0.5, 0, 2 * math.pi)
    cr.set_line_width(1)
    cr.set_source_rgba(*palette["rim"])
    cr.stroke()

    title = view.title
    profile = view.profile.upper()
    color = view.color_of(title)
    if view.selected:
        index = view.titles.index(title) if title in view.titles else -1
        icon = view.icons[index] if index >= 0 and view.icons[index] else icon_for_title(title)
        draw_icon(cr, icon, DIAL_R - CENTER_ICON_SIZE / 2, DIAL_R - 34 - CENTER_ICON_SIZE / 2, CENTER_ICON_SIZE, color)
        _text(cr, _truncate(title, 14), DIAL_R + 2, 13 if len(title) > 10 else 16, palette["text"], True)
        if view.unit and view.value is not None:
            _text(cr, f"{view.value}{view.unit}", DIAL_R + 27, 18, color, True)
        elif profile:
            _text(cr, _truncate(profile, 16), DIAL_R + 26, 8.5, palette["muted"], False)
    elif title:
        index = view.titles.index(title) if title in view.titles else -1
        icon = view.icons[index] if index >= 0 and view.icons[index] else icon_for_title(title)
        draw_icon(cr, icon, DIAL_R - CENTER_ICON_SIZE / 2, DIAL_R - 26 - CENTER_ICON_SIZE / 2, CENTER_ICON_SIZE, color)
        _text(cr, _truncate(title, 14), DIAL_R + 10, 13 if len(title) > 10 else 16, palette["text"], True)
        _text(cr, "Release to select", DIAL_R + 32, 8.5, palette["muted"], False)
    else:
        _text(cr, _truncate(profile or "DIAL", 14), DIAL_R - 8, 11 if len(profile) > 10 else 13, palette["text"], True)
        _text(cr, "Choose a function", DIAL_R + 14, 9, palette["muted"], False)


def _truncate(text, length):
    text = str(text or "")
    return text[: length - 1] + "…" if len(text) > length else text


def _text(cr, text, y, size, color, bold):
    cr.save()
    cr.select_font_face(FONT, 0, 1 if bold else 0)
    cr.set_font_size(size)
    extents = cr.text_extents(text)
    cr.move_to(DIAL_R - extents.width / 2 - extents.x_bearing, y + extents.height / 2)
    cr.set_source_rgba(*color)
    cr.show_text(text)
    cr.restore()
