"""GTK 4 windows of the layer-shell dial (started by overlay/layer_shell.py).

The structure follows gnome/extension/extension.js: appearance from
config.json (reloaded when it or a skin changes), the driver's signals on
the session bus, the dial in three layers (layers.js), a group's list
beside it (a window that fades with the dial) and the pill in its place
with visibility "pill". Decisions come from overlay/look.py and
overlay/visibility.py, painting from overlay/painter.py.
"""

from __future__ import annotations

import json
import math

import cairo
import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_foreign("cairo")
from gi.repository import Gdk, Gio, GLib, Gtk, Gtk4LayerShell  # noqa: E402

from config import identity  # noqa: E402
from config.schema import CONFIG_DIR, CONFIG_FILE  # noqa: E402
from config.skins import SKINS_DIR, load_skins, resolve_skin  # noqa: E402
from desktop import pointer as desktop_pointer  # noqa: E402
from desktop.color_scheme import ColorScheme  # noqa: E402
from overlay import gtk_icons, look, painter  # noqa: E402
from overlay.visibility import Visibility  # noqa: E402

NAMESPACE = identity.SLUG
# Batches the events of one save of config.json, like the extension.
CONFIG_RELOAD_MS = 200
# Opacity steps of a fade, about one per frame.
FADE_STEP_MS = 16

CSS = """
window.turnpad-dial, window.turnpad-pill, window.turnpad-list { background: none; box-shadow: none; }
"""


def _log(message: str) -> None:
    import sys

    print(f"turnpad-dial: {message}", file=sys.stderr, flush=True)


def _rgba(color) -> str:
    r, g, b = (round(channel * 255) for channel in color[:3])
    alpha = color[3] if len(color) > 3 else 1
    return f"rgba({r}, {g}, {b}, {alpha})"


# --- windows on the overlay layer ------------------------------------------------

def _layer_window(css_class: str) -> Gtk.Window:
    """A layer surface above everything that takes no input at all."""
    window = Gtk.Window()
    window.add_css_class(css_class)
    window.set_decorated(False)
    window.set_resizable(False)
    window.set_can_focus(False)
    window.set_focusable(False)
    Gtk4LayerShell.init_for_window(window)
    Gtk4LayerShell.set_layer(window, Gtk4LayerShell.Layer.OVERLAY)
    Gtk4LayerShell.set_namespace(window, NAMESPACE)
    Gtk4LayerShell.set_keyboard_mode(window, Gtk4LayerShell.KeyboardMode.NONE)
    # Placed against the whole output like the Shell places its actors,
    # not inside the space panels leave.
    Gtk4LayerShell.set_exclusive_zone(window, -1)
    Gtk4LayerShell.set_anchor(window, Gtk4LayerShell.Edge.TOP, True)
    Gtk4LayerShell.set_anchor(window, Gtk4LayerShell.Edge.LEFT, True)

    def click_through(*_args):
        # An empty input region: clicks and touches reach the window below.
        surface = window.get_surface()
        if surface is not None:
            surface.set_input_region(cairo.Region())

    window.connect("realize", click_through)
    window.connect("map", click_through)
    return window


class FadingWindow:
    """A window as the Actor overlay/visibility.py fades (Clutter's ease())."""

    def __init__(self, window: Gtk.Window):
        self.window = window
        self._opacity = 0.0
        self._source = 0
        # Windows that show and fade with this one, like child actors
        # (GroupList): told after every change.
        self.followers = []
        window.set_opacity(0)

    @property
    def visible(self) -> bool:
        return self.window.get_visible()

    @visible.setter
    def visible(self, value: bool) -> None:
        # Hidden windows are unmapped: they cost the compositor nothing and
        # the next show lets it choose the output again.
        self.window.set_visible(value)
        for follower in self.followers:
            follower.parent_changed()

    @property
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, value: float) -> None:
        self._opacity = value
        self.window.set_opacity(max(0.0, min(1.0, value / 255)))
        for follower in self.followers:
            follower.parent_changed()

    def ease(self, opacity, duration, easing, on_complete=None) -> None:
        self.remove_all_transitions()
        start, begin = self._opacity, GLib.get_monotonic_time()

        def step():
            progress = min(1.0, (GLib.get_monotonic_time() - begin) / (duration * 1000)) if duration else 1.0
            self.opacity = start + (opacity - start) * easing(progress)
            if progress < 1:
                return GLib.SOURCE_CONTINUE
            self._source = 0
            if on_complete:
                on_complete()
            return GLib.SOURCE_REMOVE

        self._source = GLib.timeout_add(FADE_STEP_MS, step)

    def remove_all_transitions(self) -> None:
        if self._source:
            GLib.source_remove(self._source)
            self._source = 0


