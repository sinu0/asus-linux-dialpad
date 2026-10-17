"""Cairo painting of the on-screen dial, independent of any toolkit.

A port of gnome/extension/dial.js (keep geometry and drawing order in sync)
used by the settings app previews and meant for overlays on other desktops:
they get the same look by calling paint_dial() on any Cairo context. Icons
are drawn by a callback, e.g. overlay.gtk_icons.draw_icon for GTK.
"""

import math
import os

import cairo

from config.labels import icon_for_title
from config.skins import parse_color
from overlay import look

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
# A group's list beside the dial (twins of the LIST_* constants in dial.js).
LIST_W = 232
LIST_ROW_H = 40
LIST_HEADER_H = 34
LIST_FOOTER_H = 22
LIST_PAD = 8
LIST_MARGIN = 12
LIST_RADIUS = 18
LIST_ICON_SIZE = 18
LIST_ROWS_MAX = 7
LIST_FOOTER = "Turn: move  ·  Tap centre: choose  ·  Hold: back"


def _rgb(text, fallback=DEFAULT_ACCENT):
    return parse_color(text, fallback)


def _no_icon(_cr, _name, _x, _y, _size, _color):
    pass


class DialView:
    """What to paint: menu titles and colours, the highlighted or selected
    function and a resolved skin from config.skins.resolve_skin()."""

    def __init__(self, skin, titles, colors, accent="#e7b98d", icons=None, title="",
                 selected=False, value=None, unit="", profile="", pointer=None, submenu=None):
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
        # An open group's list, as the driver sends it: title, items,
        # icons, colors and selected; the title is then the highlighted item.
        self.submenu = submenu

    @property
    def count(self):
        return max(len(self.titles), 4)

    def color_at(self, index):
        """Colour of the function at a menu position."""
        return self.color_of(self.titles[index])

    def color_of(self, title):
        if title in self.titles:
            index = self.titles.index(title)
            if index < len(self.colors):
                return self.colors[index]
        return self.accent


