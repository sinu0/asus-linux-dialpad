"""Symbolic icons for overlay.painter, looked up in the GTK icon theme."""

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, Gtk

try:
    gi.require_version("Rsvg", "2.0")
    from gi.repository import Rsvg
except (ImportError, ValueError):
    # Without librsvg's introspection data dials simply have no icons.
    Rsvg = None

_handles = {}


def _handle(name):
    if name in _handles:
        return _handles[name]
    handle = None
    path = name if name.startswith("/") else None
    display = Gdk.Display.get_default()
    if path is None and display is not None:
        paintable = Gtk.IconTheme.get_for_display(display).lookup_icon(
            name, None, 32, 1, Gtk.TextDirection.LTR, 0
        )
        icon_file = paintable.get_file() if paintable is not None else None
        path = icon_file.get_path() if icon_file is not None else None
    if Rsvg is not None and path and path.endswith(".svg"):
        try:
            handle = Rsvg.Handle.new_from_file(path)
        except Exception:
            handle = None
    _handles[name] = handle
    return handle


def draw_icon(cr, name, x, y, size, color):
    """Paint a symbolic icon (theme name or absolute .svg path) recoloured
    like GNOME Shell does."""
    handle = _handle(name)
    if handle is None:
        return
    cr.push_group()
    viewport = Rsvg.Rectangle()
    viewport.x, viewport.y, viewport.width, viewport.height = x, y, size, size
    handle.render_document(cr, viewport)
    mask = cr.pop_group()
    cr.set_source_rgba(*color)
    cr.mask(mask)