class GroupList:
    """A group's list beside the dial: the list actor of extension.js, a
    child of the dial there, so it shows, fades and hides with it. Here it
    is a window of its own whose opacity is the dial's times its own; it
    slides out from the dial, so the window reaches LIST_SLIDE further
    towards the dial and the picture moves inside it."""

    def __init__(self, window: Gtk.Window, fixed: Gtk.Fixed, area: Gtk.Widget, dial: FadingWindow):
        self.window = window
        self._fixed = fixed
        self._area = area
        self._dial = dial
        dial.followers.append(self)
        self.open = False
        self._shown = False
        self._opacity = 0.0
        self._translation = 0.0
        self._offset = 0
        self._moved_to = None
        self._placed = None
        self._side = "right"
        self._slide = 0
        self._source = 0
        window.set_opacity(0)

    def place(self, placed: dict, scale: float, width: int) -> None:
        """placed: look.submenu_placement() on the monitor; width: of the
        monitor, which the window does not pass."""
        # Called for every driver signal: the window moves only on a change.
        key = (placed["x"], placed["y"], placed["width"], placed["height"], placed["side"], scale, width)
        if key == self._placed:
            return
        self._placed = key
        self._side = placed["side"]
        self._slide = look.js_round(look.LIST_SLIDE * scale)
        if placed["side"] == "right":
            left = max(0, placed["x"] - self._slide)
            right = placed["x"] + placed["width"]
        else:
            left = placed["x"]
            right = min(width, placed["x"] + placed["width"] + self._slide)
        self._offset = placed["x"] - left
        self.window.get_child().set_size_request(right - left, placed["height"])
        self.window.set_default_size(right - left, placed["height"])
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.LEFT, left)
        Gtk4LayerShell.set_margin(self.window, Gtk4LayerShell.Edge.TOP, placed["y"])
        self._apply()

    def show_list(self) -> None:
        """Slide in, unless it is open already (_updateSubmenu())."""
        if self.open:
            return
        self.open = True
        self._shown = True
        self._opacity = 0.0
        self._translation = (-1 if self._side == "right" else 1) * self._slide
        self._ease(255, 0, look.LIST_OPEN_MS, look.ease_out_cubic)

    def hide_list(self) -> None:
        """Fade out towards the dial (_closeSubmenu())."""
        if not self.open:
            return
        self.open = False

        def done():
            if not self.open:
                self._shown = False
                self._apply()

        towards = (-1 if self._side == "right" else 1) * look.js_round(self._slide / 2)
        self._ease(0, towards, look.LIST_CLOSE_MS, look.ease_in_quad, done)

    def parent_changed(self) -> None:
        self._apply()

    def _apply(self) -> None:
        visible = self._shown and self._dial.visible
        if self.window.get_visible() != visible:
            self.window.set_visible(visible)
        self.window.set_opacity(max(0.0, min(1.0, self._dial.opacity / 255 * self._opacity / 255)))
        position = self._offset + round(self._translation)
        if position != self._moved_to:
            self._moved_to = position
            self._fixed.move(self._area, position, 0)

    def _ease(self, opacity, translation, duration, easing, on_complete=None) -> None:
        if self._source:
            GLib.source_remove(self._source)
        start = (self._opacity, self._translation)
        begin = GLib.get_monotonic_time()

        def step():
            progress = min(1.0, (GLib.get_monotonic_time() - begin) / (duration * 1000))
            eased = easing(progress)
            self._opacity = start[0] + (opacity - start[0]) * eased
            self._translation = start[1] + (translation - start[1]) * eased
            self._apply()
            if progress < 1:
                return GLib.SOURCE_CONTINUE
            self._source = 0
            if on_complete:
                on_complete()
            return GLib.SOURCE_REMOVE

        self._apply()
        self._source = GLib.timeout_add(FADE_STEP_MS, step)


