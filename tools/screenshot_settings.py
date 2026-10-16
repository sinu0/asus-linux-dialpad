#!/usr/bin/env python3
"""Take the README screenshots of the settings app.

    python3 tools/screenshot_settings.py [output directory]

Opens the settings app on a demo configuration (default profile plus a few
application profiles), walks through its pages and saves each one as a PNG.
Nothing is written to ~/.config: saving is disabled and only built-in skins
are shown. The window briefly appears on screen while it runs.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib

import gi

gi.require_version("Graphene", "1.0")
# config_app exports main(); import the module itself, which also pins the
# GTK and Adwaita versions.
app_main = importlib.import_module("config_app.main")
from gi.repository import Adw, Gio, GLib, Graphene, Gtk  # noqa: E402

from config.presets import pack_for_app, profile_for_pack  # noqa: E402
from config.schema import _default_config  # noqa: E402
from config.skins import builtin_skins  # noqa: E402

OUTPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "preview"
WIDTH, HEIGHT = 1080, 760
SETTLE_MS = 700


def demo_config():
    config = _default_config()
    default = config.profiles[0]
    profiles = [default]
    for app_id in ("org.kde.krita.desktop", "firefox.desktop", "org.darktable.darktable.desktop"):
        pack = pack_for_app(app_id)
        profile = profile_for_pack(pack)
        profile.app_id = app_id
        profiles.append(profile)
    spotify = profile_for_pack(pack_for_app("spotify.desktop"))
    spotify.mode = "single"
    spotify.single_function = next(
        (segment.title for segment in spotify.segments if "volume" in segment.title.lower()), None
    )
    profiles.append(spotify)
    config.profiles = profiles
    # Shows the light and dark badges in the skin gallery.
    config.overlay.follow_system_style = True
    return config


class ScreenshotApp(app_main.Application):
    def _save_config(self):
        self._save_source = 0
        return GLib.SOURCE_REMOVE


def capture(window, name):
    # No keyboard focus ring in the pictures.
    window.set_focus_visible(False)
    width, height = window.get_width(), window.get_height()
    snapshot = Gtk.Snapshot()
    Gtk.WidgetPaintable.new(window).snapshot(snapshot, width, height)
    node = snapshot.to_node()
    bounds = Graphene.Rect().init(0, 0, width, height)
    texture = window.get_renderer().render_texture(node, bounds)
    path = OUTPUT / f"{name}.png"
    texture.save_to_png(str(path))
    print(f"wrote {path}")


def scroll_to(widget):
    scrolled = widget.get_ancestor(Gtk.ScrolledWindow)
    ok, point = widget.compute_point(scrolled.get_child(), Graphene.Point().init(0, 0))
    if ok:
        scrolled.get_vadjustment().set_value(max(0, point.y - 12))


def close_dialogs(app):
    dialog = app._window.get_visible_dialog()
    if dialog is not None:
        dialog.force_close()


def steps(app):
    window = app._window
    config = app.config
    default, krita, _firefox, darktable = config.profiles[:4]

    def page(name, size=(WIDTH, HEIGHT)):
        close_dialogs(app)
        window.set_default_size(*size)
        app._view_stack.set_visible_child_name(name)

    page("actions", (WIDTH, 1168))
    app._select_profile(default)
    yield
    capture(window, "settings-dial-controls")

    page("profiles")
    yield
    capture(window, "settings-profiles")

    page("actions")
    app._select_profile(krita)
    yield
    app._show_function_library(krita)
    yield
    capture(window, "settings-library")

    close_dialogs(app)
    app._select_profile(darktable)
    yield
    zoom = next(segment for segment in darktable.segments if segment.title == "Zoom")
    app._show_function_editor(darktable, zoom)
    yield
    capture(window, "settings-function-editor")

    page("calibration")
    yield
    capture(window, "settings-calibration")

    page("device")
    yield
    capture(window, "settings-behaviour")

    scroll_to(app._skin_gallery.get_ancestor(Adw.PreferencesGroup))
    yield
    capture(window, "settings-skins")

    app._show_skin_editor(None, {"name": "My ProArt bronze", "base": "proart",
                                 "palette": {"rim": "#f5d1aa80", "pointer": "#ffe2bf"}})
    yield
    capture(window, "settings-skin-editor")

    close_dialogs(app)
    app.quit()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    demo = demo_config()
    # Never touch the user's configuration or skins.
    app_main.CONFIG_FILE = Path(__file__)
    app_main.load_config = lambda: demo
    app_main.load_skins = builtin_skins
    Adw.init()
    app = ScreenshotApp()
    # Run beside an open settings app instead of activating it.
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)

    def start(_app):
        runner = steps(app)

        def tick():
            try:
                next(runner)
            except StopIteration:
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(SETTLE_MS, tick)

    app.connect("activate", start)
    app.run([])


if __name__ == "__main__":
    main()
