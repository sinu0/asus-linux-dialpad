"""Walks the settings app at several window sizes and reports layout faults.

Run by tests/test_settings_layout.py inside a headless mutter, one window
size per process so the sizes run in parallel:

    python3 tests/layout_probe.py result.json "PX13 at 200 %"

Opens the app on the demo configuration of tools/screenshot_settings.py
(nothing is saved), resizes the window to what monitors from 1080p to 4K
give it, visits every page and the main dialogs, and writes the faults as
JSON: widgets that reach past the window's edge, and windows that cannot
shrink to the size.
"""

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import screenshot_settings as demo  # noqa: E402
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from config.schema import StepType  # noqa: E402

# Window sizes in logical pixels: monitors minus the GNOME top bar.
SIZES = {
    "1080p at 150 %": (1280, 688),
    "PX13 at 200 %": (1440, 868),
    "1080p": (1920, 1048),
    "4K": (3840, 2128),
}
PAGES = ("actions", "profiles", "look", "device", "calibration", "diagnostics")
CALIBRATION_RESULT = {"circle_diameter": 1012, "center_button_diameter": 388, "center_x": 3341, "center_y": 640}
# Long enough for a resize or a new page to be laid out and mapped.
SETTLE_MS = 120


def describe(widget):
    label = ""
    if isinstance(widget, (Gtk.Label, Gtk.Button)):
        label = widget.get_label() or ""
    elif isinstance(widget, Adw.PreferencesRow):
        label = widget.get_title() or ""
    return f"{type(widget).__name__}{f' “{label}”' if label else ''}"


def unfold(widget):
    """Open folded rows (the dial look of profiles and functions) so they count."""
    for expander in demo._descendants(widget, Adw.ExpanderRow):
        expander.set_expanded(True)


def overflowing(window):
    """The outermost widgets that reach past the window's left or right edge."""
    width = window.get_width()
    found = []

    def walk(widget):
        # Overlay scrollbars sit on the edge on purpose.
        if not widget.get_mapped() or isinstance(widget, Gtk.Scrollbar):
            return
        ok, bounds = widget.compute_bounds(window)
        if ok:
            left, right = bounds.get_x(), bounds.get_x() + bounds.get_width()
            if left < -1 or right > width + 1:
                found.append(f"{describe(widget)} spans {left:.0f}–{right:.0f} of {width}")
                return
        child = widget.get_first_child()
        while child is not None:
            walk(child)
            child = child.get_next_sibling()

    walk(window)
    return found


def dialogs(app, profile):
    """Open each main dialog in turn; yields its name while it is shown."""
    segment = profile.segments[0]
    app._show_function_library(profile)
    yield "function library"
    app._show_function_editor(profile, segment)
    yield "function editor"
    for kind in StepType:
        demo.close_dialogs(app)
        app._show_step_dialog(segment, "macro_cw", None, lambda: None)
        dialog = app._window.get_visible_dialog()
        combo = next(demo._descendants(dialog, Adw.ComboRow))
        names = [combo.get_model().get_string(index) for index in range(combo.get_model().get_n_items())]
        labels = [label for label, step_type in demo.app_main.ACTION_TYPES if step_type is kind]
        if not labels or labels[0] not in names:
            continue
        combo.set_selected(names.index(labels[0]))
        yield f"action: {labels[0]}"
    demo.close_dialogs(app)
    app._show_skin_editor(None, {"name": "Probe", "base": "proart"})
    yield "skin editor"
    demo.close_dialogs(app)


def sidebar_faults(app):
    """The list that stands in for Adw.ViewSwitcherSidebar before Libadwaita 1.9
    must follow the pages both ways."""
    sidebar = next((box for box in demo._descendants(app._window, Gtk.ListBox)
                    if box.has_css_class("navigation-sidebar")), None)
    if hasattr(Adw, "ViewSwitcherSidebar"):
        return []
    if sidebar is None:
        return ["no page sidebar"]
    faults = []
    for index, page in enumerate(PAGES):
        app._view_stack.set_visible_child_name(page)
        selected = sidebar.get_selected_row()
        if selected is None or selected.get_index() != index:
            faults.append(f"sidebar does not follow the {page} page")
    for index, page in reversed(list(enumerate(PAGES))):
        sidebar.select_row(sidebar.get_row_at_index(index))
        if app._view_stack.get_visible_child_name() != page:
            faults.append(f"sidebar row {index} does not show the {page} page")
    return faults


def steps(app, result, size_names):
    window = app._window
    profile = app.config.profiles[0]
    result.extend(sidebar_faults(app))
    app._select_profile(profile)
    for size_name in size_names:
        width, height = SIZES[size_name]
        yield from demo.resize(window, width, height)
        minimum = window.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
        if minimum > width:
            result.append(f"{size_name}: the window needs {minimum} px but the screen gives {width}")
        if abs(window.get_width() - width) > 1:
            result.append(f"{size_name}: window is {window.get_width()} px wide, wanted {width}")
        for page in PAGES:
            app._view_stack.set_visible_child_name(page)
            unfold(window)
            yield
            result.extend(f"{size_name}, {page} page: {fault}" for fault in overflowing(window))
        # A finished guided calibration waiting for Keep or Revert.
        app._view_stack.set_visible_child_name("calibration")
        app._apply_calibration(CALIBRATION_RESULT, "proartp16")
        yield
        result.extend(f"{size_name}, calibration review: {fault}" for fault in overflowing(window))
        app._finish_calibration_review(keep=False, quiet=True)
        app._view_stack.set_visible_child_name("actions")
        for dialog_name in dialogs(app, profile):
            unfold(window)
            yield
            result.extend(f"{size_name}, {dialog_name}: {fault}" for fault in overflowing(window))
    app.quit()


def main():
    output = Path(sys.argv[1])
    size_names = sys.argv[2:] or list(SIZES)
    config = demo.demo_config()
    # Show every dial look row: the screen picker and the fade level.
    config.overlay.position = "custom"
    config.overlay.visibility = "fade"
    config.profiles[0].overlay = {"position": "custom", "custom_x": 0.8, "custom_y": 0.7, "visibility": "fade"}
    config.profiles[0].segments[0].overlay = {"position": "custom", "visibility": "fade"}
    demo.app_main.CONFIG_FILE = Path(__file__)
    demo.app_main.load_config = lambda: config
    demo.app_main.load_skins = demo.builtin_skins
    Adw.init()
    app = demo.ScreenshotApp()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    result = []

    def start(_app):
        runner = steps(app, result, size_names)

        def tick():
            try:
                next(runner)
            except StopIteration:
                return GLib.SOURCE_REMOVE
            except Exception:
                # Without this the loop stops but the app keeps running.
                result.append(f"the probe failed:\n{traceback.format_exc()}")
                app.quit()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        GLib.timeout_add(SETTLE_MS, tick)

    app.connect("activate", start)
    app.run([])
    output.write_text(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