class GLibTimers:
    def add(self, milliseconds, callback):
        def run():
            callback()
            return GLib.SOURCE_REMOVE

        return GLib.timeout_add(milliseconds, run)

    def remove(self, handle):
        GLib.source_remove(handle)


# --- the three layers (gnome/extension/layers.js) ---------------------------------

class _Layer:
    """A drawing area that keeps its picture until invalidate()."""

    def __init__(self, paint):
        self.area = Gtk.DrawingArea()
        self.area.set_can_target(False)
        self.area.set_draw_func(self._draw)
        self._paint = paint
        self._image = None
        self._key = None

    def set_size(self, width: int, height: int) -> None:
        self.area.set_content_width(width)
        self.area.set_content_height(height)
        self.area.set_size_request(width, height)

    def invalidate(self) -> None:
        self._image = None
        self.area.queue_draw()

    def pixel_scale(self) -> float:
        native = self.area.get_native()
        surface = native.get_surface() if native is not None else None
        if surface is not None and hasattr(surface, "get_scale"):
            return surface.get_scale()
        return float(self.area.get_scale_factor())

    def _draw(self, _area, cr, width, height):
        scale = self.pixel_scale()
        key = (width, height, scale)
        if self._image is None or self._key != key:
            image = cairo.ImageSurface(cairo.FORMAT_ARGB32, math.ceil(width * scale), math.ceil(height * scale))
            image.set_device_scale(scale, scale)
            self._paint(cairo.Context(image))
            self._image, self._key = image, key
        cr.set_source_surface(self._image, 0, 0)
        cr.paint()


class DialLayers:
    """Background (skin, scale), content (contentKey()) and the finger dot
    (its colour); moving the finger only moves the dot's widget."""

    def __init__(self, fixed: Gtk.Fixed, get_view):
        self._fixed = fixed
        self._get_view = get_view
        self._cache = {}
        self._content_key = None
        self._pointer_key = None
        self._pointer_color = None
        self._background = _Layer(lambda cr: painter.paint_background(cr, self._get_view()))
        self._content = _Layer(self._paint_content)
        self._pointer = _Layer(self._paint_pointer)
        for layer in (self._background, self._content, self._pointer):
            fixed.put(layer.area, 0, 0)
        self._pointer.area.set_visible(False)
        # Counts paints, for the tests.
        self.content_paints = 0

    def _paint_content(self, cr):
        view = self._get_view()
        self.content_paints += 1
        if view["state"]["enabled"]:
            painter.paint_content(cr, view, self._cache, gtk_icons.draw_icon)

    def _paint_pointer(self, cr):
        if self._pointer_color:
            painter.paint_pointer(cr, self._get_view(), self._pointer_color)

    def set_size(self, width: int, height: int, scale: float) -> None:
        self._background.set_size(width, height)
        self._content.set_size(width, height)
        size = math.ceil(look.POINTER_SIZE * scale)
        self._pointer.set_size(size, size)
        self.invalidate()

    def invalidate(self) -> None:
        """After a skin, scale or size change: paint every layer again."""
        self._content_key = None
        self._pointer_key = None
        self._background.invalidate()
        self.update()

    def update(self) -> None:
        """For every driver signal, so it only compares and moves."""
        view = self._get_view()
        key = look.content_key(view)
        if key != self._content_key:
            self._content_key = key
            self._content.invalidate()
        self._background.area.set_visible(view["state"]["enabled"])
        self._update_pointer(view)

    def _update_pointer(self, view) -> None:
        placement = look.pointer_placement(view) if view["state"]["enabled"] else None
        self._pointer.area.set_visible(bool(placement))
        if not placement:
            return
        scale = view["appearance"]["scale"]
        half = look.POINTER_SIZE * scale / 2
        # Between screen pixels the dot is resampled, as in the Shell.
        self._fixed.move(self._pointer.area, placement["x"] * scale - half, placement["y"] * scale - half)
        key = json.dumps([placement["color"], view["skin"]["palette"]["pointer"]])
        if key != self._pointer_key:
            self._pointer_key = key
            self._pointer_color = placement["color"]
            self._pointer.invalidate()


# --- the frontend ------------------------------------------------------------------