class OpenSubmenu:
    """The group whose list is open (openSubmenu() in dial.js)."""

    def __init__(self, view):
        submenu = view.submenu
        self.title = str(submenu.get("title") or "")
        self.items = [str(item) for item in submenu["items"]]
        count = len(self.items)
        self.icons = [str((submenu.get("icons") or [])[n]) if n < len(submenu.get("icons") or []) else ""
                      for n in range(count)]
        colors = submenu.get("colors") or []
        self.colors = [_rgb(colors[n] if n < len(colors) else "", view.accent) for n in range(count)]
        self.selected = max(0, min(count - 1, int(submenu.get("selected") or 0)))
        self.rows = min(LIST_ROWS_MAX, count)
        self.first = max(0, min(count - self.rows, self.selected - self.rows // 2))
        self.index = view.titles.index(self.title) if self.title in view.titles else -1
        self.prefer_right = self.index < 0 or (self.index + 0.5) / view.count <= 0.5

    def faded(self, row):
        return (row == 0 and self.first > 0) or (
            row == self.rows - 1 and self.first + self.rows < len(self.items))


def open_submenu(view):
    """The open group's list, or None."""
    submenu = view.submenu
    if view.selected or not isinstance(submenu, dict) or not submenu.get("items"):
        return None
    return OpenSubmenu(view)


def submenu_size(count, hints=True):
    """Width and height of a list with count functions, shadow included."""
    rows = max(1, min(LIST_ROWS_MAX, count))
    return (
        LIST_W + 2 * LIST_MARGIN,
        LIST_HEADER_H + rows * LIST_ROW_H + 2 * LIST_PAD + (LIST_FOOTER_H if hints else 0) + 2 * LIST_MARGIN,
    )


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
    submenu = open_submenu(view)
    active = submenu.title if submenu else view.title
    for index in range(view.count):
        label = view.titles[index] if index < len(view.titles) else ""
        start = index * slice_angle - math.pi / 2
        yield index, label, bool(label) and label == active, start, start + slice_angle, start + slice_angle / 2


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


# --- shapes (twins of the shape functions in dial.js) ----------------------

_images = {}


def _image(path):
    """A background PNG, loaded again when the file changes."""
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    cached = _images.get(path)
    if cached is None or cached[0] != stamp:
        try:
            cached = (stamp, cairo.ImageSurface.create_from_png(path))
        except (cairo.Error, OSError):
            cached = (stamp, None)
        _images[path] = cached
    return cached[1]


def outline_points(outline, cx, cy, radius):
    """Points of a custom outline, clockwise from the top."""
    count = len(outline["points"])
    return [
        (cx + math.cos(index / count * 2 * math.pi - math.pi / 2) * radius * fraction,
         cy + math.sin(index / count * 2 * math.pi - math.pi / 2) * radius * fraction)
        for index, fraction in enumerate(outline["points"])
    ]


def _smooth_path(cr, points):
    """Closed Catmull-Rom spline through the points, as Bézier curves."""
    count = len(points)
    cr.move_to(*points[0])
    for index in range(count):
        p0, p1, p2, p3 = (points[(index + offset) % count] for offset in (-1, 0, 1, 2))
        cr.curve_to(
            p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6,
            p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6,
            p2[0], p2[1],
        )
    cr.close_path()


def _polygon(cr, cx, cy, radius, sides, rotation):
    for index in range(sides):
        angle = rotation + index / sides * 2 * math.pi
        cr.line_to(cx + math.cos(angle) * radius, cy + math.sin(angle) * radius)
    cr.close_path()


def _rounded_rect(cr, x, y, width, height, radius):
    cr.new_sub_path()
    cr.arc(x + width - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + width - radius, y + height - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + height - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


def shape_path(cr, cx, cy, radius, skin):
    """Path of the skin's disc outline; radius is half the width."""
    cr.new_path()
    shape = skin.get("shape", "circle")
    if shape == "square":
        _rounded_rect(cr, cx - radius, cy - radius, 2 * radius, 2 * radius, radius * 0.22)
    elif shape == "octagon":
        _polygon(cr, cx, cy, radius / math.cos(math.pi / 8), 8, math.pi / 8)
    elif shape in ("knurled", "scalloped"):
        steps = 120 if shape == "knurled" else 192
        for index in range(steps):
            angle = index / steps * 2 * math.pi
            r = radius - (4 if index % 2 else 0) if shape == "knurled" else radius - 3 + 3 * math.cos(16 * angle)
            cr.line_to(cx + math.cos(angle) * r, cy + math.sin(angle) * r)
        cr.close_path()
    elif shape == "custom" and skin.get("outline"):
        points = outline_points(skin["outline"], cx, cy, radius)
        if skin["outline"]["smooth"]:
            _smooth_path(cr, points)
        else:
            for point in points:
                cr.line_to(*point)
            cr.close_path()
    else:
        cr.arc(cx, cy, radius, 0, 2 * math.pi)


def _tile_path(cr, x, y, r, tile):
    cr.new_path()
    if tile == "square":
        _rounded_rect(cr, x - r * 0.9, y - r * 0.9, r * 1.8, r * 1.8, r * 0.38)
    elif tile == "diamond":
        _polygon(cr, x, y, r * 1.12, 4, -math.pi / 2)
    elif tile == "hexagon":
        _polygon(cr, x, y, r * 1.04, 6, -math.pi / 2)
    else:
        cr.arc(x, y, r, 0, 2 * math.pi)


def _surface(cr, view):
    skin = view.skin
    palette = view.palette
    background = skin.get("background")
    image = _image(background["path"]) if background else None
    if skin.get("shape", "circle") == "circle":
        _radial(cr, DIAL_R, DIAL_R + 4, OUTER_R - 6, OUTER_R + 16, palette["shadow"])
    else:
        for step in range(5, -1, -1):
            shape_path(cr, DIAL_R, DIAL_R + 4, OUTER_R + step * 2.4 - 4, skin)
            cr.set_source_rgba(0, 0, 0, palette["shadow"] * 0.12)
            cr.fill()
    shape_path(cr, DIAL_R, DIAL_R, OUTER_R, skin)
    cr.set_source(_linear(cr, DIAL_R - OUTER_R, DIAL_R + OUTER_R, palette["surfaceTop"], palette["surfaceBottom"]))
    cr.fill()
    if image is not None:
        width, height = image.get_width(), image.get_height()
        scale = max(2 * OUTER_R / width, 2 * OUTER_R / height)
        cr.save()
        shape_path(cr, DIAL_R, DIAL_R, OUTER_R, skin)
        cr.clip()
        cr.translate(DIAL_R - width * scale / 2, DIAL_R - height * scale / 2)
        cr.scale(scale, scale)
        cr.set_source_surface(image, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(background["opacity"])
        cr.restore()
    shape_path(cr, DIAL_R, DIAL_R, OUTER_R - 0.5, skin)
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
        color = view.color_at(index)
        if active:
            _wedge(cr, CENTER_R + 8, OUTER_R - 3, start + 0.06, end - 0.06)
            cr.set_source_rgba(color[0], color[1], color[2], 0.07)
            cr.fill()
            cr.new_path()
            cr.set_line_width(4)
            cr.set_source_rgba(*color)
            cr.arc(DIAL_R, DIAL_R, HIGHLIGHT_R, start + 0.1, end - 0.1)
            cr.stroke()
        tile = view.skin.get("tile", "circle")
        radius = BUBBLE_R * view.skin.get("tileSize", 1)
        _tile_path(cr, x, y, radius, tile)
        if active:
            cr.set_source_rgba(*color)
            cr.fill()
        else:
            cr.set_source_rgba(*palette["bubble"])
            cr.fill()
            if tile == "circle":
                cr.arc(x, y, radius - 0.75, mid + math.pi - 0.55, mid + math.pi + 0.55)
            else:
                _tile_path(cr, x, y, radius - 0.75, tile)
            cr.set_line_width(1.5)
            cr.set_source_rgba(color[0], color[1], color[2], 0.75 if tile == "circle" else 0.5)
            cr.stroke()
    _pointer(cr, view, HIGHLIGHT_R, palette["pointer"])


def _segments(cr, view):
    palette = view.palette
    inner, outer = CENTER_R + 8, OUTER_R - 6
    for index, label, active, start, end, _mid in _slices(view):
        start, end = start + 0.02, end - 0.02
        _wedge(cr, inner, outer, start, end)
        if not label:
            cr.set_source_rgba(*palette["freeSlot"])
            cr.fill()
            continue
        color = view.color_at(index)
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
        submenu = open_submenu(view)
        if submenu:
            icon = submenu.icons[submenu.selected] or icon_for_title(title)
            color = submenu.colors[submenu.selected]
        draw_icon(cr, icon, DIAL_R - CENTER_ICON_SIZE / 2, DIAL_R - 26 - CENTER_ICON_SIZE / 2, CENTER_ICON_SIZE, color)
        _text(cr, _truncate(title, 14), DIAL_R + 10, 13 if len(title) > 10 else 16, palette["text"], True)
        _text(cr, "Tap to choose" if submenu else "Release to select", DIAL_R + 32, 8.5, palette["muted"], False)
    else:
        _text(cr, _truncate(profile or "DIAL", 14), DIAL_R - 8, 11 if len(profile) > 10 else 13, palette["text"], True)
        _text(cr, "Choose a function", DIAL_R + 14, 9, palette["muted"], False)


def paint_submenu(cr, view, x, y, scale, side="right", draw_icon=None, hints=True):
    """Paint the open group's list with its top left corner at x, y; side is
    where the dial is, where the colour edge goes (paintSubmenu() in dial.js)."""
    submenu = open_submenu(view)
    if submenu is None:
        return
    draw_icon = draw_icon or _no_icon
    group_color = view.colors[submenu.index] if 0 <= submenu.index < len(view.colors) else view.accent

    def row_icon(cr, position, icon_x, middle, selected):
        icon = submenu.icons[position] or icon_for_title(submenu.items[position])
        draw_icon(cr, icon, icon_x - LIST_ICON_SIZE / 2, middle - LIST_ICON_SIZE / 2, LIST_ICON_SIZE,
                  view.palette["iconOnColor" if selected else "icon"])

    cr.save()
    cr.translate(x, y)
    cr.scale(scale, scale)
    _draw_list(cr, view.palette, submenu, group_color, side, hints, row_icon)
    cr.restore()


def _draw_list(cr, palette, submenu, group_color, side, hints, row_icon=None):
    """drawSubmenu() in dial.js, unscaled; submenu as OpenSubmenu has it.
    row_icon(cr, position, x, y, selected) paints a row's icon inside the
    row, so it fades with it (the previews); the Shell's icons are actors."""
    width, height = submenu_size(len(submenu.items), hints)
    left = top = LIST_MARGIN
    panel_w, panel_h = width - 2 * LIST_MARGIN, height - 2 * LIST_MARGIN
    cr.save()
    for step in range(5, -1, -1):
        grow = step * 1.8 - 3
        cr.new_path()
        _rounded_rect(cr, left - grow, top + 3 - grow, panel_w + 2 * grow, panel_h + 2 * grow, LIST_RADIUS + grow)
        cr.set_source_rgba(0, 0, 0, palette["shadow"] * 0.12)
        cr.fill()
    cr.new_path()
    _rounded_rect(cr, left, top, panel_w, panel_h, LIST_RADIUS)
    gradient = cairo.LinearGradient(0, top, 0, top + panel_h)
    gradient.add_color_stop_rgba(0, *palette["surfaceTop"])
    gradient.add_color_stop_rgba(1, *palette["surfaceBottom"])
    cr.set_source(gradient)
    cr.fill()
    _rounded_rect(cr, left + 0.5, top + 0.5, panel_w - 1, panel_h - 1, LIST_RADIUS - 0.5)
    cr.set_line_width(1)
    cr.set_source_rgba(*palette["rim"])
    cr.stroke()

    edge = left + panel_w - 2.5 if side == "left" else left + 2.5
    cr.new_path()
    cr.set_line_cap(1)  # round
    cr.set_line_width(3)
    cr.set_source_rgba(*group_color)
    cr.move_to(edge, top + LIST_RADIUS + 4)
    cr.line_to(edge, top + panel_h - LIST_RADIUS - 4)
    cr.stroke()

    header_y = top + LIST_HEADER_H / 2 + 1
    _aligned_text(cr, _truncate(submenu.title.upper(), 22), left + 18, header_y, 9.5, palette["muted"], "left", True)
    if len(submenu.items) > submenu.rows:
        _aligned_text(cr, f"{submenu.selected + 1} / {len(submenu.items)}", left + panel_w - 18, header_y, 9.5,
                      palette["muted"], "right")

    for row in range(submenu.rows):
        position = submenu.first + row
        box_x, box_y = LIST_MARGIN + LIST_PAD, LIST_MARGIN + LIST_HEADER_H + row * LIST_ROW_H
        box_w, box_h = LIST_W - 2 * LIST_PAD, LIST_ROW_H - 4
        color = submenu.colors[position]
        selected = position == submenu.selected
        icon_x, middle = box_x + 22, box_y + box_h / 2
        alpha = 0.4 if submenu.faded(row) else 1
        cr.push_group()
        if selected:
            cr.new_path()
            _rounded_rect(cr, box_x, box_y, box_w, box_h, 12)
            cr.set_source_rgba(*color)
            cr.fill()
        else:
            cr.new_path()
            cr.arc(icon_x, middle, 14, 0, 2 * math.pi)
            cr.set_source_rgba(*palette["bubble"])
            cr.fill()
            cr.arc(icon_x, middle, 13.25, math.pi - 0.6, math.pi + 0.6)
            cr.set_line_width(1.5)
            cr.set_source_rgba(color[0], color[1], color[2], 0.75)
            cr.stroke()
        _aligned_text(cr, _truncate(submenu.items[position], 20), box_x + 44, middle, 13,
                      palette["iconOnColor" if selected else "text"], "left", selected)
        if row_icon is not None:
            row_icon(cr, position, icon_x, middle, selected)
        cr.pop_group_to_source()
        cr.paint_with_alpha(alpha)

    if hints:
        footer_y = top + LIST_HEADER_H + submenu.rows * LIST_ROW_H + LIST_FOOTER_H / 2
        _aligned_text(cr, LIST_FOOTER, left + panel_w / 2, footer_y, 8.5, palette["muted"], "center")
    cr.restore()


def _aligned_text(cr, text, x, y, size, color, align, bold=False):
    cr.save()
    cr.select_font_face(FONT, 0, 1 if bold else 0)
    cr.set_font_size(size)
    extents = cr.text_extents(text)
    shift = {"right": extents.width, "center": extents.width / 2}.get(align, 0)
    cr.move_to(x - shift - extents.x_bearing, y + extents.height / 2)
    cr.set_source_rgba(*color)
    cr.show_text(text)
    cr.restore()


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


# --- the live dial ------------------------------------------------------------
#
# Twins of paintBackground(), paintContent() and paintPointer() in dial.js,
# for frontends outside GNOME Shell (overlay/layer_shell.py). They take a
# dial.js view (see overlay/look.py) and paint at the dial's top left corner
# in logical pixels, scaled by appearance["scale"], so they match the Shell;
# tests/layer_shell_in_container.sh compares them with dial.js on screen.

CENTER_EXTENT = CENTER_R + 12
GAUGE_STEPS = 24
HINT_W = 300


class _LiveMenu:
    """A dial.js view in the shape _surface(), _bubbles() and _segments() read."""

    def __init__(self, view):
        state = view["state"]
        segments = look.segment_state(state)
        self.skin = view["skin"]
        self.palette = self.skin["palette"]
        self.titles = segments["titles"]
        self.count = segments["count"]
        # The sector to highlight: an open list's group, else the title.
        self.title = look.active_title(view)
        self.pointer = None
        self.selected = False
        self.submenu = None
        self._view = view

    def color_at(self, index):
        return look.segment_color(self._view, index)


def paint_background(cr, view):
    """Shadow, disc and rim: they change only with the skin and the scale."""
    cr.save()
    cr.scale(view["appearance"]["scale"], view["appearance"]["scale"])
    _surface(cr, _LiveMenu(view))
    cr.restore()


def paint_content(cr, view, cache=None, draw_icon=None):
    """Menu or gauge, centre, hints and the icons (actors in the Shell).

    cache: a dict kept between calls; it holds the centre disc as an image.
    """
    scale = view["appearance"]["scale"]
    cr.save()
    cr.scale(scale, scale)
    if look.is_selected_mode(view["state"]):
        _live_gauge(cr, view)
    else:
        cr.save()
        menu = _LiveMenu(view)
        if view["skin"]["menu"] == "segments":
            _segments(cr, menu)
        else:
            _bubbles(cr, menu)
        cr.restore()
    _live_center(cr, view, cache)
    _hints(cr, view)
    cr.restore()
    cr.new_path()
    if draw_icon is not None:
        layout = look.icon_layout(view)
        icons = layout["menu"] if layout["menuVisible"] else []
        if layout["center"]:
            icons = [*icons, layout["center"]]
        for icon in icons:
            name = look.icon_source(icon["title"], icon["configured"])
            draw_icon(cr, name, icon["x"], icon["y"], icon["size"], icon["color"])


def paint_pointer(cr, view, color):
    """The finger dot centred in a POINTER_SIZE square (scaled)."""
    cr.save()
    cr.scale(view["appearance"]["scale"], view["appearance"]["scale"])
    _draw_pointer(cr, view["skin"]["palette"], look.POINTER_GLOW_R, look.POINTER_GLOW_R, color)
    cr.restore()


def paint_live_dial(cr, view, draw_icon=None):
    """All layers at once as the Shell shows them (paintDial() and the icon
    actors); nothing while the dial is off."""
    if not view["state"]["enabled"]:
        return
    paint_background(cr, view)
    paint_content(cr, view, None, draw_icon)
    pointer = look.pointer_placement(view)
    if pointer:
        scale = view["appearance"]["scale"]
        cr.save()
        cr.scale(scale, scale)
        _draw_pointer(cr, view["skin"]["palette"], pointer["x"], pointer["y"], pointer["color"])
        cr.restore()


class _LiveSubmenu:
    """openSubmenu() of overlay/look.py in the shape _draw_list() reads."""

    def __init__(self, submenu):
        for key in ("title", "items", "colors", "selected", "first", "rows"):
            setattr(self, key, submenu[key])
        self._submenu = submenu

    def faded(self, row):
        return look.list_row_faded(self._submenu, row)


def paint_live_submenu(cr, view, side="right", scale=None, draw_icon=None):
    """paintSubmenu() in dial.js and the list's icon actors
    (submenuLayout()): the open group's list in a submenu_size() box at the
    top left corner; side and scale come from look.submenu_placement()."""
    submenu = look.open_submenu(view)
    if not submenu:
        return
    scale = view["appearance"]["scale"] if scale is None else scale
    group_color = look.segment_color(view, submenu["index"]) if submenu["index"] >= 0 else view["accent"]
    cr.save()
    cr.scale(scale, scale)
    _draw_list(cr, view["skin"]["palette"], _LiveSubmenu(submenu), group_color, side,
               view["appearance"].get("show_hints") is not False)
    cr.restore()
    cr.new_path()
    if draw_icon is not None:
        for row in look.submenu_layout(view, scale)["rows"]:
            draw_icon(cr, look.icon_source(row["title"], row["configured"]), row["x"], row["y"], row["size"],
                      row["color"])


def _draw_pointer(cr, palette, x, y, color):
    cr.save()
    cr.new_path()
    glow = cairo.RadialGradient(x, y, 2, x, y, look.POINTER_GLOW_R)
    glow.add_color_stop_rgba(0, color[0], color[1], color[2], 0.55)
    glow.add_color_stop_rgba(1, color[0], color[1], color[2], 0)
    cr.arc(x, y, look.POINTER_GLOW_R, 0, 2 * math.pi)
    cr.set_source(glow)
    cr.fill()
    cr.arc(x, y, 5.5, 0, 2 * math.pi)
    cr.set_source_rgba(*palette["pointer"])
    cr.fill()
    cr.restore()


def _live_gauge(cr, view):
    state = view["state"]
    palette = view["skin"]["palette"]
    color = look.function_color(view)
    number = look.js_number(state["value"])
    value = number if math.isfinite(number) else None
    level = not state["valueShowOnlyProgress"] and state["unit"] == "%" and value is not None
    cr.save()
    cr.new_path()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_width(GAUGE_W)
    if level:
        # Level functions (volume, brightness…) get a knob-style scale.
        cr.set_source_rgba(*palette["track"])
        cr.arc(DIAL_R, DIAL_R, GAUGE_R, GAUGE_START, GAUGE_START + GAUGE_SWEEP)
        cr.stroke()
        fraction = max(0, min(1, value / 100))
        if fraction > 0.005:
            cr.set_source_rgba(*color)
            cr.arc(DIAL_R, DIAL_R, GAUGE_R, GAUGE_START, GAUGE_START + fraction * GAUGE_SWEEP)
            cr.stroke()
    else:
        # Endless functions show detents, like the notches of a wheel.
        cr.set_source_rgba(*palette["track"])
        cr.arc(DIAL_R, DIAL_R, GAUGE_R, 0, 2 * math.pi)
        cr.stroke()
        cr.set_line_width(2)
        for index in range(GAUGE_STEPS):
            angle = index / GAUGE_STEPS * 2 * math.pi
            cr.move_to(DIAL_R + math.cos(angle) * (GAUGE_R - 3), DIAL_R + math.sin(angle) * (GAUGE_R - 3))
            cr.line_to(DIAL_R + math.cos(angle) * (GAUGE_R + 3), DIAL_R + math.sin(angle) * (GAUGE_R + 3))
        cr.set_source_rgba(*palette["detent"])
        cr.stroke()
    if state["valueShowOnlyProgress"] and value is not None:
        # Progress towards the next step of slow functions (Undo…).
        fraction = max(-1, min(1, value / 100))
        if abs(fraction) >= 0.01:
            start = math.radians(look.js_number(state["valueAngleStart"])) - math.pi / 2
            cr.set_line_width(GAUGE_W)
            cr.set_source_rgba(*color)
            if fraction > 0:
                cr.arc(DIAL_R, DIAL_R, GAUGE_R, start, start + fraction * 2 * math.pi)
            else:
                cr.arc_negative(DIAL_R, DIAL_R, GAUGE_R, start, start + fraction * 2 * math.pi)
            cr.stroke()
    cr.restore()


def _center_disc(cr, palette, cx, cy):
    _radial(cr, cx, cy + 2, CENTER_R - 4, CENTER_R + 10, palette["shadow"] * 0.75)
    gradient = cairo.LinearGradient(cx, cy - CENTER_R, cx, cy + CENTER_R)
    gradient.add_color_stop_rgba(0, *palette["centerTop"])
    gradient.add_color_stop_rgba(1, *palette["centerBottom"])
    cr.arc(cx, cy, CENTER_R, 0, 2 * math.pi)
    cr.set_source(gradient)
    cr.fill()


def _cached_center_disc(cr, palette, cache):
    """The disc, the most expensive part, copied from an image made once per
    skin and pixel density."""
    pixel_scale = cr.user_to_device_distance(1, 0)[0] * cr.get_target().get_device_scale()[0]
    key = (pixel_scale, palette["shadow"], tuple(palette["centerTop"]), tuple(palette["centerBottom"]))
    if cache.get("center_key") != key:
        pixels = math.ceil(2 * CENTER_EXTENT * pixel_scale)
        image = cairo.ImageSurface(cairo.FORMAT_ARGB32, pixels, pixels)
        image.set_device_scale(pixel_scale, pixel_scale)
        _center_disc(cairo.Context(image), palette, CENTER_EXTENT, CENTER_EXTENT)
        cache["center_image"] = image
        cache["center_key"] = key
    cr.save()
    cr.set_source_surface(cache["center_image"], DIAL_R - CENTER_EXTENT, DIAL_R - CENTER_EXTENT)
    cr.rectangle(DIAL_R - CENTER_EXTENT, DIAL_R - CENTER_EXTENT, 2 * CENTER_EXTENT, 2 * CENTER_EXTENT)
    cr.fill()
    cr.restore()


def _live_center(cr, view, cache):
    state, details = view["state"], view["details"]
    palette = view["skin"]["palette"]
    selected = look.is_selected_mode(state)
    accent = look.function_color(view) if selected else view["accent"]
    cr.save()
    cr.new_path()
    if cache is not None:
        _cached_center_disc(cr, palette, cache)
    else:
        _center_disc(cr, palette, DIAL_R, DIAL_R)
    cr.arc(DIAL_R, DIAL_R, CENTER_R - 0.5, 0, 2 * math.pi)
    cr.set_line_width(2.5 if state["centerPressed"] else 1)
    cr.set_source_rgba(*(accent if state["centerPressed"] else palette["rim"]))
    cr.stroke()

    title = state["title"]
    profile = (details.get("profile") or "").upper()
    if selected:
        value = ""
        if not state["valueShowOnlyProgress"] and state["unit"]:
            value = f"{look.format_value(state['value'])}{state['unit']}"
        _text(cr, _truncate(title, 14), DIAL_R + 2, 13 if len(title) > 10 else 16, palette["text"], True)
        if value:
            _text(cr, value, DIAL_R + 27, 18, accent, True)
        elif profile:
            _text(cr, _truncate(profile, 16), DIAL_R + 26, 8.5, palette["muted"], False)
    elif title and title != "Menu":
        _text(cr, _truncate(title, 14), DIAL_R + 10, 13 if len(title) > 10 else 16, palette["text"], True)
        action = "Tap to choose" if look.open_submenu(view) else "Release to select"
        _text(cr, action, DIAL_R + 32, 8.5, palette["muted"], False)
    else:
        _text(cr, _truncate(profile or "DIAL", 14), DIAL_R - 8, 11 if len(profile) > 10 else 13, palette["text"], True)
        _text(cr, "Choose a function", DIAL_R + 14, 9, palette["muted"], False)
    cr.restore()


def _hints(cr, view):
    """The bar below the disc: what turning and the centre do."""
    if not view["appearance"].get("show_hints") or not look.is_selected_mode(view["state"]):
        return
    palette = view["skin"]["palette"]
    hints = view["details"].get("hints")
    hints = hints if isinstance(hints, dict) else {}
    multi = view["details"].get("mode") != "single"
    ccw = _truncate(hints.get("ccw"), 20)
    cw = _truncate(hints.get("cw"), 20)
    # A function of a group goes back to the group's list.
    back = "back" if view["details"].get("parent") else "menu"
    center = ""
    if hints.get("center"):
        action = _truncate(hints["center"], 26)
        center = f"Tap: {action}  ·  Hold: {back}" if multi else f"Tap: {action}"
    elif multi:
        center = f"Tap centre: {back}"
    if not ccw and not cw and not center:
        return
    height = 40 if center else 24
    # The bar is centred in the HINT_H strip below the disc.
    top = DIAL_D + 2
    left, right = DIAL_R - HINT_W / 2, DIAL_R + HINT_W / 2
    cr.save()
    cr.new_path()
    _rounded_rect(cr, left, top, HINT_W, height, 12)
    cr.set_source_rgba(*palette["surfaceBottom"])
    cr.fill_preserve()
    cr.set_line_width(1)
    cr.set_source_rgba(*palette["rim"])
    cr.stroke()
    arrow = look.function_color(view)
    if ccw:
        _turn_arrow(cr, left + 18, top + 12, False, arrow)
        _aligned_text(cr, ccw, left + 30, top + 12, 11, palette["text"], "left")
    if cw:
        _turn_arrow(cr, right - 18, top + 12, True, arrow)
        _aligned_text(cr, cw, right - 30, top + 12, 11, palette["text"], "right")
    if center:
        _text(cr, center, top + 29, 9, palette["muted"], False)
    cr.restore()


def _turn_arrow(cr, x, y, clockwise, color):
    """Drawn instead of ↺/↻, which the Cairo toy font cannot render."""
    radius = 5.5
    start = -math.pi * 0.85 if clockwise else -math.pi * 0.15
    end = math.pi * 0.45 if clockwise else math.pi * 0.55
    cr.save()
    cr.new_path()
    cr.set_line_width(1.6)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_source_rgba(*color)
    if clockwise:
        cr.arc(x, y, radius, start, end)
    else:
        cr.arc_negative(x, y, radius, start, end)
    cr.stroke()
    tip_x, tip_y = x + math.cos(end) * radius, y + math.sin(end) * radius
    tangent = end + (math.pi / 2 if clockwise else -math.pi / 2)
    for spread in (0.5, -0.5):
        angle = tangent + math.pi + spread
        cr.move_to(tip_x, tip_y)
        cr.line_to(tip_x + math.cos(angle) * 4, tip_y + math.sin(angle) * 4)
    cr.stroke()
    cr.restore()