class DialFrontend:
    def __init__(self, output: str | None = None):
        self._output = output
        self._bus = None
        self._subscriptions = []
        self._watch = 0
        self._monitors = []
        self._reload_source = 0
        self._monitors_changed = 0
        self._placed_on = None
        # (monitor, [x, y] from its corner) when a fully hidden dial with
        # position "pointer" was shown; kept while it is visible.
        self._pointer = None
        # The output was chosen for the pointer, not by the compositor.
        self._pinned_to_pointer = False
        self._look_key = ""
        self._pill_key = ""
        self._skin_id = ""
        # Where the dial is on self._placed_on, and the group list beside it.
        self._dial_placement = None
        self._list_key = ""
        self._list_side = "right"
        self._list_scale = 1.0
        self._list_monitor = None
        self.state = look.new_state()
        self.details = look.new_details()
        self.appearance = dict(look.DEFAULT_APPEARANCE)
        self.skin = resolve_skin({}, look.DEFAULT_SKIN)
        self._color_scheme = None

    # --- start and stop

    def start(self) -> None:
        display = Gdk.Display.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_string(CSS) if hasattr(provider, "load_from_string") else provider.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._pill_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(display, self._pill_provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        try:
            self._color_scheme = ColorScheme()
            self._color_scheme.on_changed(self._on_style_changed)
        except GLib.Error as error:
            _log(f"light/dark style unknown: {error.message}")
        self._load_appearance()
        self._watch_config()
        self._create_windows()
        self._connect_dbus()
        self._monitors_changed = display.get_monitors().connect("items-changed", lambda *_: self._apply_geometry())
        GLib.idle_add(lambda: (self._apply_geometry(), GLib.SOURCE_REMOVE)[1])

    def stop(self) -> None:
        self.visibility.cancel()
        for monitor in self._monitors:
            monitor.cancel()
        if self._bus is not None:
            for subscription in self._subscriptions:
                self._bus.signal_unsubscribe(subscription)
        if self._watch:
            Gio.bus_unwatch_name(self._watch)

    # --- appearance from config.json

    def _load_appearance(self) -> None:
        try:
            with open(CONFIG_FILE) as handle:
                overlay = json.load(handle).get("overlay") or {}
        except (OSError, ValueError, AttributeError) as error:
            # An unreadable file keeps the last good look instead of jumping
            # to the default skin.
            if self._skin_id:
                _log(f"keeping the current look, config.json unreadable: {error}")
                return
            overlay = {}
        self.appearance = look.load_appearance(overlay)
        self._apply_skin()

    def _prefers_dark(self) -> bool:
        return self._color_scheme.prefers_dark() if self._color_scheme else True

    def _apply_skin(self) -> None:
        wanted = look.skin_id(self.appearance, self._prefers_dark())
        skins = load_skins()
        if wanted not in skins:
            _log(f'skin "{wanted}" not found')
            # Keep a skin that was shown already (its file may be in the
            # middle of being replaced); a new choice falls back to the default.
            if self._skin_id == wanted:
                return
        self.skin = resolve_skin(skins, wanted)
        self._skin_id = wanted

    def _on_style_changed(self) -> None:
        if not self.appearance.get("follow_system_style"):
            return
        self._apply_skin()
        self._pill_key = ""
        self.layers.invalidate()
        self._update_pill()
        self._list_key = ""
        self._update_submenu()

    def _watch_config(self) -> None:
        # config.json and the skins directory; a skins directory created
        # later is picked up when it appears.
        self._watch_directory(CONFIG_DIR, lambda name: name in (CONFIG_FILE.name, "skins"))
        self._watch_directory(SKINS_DIR, lambda name: name.endswith((".json", ".png")))

    def _watch_directory(self, path, relevant) -> None:
        try:
            monitor = Gio.File.new_for_path(str(path)).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
        except GLib.Error:
            return

        def changed(_monitor, file, other, _event):
            names = [item.get_basename() for item in (file, other) if item is not None]
            if any(relevant(name) for name in names):
                self._schedule_config_reload()

        monitor.connect("changed", changed)
        self._monitors.append(monitor)

    def _schedule_config_reload(self) -> None:
        if self._reload_source:
            GLib.source_remove(self._reload_source)

        def reload():
            self._reload_source = 0
            self._load_appearance()
            self._apply_geometry()
            return GLib.SOURCE_REMOVE

        self._reload_source = GLib.timeout_add(CONFIG_RELOAD_MS, reload)

    # --- windows

    def _create_windows(self) -> None:
        self._dial = _layer_window("turnpad-dial")
        fixed = Gtk.Fixed()
        fixed.set_can_target(False)
        self._dial.set_child(fixed)
        self.layers = DialLayers(fixed, self.view)

        # A small label shown instead of the dial (visibility "pill").
        self._pill = _layer_window("turnpad-pill")
        self._pill_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._pill_box.add_css_class("turnpad-pill-box")
        self._pill_icon = Gtk.Image()
        self._pill_icon.add_css_class("turnpad-pill-icon")
        self._pill_title = Gtk.Label()
        self._pill_title.add_css_class("turnpad-pill-title")
        self._pill_value = Gtk.Label()
        self._pill_value.add_css_class("turnpad-pill-value")
        for child in (self._pill_icon, self._pill_title, self._pill_value):
            child.set_valign(Gtk.Align.CENTER)
            self._pill_box.append(child)
        self._pill.set_child(self._pill_box)

        for window in (self._dial, self._pill):
            if self._output:
                Gtk4LayerShell.set_monitor(window, self._monitor_by_connector(self._output))
            window.connect("realize", self._on_realize)

        self.dial_actor = FadingWindow(self._dial)
        self.pill_actor = FadingWindow(self._pill)

        # A group's list beside the dial, on the dial's output.
        self._list = _layer_window("turnpad-list")
        list_fixed = Gtk.Fixed()
        list_fixed.set_can_target(False)
        self._list.set_child(list_fixed)
        self._list_layer = _Layer(self._paint_list)
        list_fixed.put(self._list_layer.area, 0, 0)
        if self._output:
            Gtk4LayerShell.set_monitor(self._list, self._monitor_by_connector(self._output))
        self.list_actor = GroupList(self._list, list_fixed, self._list_layer.area, self.dial_actor)
        self.visibility = Visibility(self.dial_actor, self.pill_actor, GLibTimers(), self._look, lambda: self.state,
                                     lambda: self.appearance["hide_delay_ms"], self._follow_pointer)

    def _on_realize(self, window) -> None:
        window.get_surface().connect("enter-monitor", self._on_enter_monitor)

    def _on_enter_monitor(self, _surface, monitor) -> None:
        # The compositor put the window on another output than the one it
        # was placed for: place it again for this one.
        if monitor is not self._placed_on:
            self._placed_on = monitor
            self._apply_geometry()

    def _monitor_by_connector(self, connector):
        monitors = Gdk.Display.get_default().get_monitors()
        for index in range(monitors.get_n_items()):
            monitor = monitors.get_item(index)
            if monitor.get_connector() == connector:
                return monitor
        _log(f"output {connector} not found, the compositor chooses")
        return None

    def _monitor(self):
        """The monitor to place for: a pinned one, the one the compositor
        showed the dial on last, else the first."""
        if self._output:
            pinned = self._monitor_by_connector(self._output)
            if pinned is not None:
                return pinned
        items = self._outputs()
        if self._placed_on in items:
            return self._placed_on
        return items[0] if items else None

    def _outputs(self) -> list:
        monitors = Gdk.Display.get_default().get_monitors()
        return [monitors.get_item(index) for index in range(monitors.get_n_items())]

    def _follow_pointer(self) -> None:
        """A fully hidden dial with position "pointer" comes back next to
        the pointer, on its output, where the compositor tells where it is
        (desktop/pointer.py); elsewhere it goes to "lower". Fading in or out
        counts as shown, so a visible dial never moves."""
        if self.dial_actor.visible or self.pill_actor.visible:
            return
        found = None
        if self._look()["position"] == "pointer":
            at = desktop_pointer.position()
            for monitor in self._outputs() if at else ():
                area = monitor.get_geometry()
                if area.x <= at[0] < area.x + area.width and area.y <= at[1] < area.y + area.height:
                    found = (monitor, [at[0] - area.x, at[1] - area.y])
                    break
        if found and self._output and found[0] is not self._monitor_by_connector(self._output):
            found = None  # --output pins the dial to another output
        if found and not self._output:
            for window in (self._dial, self._pill):
                Gtk4LayerShell.set_monitor(window, found[0])
            self._pinned_to_pointer = True
        elif self._pinned_to_pointer:
            # Back to the compositor's choice.
            for window in (self._dial, self._pill):
                Gtk4LayerShell.set_monitor(window, None)
            self._pinned_to_pointer = False
        if found or self._pointer:
            self._pointer = found
            if found:
                self._placed_on = found[0]
            self._apply_geometry()

    @staticmethod
    def _logical(monitor) -> dict:
        geometry = monitor.get_geometry()
        return {"width": geometry.width, "height": geometry.height}

    def _look(self) -> dict:
        return look.effective_look(self.appearance, self.details.get("look"))

    def view(self) -> dict:
        return look.make_view(self.state, self.details, self.appearance, self.skin)

    def _dial_pointer(self, monitor):
        """The pointer on this monitor when the dial appeared, or None."""
        return self._pointer[1] if self._pointer and self._pointer[0] is monitor else None

    def _apply_geometry(self) -> None:
        monitor = self._monitor()
        if monitor is None:
            return
        self._placed_on = monitor
        scale = self.appearance["scale"]
        current = self._look()
        self._look_key = json.dumps(current)
        placed = look.overlay_placement(self._logical(monitor), scale, current["position"], current["custom"],
                                        self._dial_pointer(monitor), current["pointerSide"], current["pointerGap"])
        # The window is only as large as the dial, so fading it composites
        # the dial and not the whole screen.
        self._dial.get_child().set_size_request(placed["width"], placed["height"])
        self._dial.set_default_size(placed["width"], placed["height"])
        Gtk4LayerShell.set_margin(self._dial, Gtk4LayerShell.Edge.LEFT, placed["x"])
        Gtk4LayerShell.set_margin(self._dial, Gtk4LayerShell.Edge.TOP, placed["y"])
        self.layers.set_size(placed["width"], placed["height"], scale)
        self._dial_placement = placed
        self._pill_key = ""
        self._update_pill()
        self._list_key = ""
        self._update_submenu()

    # --- group list

    def _paint_list(self, cr) -> None:
        painter.paint_live_submenu(cr, self.view(), self._list_side, self._list_scale, gtk_icons.draw_icon)

    def _update_submenu(self) -> None:
        """Opens, moves, repaints or closes the list of the open group
        (_updateSubmenu() in extension.js)."""
        monitor = self._placed_on
        if monitor is None or self._dial_placement is None:
            return
        view = self.view()
        submenu = look.open_submenu(view)
        if not submenu:
            self.list_actor.hide_list()
            self._list_key = ""
            return
        scale = self.appearance["scale"]
        geometry = self._logical(monitor)
        size = look.submenu_size(len(submenu["items"]), self.appearance["show_hints"])
        placed = look.submenu_placement(geometry, self._dial_placement, scale, size, submenu["preferRight"])
        self._list_side, self._list_scale = placed["side"], placed["scale"]
        if not self._output and monitor is not self._list_monitor:
            # The compositor would choose the list's output on its own.
            Gtk4LayerShell.set_monitor(self._list, monitor)
            self._list_monitor = monitor
        self.list_actor.place(placed, scale, geometry["width"])
        key = json.dumps([look.submenu_key(view, placed["side"]), placed["scale"], placed["width"],
                          placed["height"]])
        if key != self._list_key:
            self._list_key = key
            self._list_layer.set_size(placed["width"], placed["height"])
            self._list_layer.invalidate()
        self.list_actor.show_list()

    # --- pill

    def _update_pill(self) -> None:
        monitor = self._placed_on or self._monitor()
        current = self._look()
        if monitor is None or current["visibility"] != "pill":
            return
        scale = self.appearance["scale"]
        palette = self.skin["palette"]
        content = look.pill_content(self.view())
        geometry = self._logical(monitor)
        pointer = self._dial_pointer(monitor)
        # The driver signals every few degrees; restyle only on a change.
        key = json.dumps([content, scale, palette["surfaceTop"], palette["rim"], palette["text"], self._look_key,
                          geometry, pointer], default=str)
        if key == self._pill_key:
            return
        self._pill_key = key
        font = round(15 * scale)
        css = (
            f".turnpad-pill-box {{ background-color: {_rgba(palette['surfaceTop'])}; "
            f"border: 1px solid {_rgba(palette['rim'])}; border-radius: {round(24 * scale)}px; "
            f"padding: {round(9 * scale)}px {round(18 * scale)}px; }}\n"
            f".turnpad-pill-icon {{ color: {_rgba(content['color'])}; }}\n"
            f".turnpad-pill-title {{ color: {_rgba(palette['text'])}; font-weight: bold; font-size: {font}px; }}\n"
            f".turnpad-pill-value {{ color: {_rgba(content['color'])}; font-weight: bold; font-size: {font}px; }}\n"
        )
        if hasattr(self._pill_provider, "load_from_string"):
            self._pill_provider.load_from_string(css)
        else:
            self._pill_provider.load_from_data(css, -1)
        self._pill_box.set_spacing(round(10 * scale))
        source = look.icon_source(content["title"], content["configured"])
        if source.startswith("/"):
            self._pill_icon.set_from_gicon(Gio.FileIcon.new(Gio.File.new_for_path(source)))
        else:
            self._pill_icon.set_from_icon_name(source)
        self._pill_icon.set_pixel_size(round(look.PILL_ICON_SIZE * scale))
        self._pill_title.set_text(content["title"])
        self._pill_value.set_text(content["value"])
        self._pill_value.set_visible(bool(content["value"]))
        width = self._pill_box.measure(Gtk.Orientation.HORIZONTAL, -1)[1]
        height = self._pill_box.measure(Gtk.Orientation.VERTICAL, width)[1]
        placed = look.pill_placement(geometry, scale, current, width, height, pointer)
        Gtk4LayerShell.set_margin(self._pill, Gtk4LayerShell.Edge.LEFT, placed["x"])
        Gtk4LayerShell.set_margin(self._pill, Gtk4LayerShell.Edge.TOP, placed["y"])

    # --- D-Bus

    def _connect_dbus(self) -> None:
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as error:
            _log(f"no session bus: {error.message}")
            return
        for name, handler in (("OverlayState", self._on_overlay_state), ("OverlayDetails", self._on_overlay_details)):
            self._subscriptions.append(self._bus.signal_subscribe(
                identity.DBUS_NAME, identity.DBUS_INTERFACE, name, identity.DBUS_PATH, None,
                Gio.DBusSignalFlags.NONE, handler))
        # Details now and whenever the driver (re)starts.
        self._watch = Gio.bus_watch_name_on_connection(
            self._bus, identity.DBUS_NAME, Gio.BusNameWatcherFlags.NONE,
            lambda *_: self._fetch_details(), self._on_driver_gone)

    def _fetch_details(self) -> None:
        def done(bus, result):
            try:
                (text,) = bus.call_finish(result).unpack()
            except GLib.Error:
                return  # Older drivers have no details; the dial still works.
            self._merge_details(text)

        self._bus.call(identity.DBUS_NAME, identity.DBUS_PATH, identity.DBUS_INTERFACE, "GetOverlayDetails",
                       None, GLib.VariantType("(s)"), Gio.DBusCallFlags.NONE, 1000, None, done)

    def _on_driver_gone(self, *_args) -> None:
        # A driver that stops while the finger is down would leave the dial
        # on screen; nothing touches any more.
        if self.state["enabled"]:
            was_enabled, was_touching = self.state["enabled"], self.state["touching"]
            self.state["enabled"] = self.state["touching"] = False
            self.visibility.update(was_enabled, was_touching)

    def _merge_details(self, text: str) -> None:
        look.merge_details(self.details, text)
        if json.dumps(self._look()) != self._look_key:
            self._apply_geometry()
            self.visibility.look_changed()
        self.layers.update()
        self._update_pill()
        self._update_submenu()

    def _on_overlay_details(self, _bus, _sender, _path, _interface, _signal, parameters) -> None:
        self._merge_details(parameters.unpack()[0])

    def _on_overlay_state(self, _bus, _sender, _path, _interface, _signal, parameters) -> None:
        was_enabled, was_touching = self.state["enabled"], self.state["touching"]
        look.apply_overlay_state(self.state, parameters.unpack())
        self.visibility.update(was_enabled, was_touching)
        self.layers.update()
        self._update_pill()
        self._update_submenu()
