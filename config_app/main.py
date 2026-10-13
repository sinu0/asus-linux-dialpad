import copy
import json
import math
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import gi

gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from config.labels import describe_macro, describe_step, format_keys
from config.presets import (
    FUNCTION_LIBRARY,
    LIBRARY_CATEGORIES,
    pack_for_app,
    profile_for_app,
    segment_color,
)
from config.schema import (
    CONFIG_DIR,
    CONFIG_FILE,
    DARKTABLE_APP_ID,
    OVERLAY_POSITIONS,
    DialPadConfig,
    MacroStep,
    Profile,
    Segment,
    StepType,
    _decoder,
    _encoder,
    darktable_colour_labels_segment,
    load_config,
    save_config,
)
from config.migrate import migrate_old_format


DBUS_NAME = "io.github.asuslinuxdrivers.DialPad"
DBUS_PATH = "/io/github/asuslinuxdrivers/DialPad"
DBUS_INTERFACE = DBUS_NAME
STYLE_FILE = Path(__file__).with_name("style.css")
DEFAULT_ACCENT = "#e7b98d"
# The PX13 touchpad range; replaced by the driver's report when available.
DEFAULT_TOUCHPAD = (4010, 2443)

TRIGGERS = (
    ("macro_cw", "Turn clockwise", "object-rotate-right-symbolic",
     "Runs once per rotation step"),
    ("macro_ccw", "Turn counter-clockwise", "object-rotate-left-symbolic",
     "Runs once per rotation step"),
    ("macro_center", "Tap", "input-touchpad-symbolic",
     "Tap the centre while the function is active; a function with only a tap "
     "action runs straight from its menu sector"),
)

ACTION_TYPES = (
    ("Keyboard shortcut", StepType.KEYSTROKE),
    ("Media key", StepType.MEDIA),
    ("Volume", StepType.VOLUME),
    ("Brightness", StepType.BRIGHTNESS),
    ("Scroll", StepType.SCROLL),
    ("Command", StepType.SHELL),
    ("Wait", StepType.DELAY),
)

POSITION_LABELS = {
    "center": "Centre of the screen",
    "lower": "Slightly below centre",
    "bottom": "Bottom of the screen",
    "top": "Top of the screen",
}


def _load_proart_style():
    """Apply the local, intentionally restrained ProArt visual treatment."""
    display = Gdk.Display.get_default()
    if display is None or not STYLE_FILE.exists():
        return
    provider = Gtk.CssProvider()
    try:
        provider.load_from_path(str(STYLE_FILE))
    except GLib.Error:
        return
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def _clear_children(widget):
    child = widget.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        widget.remove(child)
        child = next_child


def _hex_to_rgb(text, fallback=DEFAULT_ACCENT):
    rgba = Gdk.RGBA()
    if not text or not rgba.parse(text):
        rgba.parse(fallback)
    return rgba.red, rgba.green, rgba.blue


def _rgba_to_hex(rgba):
    return "#{:02x}{:02x}{:02x}".format(
        round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)
    )


def _icon_button(icon_name, tooltip, callback, *css):
    button = Gtk.Button.new_from_icon_name(icon_name)
    button.set_tooltip_text(tooltip)
    button.set_valign(Gtk.Align.CENTER)
    button.add_css_class("flat")
    for name in css:
        button.add_css_class(name)
    button.connect("clicked", lambda _button: callback())
    return button


def _spin_row(title, subtitle, value, minimum, maximum, step, digits, changed):
    row = Adw.SpinRow.new_with_range(minimum, maximum, step)
    row.set_title(title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_digits(digits)
    row.set_value(value)
    row.connect("notify::value", lambda row, _param: changed(row.get_value()))
    return row


def _switch_row(title, subtitle, active, changed):
    row = Adw.SwitchRow(title=title)
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_active(active)
    row.connect("notify::active", lambda row, _param: changed(row.get_active()))
    return row


def _combo_row(title, subtitle, labels, selected, changed):
    row = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels))
    if subtitle:
        row.set_subtitle(subtitle)
    row.set_selected(selected)
    row.connect("notify::selected", lambda row, _param: changed(row.get_selected()))
    return row


def _colour_swatch(colour, size=14):
    area = Gtk.DrawingArea()
    area.set_content_width(size)
    area.set_content_height(size)
    area.set_valign(Gtk.Align.CENTER)

    def draw(_area, cr, width, height):
        cr.arc(width / 2, height / 2, min(width, height) / 2 - 0.5, 0, 2 * math.pi)
        cr.set_source_rgb(*_hex_to_rgb(colour))
        cr.fill()

    area.set_draw_func(draw)
    return area


def draw_dial(cr, width, height, segments, active_title=None, title_text=None, mode="multi"):
    """Paint a miniature of the overlay dial, coloured like the real one."""
    size = max(1, min(width, height))
    scale = size / 190
    cx, cy = width / 2, height / 2
    outer, inner, centre = 82 * scale, 49 * scale, 42 * scale

    cr.save()
    cr.arc(cx + 2 * scale, cy + 4 * scale, outer, 0, 2 * math.pi)
    cr.set_source_rgba(0, 0, 0, 0.4)
    cr.fill()
    cr.arc(cx, cy, outer, 0, 2 * math.pi)
    cr.set_source_rgba(0.13, 0.135, 0.16, 1)
    cr.fill()

    if mode == "single" and segments:
        segment = segments[0]
        colour = segment_color(segment)
        cr.set_line_width((outer - inner) - 12 * scale)
        cr.set_source_rgba(0.21, 0.215, 0.25, 1)
        cr.arc(cx, cy, (outer + inner) / 2 - 2 * scale, 0, 2 * math.pi)
        cr.stroke()
        cr.set_source_rgb(*_hex_to_rgb(colour))
        cr.arc(cx, cy, (outer + inner) / 2 - 2 * scale, -math.pi / 2, math.pi * 0.9)
        cr.stroke()
        title_text = title_text or segment.title
    else:
        count = max(4, len(segments))
        angle = 2 * math.pi / count
        for index in range(count):
            segment = segments[index] if index < len(segments) else None
            start = index * angle - math.pi / 2 + 0.018
            end = (index + 1) * angle - math.pi / 2 - 0.018
            active = segment is not None and segment.title == active_title
            cr.move_to(cx + math.cos(start) * inner, cy + math.sin(start) * inner)
            cr.arc(cx, cy, outer - 5 * scale, start, end)
            cr.arc_negative(cx, cy, inner, end, start)
            cr.close_path()
            if segment is None:
                cr.set_source_rgba(0.18, 0.185, 0.215, 1)
            elif active:
                red, green, blue = _hex_to_rgb(segment_color(segment, index))
                cr.set_source_rgba(red * 0.62 + 0.1, green * 0.62 + 0.1, blue * 0.62 + 0.11, 1)
            else:
                cr.set_source_rgba(0.25, 0.26, 0.30, 1)
            cr.fill()

            if segment is not None:
                cr.set_line_width((4 if active else 2.4) * scale)
                cr.set_source_rgb(*_hex_to_rgb(segment_color(segment, index)))
                cr.arc(cx, cy, inner + 2.5 * scale, start + 0.05, end - 0.05)
                cr.stroke()
                mid = (start + end) / 2
                x = cx + math.cos(mid) * 66 * scale
                y = cy + math.sin(mid) * 66 * scale
                cr.set_font_size(7.5 * scale)
                cr.select_font_face("Sans", 0, 1)
                label = segment.title if len(segment.title) <= 9 else segment.title[:8] + "…"
                extents = cr.text_extents(label)
                cr.move_to(x - extents.width / 2 - extents.x_bearing, y + extents.height / 2)
                cr.set_source_rgba(0.97, 0.86, 0.75, 1 if active else 0.72)
                cr.show_text(label)

    cr.arc(cx, cy, centre, 0, 2 * math.pi)
    cr.set_source_rgba(0.18, 0.185, 0.215, 1)
    cr.fill()
    cr.arc(cx, cy, centre, 0, 2 * math.pi)
    cr.set_line_width(1.2 * scale)
    cr.set_source_rgba(0.82, 0.66, 0.51, 0.8)
    cr.stroke()
    text = title_text or "DialPad"
    if len(text) > 12:
        text = text[:11] + "…"
    cr.set_font_size(10 * scale)
    cr.select_font_face("Sans", 0, 1)
    extents = cr.text_extents(text)
    cr.move_to(cx - extents.width / 2 - extents.x_bearing, cy + extents.height / 2)
    cr.set_source_rgba(0.97, 0.86, 0.75, 1)
    cr.show_text(text)
    cr.restore()


class Application(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.asuslinuxdrivers.DialPadControl")
        self.config: DialPadConfig | None = None
        self._save_source = 0
        self._window = None
        self._toasts = None
        self._view_stack = None
        self._profiles_box = None
        self._actions_box = None
        self._actions_heading = None
        self._actions_subtitle = None
        self._profile_dropdown = None
        self._profile_dropdown_handler = 0
        self._selected_profile: Profile | None = None
        self._preview_title = None
        self._dial_preview = None
        self._diagnostics_rows = {}
        self._session_bus = None
        self._calibration_preview = None
        self._touchpad_size = DEFAULT_TOUCHPAD
        self._geometry_rows = {}
        self._calibration_row = None
        self._calibration_start = None
        self._calibration_cancel = None
        self._calibration_points = []
        self._calibration_signal = 0

    # --- lifecycle --------------------------------------------------------

    def do_activate(self):
        if self._window is not None:
            self._window.present()
            return

        self.config = (
            migrate_old_format(layout_name=self._detect_layout(), config_dir=str(PROJECT_ROOT))
            if not CONFIG_FILE.exists()
            else load_config()
        )
        self._selected_profile = self._default_profile()

        _load_proart_style()
        self._window = Adw.ApplicationWindow(application=self)
        self._window.set_title("ProArt DialPad")
        self._window.set_default_size(1080, 760)
        self._window.add_css_class("proart-window")

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        brand.add_css_class("proart-brand")
        emblem = Gtk.Image.new_from_icon_name("input-dialpad-symbolic")
        emblem.set_pixel_size(20)
        brand.append(emblem)
        title = Gtk.Label(label="ProArt DialPad", xalign=0)
        title.add_css_class("title-4")
        brand.append(title)
        header.set_title_widget(brand)
        toolbar.add_top_bar(header)

        self._view_stack = Adw.ViewStack()
        pages = (
            (self._build_actions_page(), "actions", "Dial Controls", "input-dialpad-symbolic"),
            (self._build_profiles_page(), "profiles", "Apps & Profiles", "applications-graphics-symbolic"),
            (self._build_behaviour_page(), "device", "Behaviour", "preferences-system-symbolic"),
            (self._build_calibration_page(), "calibration", "Calibration", "find-location-symbolic"),
            (self._build_diagnostics_page(), "diagnostics", "Driver", "utilities-terminal-symbolic"),
        )
        for child, name, page_title, icon_name in pages:
            page = self._view_stack.add_titled(child, name, page_title)
            page.set_icon_name(icon_name)
        self._view_stack.connect("notify::visible-child", self._on_visible_page_changed)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        sidebar = Adw.ViewSwitcherSidebar()
        sidebar.set_stack(self._view_stack)
        sidebar.set_size_request(218, -1)
        sidebar.add_css_class("proart-sidebar")
        content.append(sidebar)
        self._view_stack.set_hexpand(True)
        content.append(self._view_stack)
        toolbar.set_content(content)

        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(toolbar)
        self._window.set_content(self._toasts)
        self._refresh_all()
        self._window.present()
        self._refresh_diagnostics()

    def _detect_layout(self):
        """Return the layout the installed driver runs with (geometry differs per model)."""
        connection = self._get_session_bus()
        if connection is not None:
            try:
                reply = connection.call_sync(
                    DBUS_NAME, DBUS_PATH, DBUS_INTERFACE, "GetStatus", None,
                    GLib.VariantType.new("(a{sv})"), Gio.DBusCallFlags.NONE, 1500, None,
                )
                layout = reply.unpack()[0].get("layout")
                if layout:
                    return str(layout)
            except GLib.Error:
                pass
        # The service passes the layout as the first argument of dialpad.py.
        for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
            try:
                args = cmdline.read_bytes().split(b"\0")
            except OSError:
                continue
            for index, arg in enumerate(args[:-1]):
                if arg.endswith(b"dialpad.py") and args[index + 1]:
                    return args[index + 1].decode(errors="ignore")
        return "proartp16"

    def do_shutdown(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
            if self.config is not None:
                save_config(self.config)
        Adw.Application.do_shutdown(self)

    def _toast(self, text):
        if self._toasts is not None:
            self._toasts.add_toast(Adw.Toast.new(text))

    def _schedule_save(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
        self._save_source = GLib.timeout_add(400, self._save_config)

    def _save_config(self):
        self._save_source = 0
        if self.config is not None:
            save_config(self.config)
            self._call_driver("ReloadConfig")
        return GLib.SOURCE_REMOVE

    def _get_session_bus(self):
        if self._session_bus is not None:
            return self._session_bus
        try:
            self._session_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            return None
        return self._session_bus

    def _call_driver(self, method, reply="(b)", callback=None):
        connection = self._get_session_bus()
        if connection is None:
            if callback is not None:
                callback(None, None)
            return
        connection.call(
            DBUS_NAME,
            DBUS_PATH,
            DBUS_INTERFACE,
            method,
            None,
            GLib.VariantType.new(reply),
            Gio.DBusCallFlags.NONE,
            3000,
            None,
            callback,
        )

    def _changed(self, rebuild=True):
        """Persist the configuration and refresh what depends on it."""
        if rebuild:
            self._refresh_all()
        elif self._dial_preview is not None:
            self._dial_preview.queue_draw()
        self._schedule_save()

    # --- profile helpers ----------------------------------------------------

    def _default_profile(self):
        if self.config is None:
            return None
        for profile in self.config.profiles:
            if profile.app_id is None:
                return profile
        return self.config.profiles[0] if self.config.profiles else None

    def _current_profile(self):
        if self.config is None:
            return None
        if self._selected_profile in self.config.profiles:
            return self._selected_profile
        self._selected_profile = self._default_profile()
        return self._selected_profile

    @staticmethod
    def _profile_summary(profile):
        active = profile.active_segments()
        if not active:
            return "No functions — falls back to the default profile"
        if profile.mode == "single":
            segment = profile.single_segment()
            return f"Single function · {segment.title}"
        return f"Radial menu · {len(active)} function{'s' if len(active) != 1 else ''}"

    @staticmethod
    def _app_icon(app_id):
        if app_id:
            try:
                info = Gio.DesktopAppInfo.new(app_id)
            except TypeError:
                info = None
            if info is not None and info.get_icon() is not None:
                image = Gtk.Image.new_from_gicon(info.get_icon())
                image.set_pixel_size(32)
                return image
        image = Gtk.Image.new_from_icon_name(
            "input-dialpad-symbolic" if app_id is None else "application-x-executable-symbolic"
        )
        image.set_pixel_size(24)
        return image

    @staticmethod
    def _unique_title(profile, title, ignore=None):
        existing = {segment.title for segment in profile.segments if segment is not ignore}
        if title not in existing:
            return title
        index = 2
        while f"{title} {index}" in existing:
            index += 1
        return f"{title} {index}"

    def _select_profile(self, profile, show=True):
        self._selected_profile = profile
        self._preview_title = None
        self._refresh_all()
        if show and self._view_stack is not None:
            self._view_stack.set_visible_child_name("actions")

    def _refresh_all(self):
        self._refresh_profiles_page()
        self._rebuild_actions_page()

    def _on_visible_page_changed(self, stack, _param):
        name = stack.get_visible_child_name()
        if name == "actions":
            self._rebuild_actions_page()
        elif name == "diagnostics":
            self._refresh_diagnostics()

    def _scrolled_content(self, content, width=760):
        clamp = Adw.Clamp()
        clamp.set_maximum_size(width)
        clamp.set_child(content)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(clamp)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        return scroll

    @staticmethod
    def _page_box():
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(18)
        content.set_margin_bottom(36)
        content.set_margin_start(12)
        content.set_margin_end(12)
        return content

    # --- Apps & Profiles ------------------------------------------------------

    def _build_profiles_page(self):
        content = self._page_box()

        intro = Gtk.Label(
            label=(
                "Like ASUS Dial, the DialPad switches profile with the focused "
                "application. Applications without their own profile use the default one."
            ),
            xalign=0,
            wrap=True,
        )
        intro.add_css_class("dim-label")
        content.append(intro)

        self._profiles_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.append(self._profiles_box)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_app = Gtk.Button(label="Add application…")
        add_app.add_css_class("suggested-action")
        add_app.connect("clicked", lambda _button: self._show_app_picker())
        buttons.append(add_app)
        add_default = Gtk.Button(label="Add default profile")
        add_default.connect("clicked", lambda _button: self._show_name_dialog("New default profile", "", self._create_default_profile))
        buttons.append(add_default)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        buttons.append(spacer)
        import_button = Gtk.Button(label="Import…")
        import_button.connect("clicked", lambda _button: self._import_profiles())
        buttons.append(import_button)
        export_button = Gtk.Button(label="Export…")
        export_button.connect("clicked", lambda _button: self._export_profiles())
        buttons.append(export_button)
        content.append(buttons)
        return self._scrolled_content(content)

    def _refresh_profiles_page(self):
        if self._profiles_box is None or self.config is None:
            return
        _clear_children(self._profiles_box)
        default_group = Adw.PreferencesGroup(
            title="Default profiles",
            description="Used when the focused application has no profile. The first one is active.",
        )
        app_group = Adw.PreferencesGroup(
            title="Application profiles",
            description="Switched automatically when the application gains focus.",
        )
        for profile in self.config.profiles:
            group = default_group if profile.app_id is None else app_group
            group.add(self._profile_row(profile))
        self._profiles_box.append(default_group)
        self._profiles_box.append(app_group)

    def _profile_row(self, profile):
        row = Adw.ActionRow(title=GLib.markup_escape_text(profile.name))
        subtitle = self._profile_summary(profile)
        if profile.app_id:
            subtitle = f"{subtitle}\n{profile.app_id}"
        row.set_subtitle(GLib.markup_escape_text(subtitle))
        row.set_subtitle_lines(2)
        row.add_prefix(self._app_icon(profile.app_id))
        if profile is self._current_profile():
            row.add_css_class("proart-selected-row")
        row.set_activatable(True)
        row.connect("activated", lambda _row: self._select_profile(profile))

        row.add_suffix(_icon_button("go-next-symbolic", "Edit dial controls", lambda: self._select_profile(profile)))
        row.add_suffix(_icon_button("edit-copy-symbolic", "Duplicate profile", lambda: self._duplicate_profile(profile)))
        row.add_suffix(_icon_button(
            "document-edit-symbolic", "Rename profile",
            lambda: self._show_name_dialog("Rename profile", profile.name, lambda name: self._rename_profile(profile, name)),
        ))
        row.add_suffix(_icon_button("user-trash-symbolic", "Remove profile", lambda: self._confirm_remove_profile(profile), "error"))
        return row

    def _create_default_profile(self, name):
        profile = Profile(name=name, app_id=None)
        self.config.profiles.append(profile)
        self._select_profile(profile)
        self._schedule_save()

    def _rename_profile(self, profile, name):
        profile.name = name
        self._changed()

    def _duplicate_profile(self, profile):
        clone = copy.deepcopy(profile)
        clone.name = f"{profile.name} (copy)"
        # A copy of an application profile would shadow the original.
        clone.app_id = None
        self.config.profiles.insert(self.config.profiles.index(profile) + 1, clone)
        self._select_profile(clone, show=False)
        self._schedule_save()
        self._toast(f"Created “{clone.name}” as a default profile")

    def _confirm_remove_profile(self, profile):
        dialog = Adw.AlertDialog(
            heading=f"Remove “{profile.name}”?",
            body="Its functions and actions will be deleted.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")

        def respond(_dialog, response):
            if response == "remove" and profile in self.config.profiles:
                self.config.profiles.remove(profile)
                if self._selected_profile is profile:
                    self._selected_profile = self._default_profile()
                self._changed()

        dialog.connect("response", respond)
        dialog.present(self._window)

    def _show_name_dialog(self, heading, value, accept):
        dialog = Adw.AlertDialog(heading=heading)
        entry = Gtk.Entry()
        entry.set_text(value)
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("ok", "Save")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("ok")
        dialog.set_close_response("cancel")

        def respond(_dialog, response):
            name = entry.get_text().strip()
            if response == "ok" and name:
                accept(name)

        dialog.connect("response", respond)
        dialog.present(self._window)
        entry.grab_focus()

    def _show_app_picker(self):
        dialog = Adw.Dialog(title="Add application", content_width=520, content_height=620)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_bottom(12)
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search applications")
        box.append(search)
        note = Gtk.Label(
            label="Applications marked “Pre-programmed” start with ready functions.",
            xalign=0, wrap=True,
        )
        note.add_css_class("dim-label")
        note.add_css_class("caption")
        box.append(note)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(listbox)
        box.append(scroll)
        view.set_content(box)
        dialog.set_child(view)

        existing = {profile.app_id for profile in self.config.profiles if profile.app_id}
        apps = [app for app in Gio.AppInfo.get_all() if app.get_id() and app.should_show()]
        apps.sort(key=lambda app: (pack_for_app(app.get_id()) is None, app.get_display_name().lower()))

        def choose(app):
            dialog.close()
            self._add_application(app.get_display_name(), app.get_id())

        def rebuild():
            _clear_children(listbox)
            query = search.get_text().strip().lower()
            for app in apps:
                if query and query not in app.get_display_name().lower() and query not in app.get_id().lower():
                    continue
                row = Adw.ActionRow(title=GLib.markup_escape_text(app.get_display_name()))
                row.set_subtitle(GLib.markup_escape_text(app.get_id()))
                icon = app.get_icon()
                image = Gtk.Image.new_from_gicon(icon) if icon else Gtk.Image.new_from_icon_name("application-x-executable-symbolic")
                image.set_pixel_size(32)
                row.add_prefix(image)
                pack = pack_for_app(app.get_id()) or (app.get_id() == DARKTABLE_APP_ID)
                if app.get_id() in existing:
                    badge = Gtk.Label(label="Has profile")
                    badge.add_css_class("dim-label")
                    row.add_suffix(badge)
                elif pack:
                    badge = Gtk.Label(label="Pre-programmed")
                    badge.add_css_class("proart-badge")
                    badge.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(badge)
                row.set_activatable(True)
                row.connect("activated", lambda _row, app=app: choose(app))
                listbox.append(row)

        search.connect("search-changed", lambda _entry: rebuild())
        rebuild()
        dialog.present(self._window)
        search.grab_focus()

    def _add_application(self, name, app_id):
        for profile in self.config.profiles:
            if profile.app_id == app_id:
                self._select_profile(profile)
                return
        profile = profile_for_app(name, app_id)
        self.config.profiles.append(profile)
        self._select_profile(profile)
        self._schedule_save()
        if profile.segments:
            self._toast(f"Added {len(profile.segments)} pre-programmed functions for {name}")

    def _export_profiles(self):
        dialog = Gtk.FileDialog(title="Export DialPad profiles", initial_name="dialpad-profiles.json")

        def finish(file_dialog, result):
            try:
                file = file_dialog.save_finish(result)
            except GLib.Error:
                return
            data = {
                "dialpad_profiles": 1,
                "profiles": [_encoder(profile) for profile in self.config.profiles],
            }
            try:
                Path(file.get_path()).write_text(json.dumps(data, indent=2) + "\n")
            except OSError as error:
                self._toast(f"Export failed: {error.strerror}")
                return
            self._toast(f"Exported {len(self.config.profiles)} profiles")

        dialog.save(self._window, None, finish)

    def _import_profiles(self):
        dialog = Gtk.FileDialog(title="Import DialPad profiles")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        json_filter = Gtk.FileFilter()
        json_filter.set_name("JSON")
        json_filter.add_suffix("json")
        filters.append(json_filter)
        dialog.set_filters(filters)

        def finish(file_dialog, result):
            try:
                file = file_dialog.open_finish(result)
                data = json.loads(Path(file.get_path()).read_text())
                profiles = [_decoder(item, Profile) for item in data.get("profiles", [])]
            except (GLib.Error, OSError, ValueError, KeyError, TypeError) as error:
                self._toast(f"Import failed: {error}")
                return
            replaced = 0
            for profile in profiles:
                existing = next(
                    (item for item in self.config.profiles if profile.app_id and item.app_id == profile.app_id),
                    None,
                )
                if existing is not None:
                    self.config.profiles[self.config.profiles.index(existing)] = profile
                    replaced += 1
                else:
                    self.config.profiles.append(profile)
            self._changed()
            message = f"Imported {len(profiles)} profiles"
            if replaced:
                message += f" ({replaced} replaced)"
            self._toast(message)

        dialog.open(self._window, None, finish)

    # --- Dial Controls --------------------------------------------------------

    def _build_actions_page(self):
        content = self._page_box()

        hero = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        hero.add_css_class("proart-hero")
        copy_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        copy_box.set_valign(Gtk.Align.CENTER)
        copy_box.set_hexpand(True)
        eyebrow = Gtk.Label(label="DIAL CONTROLS", xalign=0)
        eyebrow.add_css_class("proart-eyebrow")
        copy_box.append(eyebrow)
        self._actions_heading = Gtk.Label(xalign=0)
        self._actions_heading.add_css_class("title-1")
        self._actions_heading.set_ellipsize(3)
        copy_box.append(self._actions_heading)
        self._actions_subtitle = Gtk.Label(xalign=0, wrap=True)
        self._actions_subtitle.add_css_class("dim-label")
        copy_box.append(self._actions_subtitle)

        switcher = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        switcher.set_margin_top(8)
        label = Gtk.Label(label="Profile")
        label.add_css_class("caption-heading")
        switcher.append(label)
        self._profile_dropdown = Gtk.DropDown.new(Gtk.StringList.new([]), None)
        self._profile_dropdown_handler = self._profile_dropdown.connect(
            "notify::selected", self._on_profile_dropdown
        )
        switcher.append(self._profile_dropdown)
        copy_box.append(switcher)
        hero.append(copy_box)

        self._dial_preview = Gtk.DrawingArea()
        self._dial_preview.set_content_width(200)
        self._dial_preview.set_content_height(200)
        self._dial_preview.set_draw_func(self._draw_dial_preview)
        self._dial_preview.set_valign(Gtk.Align.CENTER)
        self._dial_preview.set_tooltip_text("Click a segment to edit that function")
        click = Gtk.GestureClick.new()
        click.connect("pressed", self._on_preview_clicked)
        self._dial_preview.add_controller(click)
        hero.append(self._dial_preview)
        content.append(hero)

        self._actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.append(self._actions_box)
        return self._scrolled_content(content)

    def _on_profile_dropdown(self, dropdown, _param):
        index = dropdown.get_selected()
        if self.config is None or not 0 <= index < len(self.config.profiles):
            return
        profile = self.config.profiles[index]
        if profile is not self._current_profile():
            GLib.idle_add(lambda: self._select_profile(profile, show=False) and False)

    def _sync_profile_dropdown(self):
        if self._profile_dropdown is None or self.config is None:
            return
        self._profile_dropdown.handler_block(self._profile_dropdown_handler)
        labels = [
            profile.name if profile.app_id is None else f"{profile.name}  ·  app"
            for profile in self.config.profiles
        ]
        self._profile_dropdown.set_model(Gtk.StringList.new(labels))
        profile = self._current_profile()
        if profile in self.config.profiles:
            self._profile_dropdown.set_selected(self.config.profiles.index(profile))
        self._profile_dropdown.handler_unblock(self._profile_dropdown_handler)

    def _rebuild_actions_page(self):
        if self._actions_box is None or self._actions_heading is None:
            return
        _clear_children(self._actions_box)
        self._sync_profile_dropdown()
        profile = self._current_profile()
        if profile is None:
            self._actions_heading.set_label("No profile")
            self._actions_subtitle.set_label("Create a profile on the Apps & Profiles page.")
            return

        self._actions_heading.set_label(profile.name)
        self._actions_subtitle.set_label(
            self._profile_summary(profile)
            + (f" · {profile.app_id}" if profile.app_id else " · default profile")
        )
        self._actions_box.append(self._profile_settings_group(profile))
        self._actions_box.append(self._functions_group(profile))
        if self._dial_preview is not None:
            self._dial_preview.queue_draw()

    def _profile_settings_group(self, profile):
        group = Adw.PreferencesGroup(
            title="Profile behaviour",
            description="Mode, sensitivity and scroll speed apply only to this profile.",
        )

        mode = _combo_row(
            "Dial mode",
            "Radial menu with several functions, or the dial bound to one function",
            ["Radial menu", "Single function"],
            1 if profile.mode == "single" else 0,
            lambda index: self._set_profile_mode(profile, index),
        )
        group.add(mode)

        active = profile.active_segments()
        if profile.mode == "single" and active:
            titles = [segment.title for segment in active]
            selected = profile.single_segment()
            group.add(_combo_row(
                "Bound function",
                "Turning the dial always controls this function",
                titles,
                titles.index(selected.title) if selected else 0,
                lambda index: self._set_single_function(profile, titles[index]),
            ))

        group.add(_spin_row(
            "Sensitivity",
            "Higher values need less rotation per step",
            profile.sensitivity, 0.25, 4.0, 0.05, 2,
            lambda value: self._set_profile_value(profile, "sensitivity", round(value, 2)),
        ))
        group.add(_spin_row(
            "Scroll speed",
            "Multiplies scroll distance for Scroll and Zoom functions",
            profile.scroll_speed, 0.25, 4.0, 0.05, 2,
            lambda value: self._set_profile_value(profile, "scroll_speed", round(value, 2)),
        ))
        if profile.mode != "single":
            group.add(_switch_row(
                "Remember last function",
                "Reopen the last used function instead of the menu",
                profile.remember_last,
                lambda active: self._set_profile_value(profile, "remember_last", active),
            ))
        return group

    def _functions_group(self, profile):
        group = Adw.PreferencesGroup(
            title="Functions",
            description=(
                "Shown clockwise from the top of the dial. Click a function to edit "
                "its rotation and tap actions."
            ),
        )
        add = Gtk.Button()
        add.add_css_class("suggested-action")
        add.set_child(Adw.ButtonContent(icon_name="list-add-symbolic", label="Add function"))
        add.set_valign(Gtk.Align.CENTER)
        add.connect("clicked", lambda _button: self._show_function_library(profile))
        group.set_header_suffix(add)

        if not profile.segments:
            empty = Adw.ActionRow(
                title="No functions yet",
                subtitle="Add functions from the library or apply a pre-programmed pack.",
            )
            empty.add_prefix(Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
            group.add(empty)

        pack = pack_for_app(profile.app_id)
        if pack is not None and len(profile.segments) < 3:
            row = Adw.ActionRow(
                title=f"Pre-programmed functions for {pack.name}",
                subtitle=", ".join(segment.title for segment in pack.factory()),
            )
            row.add_prefix(Gtk.Image.new_from_icon_name("starred-symbolic"))
            apply = Gtk.Button(label="Add all")
            apply.set_valign(Gtk.Align.CENTER)
            apply.connect("clicked", lambda _button: self._apply_pack(profile, pack))
            row.add_suffix(apply)
            group.add(row)

        last = len(profile.segments) - 1
        for index, segment in enumerate(profile.segments):
            group.add(self._function_row(profile, segment, index, last))
        return group

    def _function_row(self, profile, segment, index, last):
        row = Adw.ActionRow(title=GLib.markup_escape_text(segment.title))
        parts = []
        ccw, cw, tap = (describe_macro(segment.macro_ccw), describe_macro(segment.macro_cw),
                        describe_macro(segment.macro_center))
        if ccw or cw:
            parts.append(f"↺ {ccw or '—'}   ↻ {cw or '—'}")
        if tap:
            parts.append(f"Tap: {tap}")
        if segment.value_command:
            parts.append(f"shows value{(' in ' + segment.unit) if segment.unit else ''}")
        row.set_subtitle(GLib.markup_escape_text("  ·  ".join(parts) or "No actions yet"))
        row.add_prefix(_colour_swatch(segment_color(segment, index), 16))
        if not segment.enabled:
            row.add_css_class("dim-label")
        row.set_activatable(True)
        row.connect("activated", lambda _row: self._show_function_editor(profile, segment))

        up = _icon_button("go-up-symbolic", "Move earlier on the dial", lambda: self._move_segment(profile, segment, -1))
        up.set_sensitive(index > 0)
        row.add_suffix(up)
        down = _icon_button("go-down-symbolic", "Move later on the dial", lambda: self._move_segment(profile, segment, 1))
        down.set_sensitive(index < last)
        row.add_suffix(down)

        toggle = Gtk.Switch()
        toggle.set_valign(Gtk.Align.CENTER)
        toggle.set_active(segment.enabled)
        toggle.set_tooltip_text("Show this function on the dial")
        toggle.connect("notify::active", lambda switch, _param: self._set_segment_enabled(segment, switch.get_active()))
        row.add_suffix(toggle)
        row.add_suffix(_icon_button("user-trash-symbolic", "Remove function", lambda: self._remove_segment(profile, segment), "error"))
        return row

    def _set_profile_mode(self, profile, index):
        mode = "single" if index == 1 else "multi"
        if profile.mode != mode:
            profile.mode = mode
            GLib.idle_add(lambda: self._changed() and False)

    def _set_single_function(self, profile, title):
        if profile.single_function != title:
            profile.single_function = title
            self._changed(rebuild=False)

    def _set_profile_value(self, profile, attribute, value):
        if getattr(profile, attribute) != value:
            setattr(profile, attribute, value)
            self._changed(rebuild=False)

    def _set_segment_enabled(self, segment, enabled):
        if segment.enabled != enabled:
            segment.enabled = enabled
            GLib.idle_add(lambda: self._changed() and False)

    def _move_segment(self, profile, segment, offset):
        index = profile.segments.index(segment)
        target = index + offset
        if 0 <= target < len(profile.segments):
            profile.segments[index], profile.segments[target] = profile.segments[target], segment
            self._changed()

    def _remove_segment(self, profile, segment):
        if segment in profile.segments:
            profile.segments.remove(segment)
            if profile.single_function == segment.title:
                profile.single_function = None
            self._changed()
            self._toast(f"Removed “{segment.title}”")

    def _apply_pack(self, profile, pack):
        for segment in pack.factory():
            segment.title = self._unique_title(profile, segment.title)
            profile.segments.append(segment)
        self._changed()
        self._toast(f"Added the {pack.name} functions")

    def _preview_segments(self, profile):
        if profile is None:
            return []
        if profile.mode == "single":
            segment = profile.single_segment()
            return [segment] if segment else []
        return profile.active_segments()

    def _draw_dial_preview(self, _area, cr, width, height):
        profile = self._current_profile()
        segments = self._preview_segments(profile)
        draw_dial(
            cr, width, height, segments,
            active_title=self._preview_title,
            title_text=self._preview_title or (profile.name if profile else None),
            mode=profile.mode if profile else "multi",
        )

    def _on_preview_clicked(self, _gesture, _count, x, y):
        profile = self._current_profile()
        segments = self._preview_segments(profile)
        if profile is None or not segments:
            return
        width = self._dial_preview.get_width()
        height = self._dial_preview.get_height()
        dx, dy = x - width / 2, y - height / 2
        scale = min(width, height) / 190
        distance = math.hypot(dx, dy)
        if profile.mode == "single":
            if distance <= 82 * scale:
                self._show_function_editor(profile, segments[0])
            return
        if not 49 * scale <= distance <= 82 * scale:
            return
        angle = (math.degrees(math.atan2(dy, dx)) + 90) % 360
        count = max(4, len(segments))
        index = min(int(angle // (360 / count)), count - 1)
        if index < len(segments):
            self._preview_title = segments[index].title
            self._dial_preview.queue_draw()
            self._show_function_editor(profile, segments[index])

    # --- function library -------------------------------------------------------

    def _show_function_library(self, profile):
        dialog = Adw.Dialog(title="Add a function", content_width=560, content_height=680)
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        view.add_top_bar(header)
        search = Gtk.SearchEntry()
        search.set_placeholder_text("Search functions")
        search.set_margin_start(12)
        search.set_margin_end(12)
        search.set_margin_bottom(6)
        view.add_top_bar(search)

        page = Adw.PreferencesPage()
        view.set_content(page)
        dialog.set_child(view)
        groups = []

        def add(segment):
            segment.title = self._unique_title(profile, segment.title)
            profile.segments.append(segment)
            self._preview_title = segment.title
            dialog.close()
            self._changed()
            self._toast(f"Added “{segment.title}”")

        def rebuild():
            for group in groups:
                page.remove(group)
            groups.clear()
            query = search.get_text().strip().lower()

            pack = pack_for_app(profile.app_id)
            if pack is not None and not query:
                group = Adw.PreferencesGroup(title="Pre-programmed")
                row = Adw.ActionRow(
                    title=f"All {pack.name} functions",
                    subtitle=", ".join(segment.title for segment in pack.factory()),
                )
                row.add_prefix(Gtk.Image.new_from_icon_name("starred-symbolic"))
                row.set_activatable(True)
                row.connect("activated", lambda _row: (dialog.close(), self._apply_pack(profile, pack)))
                group.add(row)
                page.add(group)
                groups.append(group)

            extras = []
            if profile.app_id == DARKTABLE_APP_ID:
                extras.append(("Darktable", "Colour labels", "tag-symbolic", "F1 / F2 / F3 colour labels", darktable_colour_labels_segment))
            entries = [
                (preset.category, preset.title, preset.icon_name, preset.description, preset.factory)
                for preset in FUNCTION_LIBRARY
            ] + extras
            categories = list(LIBRARY_CATEGORIES) + (["Darktable"] if extras else [])
            for category in categories:
                rows = [
                    entry for entry in entries
                    if entry[0] == category and (
                        not query or query in entry[1].lower() or query in entry[3].lower()
                    )
                ]
                if not rows:
                    continue
                group = Adw.PreferencesGroup(title=category)
                for _category, title, icon_name, description, factory in rows:
                    row = Adw.ActionRow(title=title, subtitle=description)
                    row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))
                    row.add_suffix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
                    row.set_activatable(True)
                    row.connect("activated", lambda _row, factory=factory: add(factory()))
                    group.add(row)
                page.add(group)
                groups.append(group)

            group = Adw.PreferencesGroup(title="Custom")
            row = Adw.ActionRow(title="Blank function", subtitle="Assign your own shortcuts, scroll or commands")
            row.add_prefix(Gtk.Image.new_from_icon_name("document-new-symbolic"))
            row.set_activatable(True)
            row.connect("activated", lambda _row: add(Segment(title="Custom")))
            group.add(row)
            page.add(group)
            groups.append(group)

        search.connect("search-changed", lambda _entry: rebuild())
        rebuild()
        dialog.present(self._window)

    # --- function editor ----------------------------------------------------------

    def _show_function_editor(self, profile, segment):
        dialog = Adw.Dialog(title=segment.title, content_width=600, content_height=720)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()
        view.set_content(page)
        dialog.set_child(view)
        state = {"groups": []}

        def changed(rebuild_lists=False):
            self._schedule_save()
            if rebuild_lists:
                build_triggers()

        general = Adw.PreferencesGroup(title="Function")
        name = Adw.EntryRow(title="Name")
        name.set_text(segment.title)

        def rename(entry):
            text = entry.get_text().strip()
            if not text or text == segment.title:
                return
            unique = self._unique_title(profile, text, ignore=segment)
            if profile.single_function == segment.title:
                profile.single_function = unique
            segment.title = unique
            dialog.set_title(unique)
            changed()

        name.connect("changed", rename)
        general.add(name)

        colour_row = Adw.ActionRow(title="Colour", subtitle="Identifies the function on the dial")
        colour_button = Gtk.ColorDialogButton.new(Gtk.ColorDialog(with_alpha=False))
        colour_button.set_valign(Gtk.Align.CENTER)
        rgba = Gdk.RGBA()
        position = profile.segments.index(segment) if segment in profile.segments else 0
        rgba.parse(segment_color(segment, position))
        colour_button.set_rgba(rgba)

        def colour_changed(button, _param):
            segment.color = _rgba_to_hex(button.get_rgba())
            changed()

        colour_button.connect("notify::rgba", colour_changed)
        colour_row.add_suffix(colour_button)
        general.add(colour_row)

        general.add(_spin_row(
            "Rotation step",
            f"Degrees per action; 0 uses the global default ({self.config.gesture.default_threshold}°)",
            segment.treshold or 0, 0, 360, 5, 0,
            lambda value: (setattr(segment, "treshold", int(value) or None), changed()),
        ))
        general.add(_switch_row(
            "Show on the dial", None, segment.enabled,
            lambda active: (setattr(segment, "enabled", active), changed()),
        ))
        page.add(general)

        value_group = Adw.PreferencesGroup(
            title="Live value",
            description="Optional shell command whose output is shown in the dial centre, e.g. the volume level.",
        )
        value_row = Adw.EntryRow(title="Value command")
        value_row.set_text(segment.value_command or "")
        value_row.connect("changed", lambda entry: (setattr(segment, "value_command", entry.get_text().strip() or None), changed()))
        value_group.add(value_row)
        unit_row = Adw.EntryRow(title="Unit (use % for a level gauge)")
        unit_row.set_text(segment.unit or "")
        unit_row.connect("changed", lambda entry: (setattr(segment, "unit", entry.get_text().strip() or None), changed()))
        value_group.add(unit_row)
        page.add(value_group)

        def build_triggers():
            for group in state["groups"]:
                page.remove(group)
            state["groups"] = []
            for field, label, icon_name, description in TRIGGERS:
                group = Adw.PreferencesGroup(title=label, description=description)
                add = _icon_button(
                    "list-add-symbolic", "Add action",
                    lambda field=field: self._show_step_dialog(
                        segment, field, None, lambda: changed(True)
                    ),
                )
                group.set_header_suffix(add)
                steps = getattr(segment, field)
                if not steps:
                    empty = Adw.ActionRow(title="No action")
                    empty.add_css_class("dim-label")
                    group.add(empty)
                for index, step in enumerate(steps):
                    group.add(self._step_row(segment, field, index, step, lambda: changed(True)))
                page.add(group)
                state["groups"].append(group)

        build_triggers()
        dialog.connect("closed", lambda _dialog: self._changed())
        dialog.present(self._window)

    def _step_row(self, segment, field, index, step, changed):
        steps = getattr(segment, field)
        row = Adw.ActionRow(title=GLib.markup_escape_text(describe_step(step)))
        row.set_subtitle(GLib.markup_escape_text(self._step_hint(step)))
        row.add_prefix(Gtk.Image.new_from_icon_name(self._icon_for_step(step)))
        row.set_activatable(True)
        row.connect("activated", lambda _row: self._show_step_dialog(segment, field, index, changed))

        def move(offset):
            target = index + offset
            if 0 <= target < len(steps):
                steps[index], steps[target] = steps[target], steps[index]
                changed()

        def remove():
            if 0 <= index < len(steps):
                del steps[index]
                changed()

        if len(steps) > 1:
            up = _icon_button("go-up-symbolic", "Run earlier", lambda: move(-1))
            up.set_sensitive(index > 0)
            row.add_suffix(up)
            down = _icon_button("go-down-symbolic", "Run later", lambda: move(1))
            down.set_sensitive(index < len(steps) - 1)
            row.add_suffix(down)
        row.add_suffix(_icon_button("user-trash-symbolic", "Remove action", remove, "error"))
        return row

    @staticmethod
    def _icon_for_step(step):
        icons = {
            StepType.KEYSTROKE: "input-keyboard-symbolic",
            StepType.SCROLL: "view-continuous-symbolic",
            StepType.MEDIA: "media-playback-start-symbolic",
            StepType.BRIGHTNESS: "display-brightness-symbolic",
            StepType.VOLUME: "audio-volume-high-symbolic",
            StepType.COMMAND: "utilities-terminal-symbolic",
            StepType.SHELL: "utilities-terminal-symbolic",
            StepType.DELAY: "alarm-symbolic",
        }
        return icons.get(step.type, "emblem-system-symbolic")

    @staticmethod
    def _step_hint(step):
        if step.type in (StepType.KEYSTROKE, StepType.MEDIA):
            return f"Shortcut: {format_keys(step.keys)}"
        if step.type is StepType.SCROLL:
            axis = "Horizontal" if step.axis == "horizontal" else "Vertical"
            held = f" with {format_keys(step.modifiers)} held" if step.modifiers else ""
            return f"{axis} scroll, {step.value or 120} units{held}"
        if step.type is StepType.VOLUME:
            return "System audio level"
        if step.type is StepType.BRIGHTNESS:
            return "Display brightness"
        if step.type is StepType.COMMAND:
            return " ".join([step.program or "", *(step.args or [])]).strip() or "Choose a program"
        if step.type is StepType.SHELL:
            return step.script or "Enter a command"
        if step.type is StepType.DELAY:
            return "Pause between steps"
        return step.type.value

    @staticmethod
    def _event_keys(keyval, state):
        """Translate a captured GTK shortcut into the evdev names the driver uses."""
        modifiers = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            modifiers.append("KEY_LEFTCTRL")
        if state & Gdk.ModifierType.SHIFT_MASK:
            modifiers.append("KEY_LEFTSHIFT")
        if state & Gdk.ModifierType.ALT_MASK:
            modifiers.append("KEY_LEFTALT")
        if state & Gdk.ModifierType.SUPER_MASK:
            modifiers.append("KEY_LEFTMETA")

        name = Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or ""
        special = {
            "Return": "KEY_ENTER",
            "KP_Enter": "KEY_ENTER",
            "Escape": "KEY_ESC",
            "BackSpace": "KEY_BACKSPACE",
            "Tab": "KEY_TAB",
            "ISO_Left_Tab": "KEY_TAB",
            "space": "KEY_SPACE",
            "Delete": "KEY_DELETE",
            "Insert": "KEY_INSERT",
            "Home": "KEY_HOME",
            "End": "KEY_END",
            "Page_Up": "KEY_PAGEUP",
            "Page_Down": "KEY_PAGEDOWN",
            "Left": "KEY_LEFT",
            "Right": "KEY_RIGHT",
            "Up": "KEY_UP",
            "Down": "KEY_DOWN",
            "bracketleft": "KEY_LEFTBRACE",
            "bracketright": "KEY_RIGHTBRACE",
            "braceleft": "KEY_LEFTBRACE",
            "braceright": "KEY_RIGHTBRACE",
            "minus": "KEY_MINUS",
            "underscore": "KEY_MINUS",
            "equal": "KEY_EQUAL",
            "plus": "KEY_EQUAL",
            "comma": "KEY_COMMA",
            "less": "KEY_COMMA",
            "period": "KEY_DOT",
            "greater": "KEY_DOT",
            "slash": "KEY_SLASH",
            "semicolon": "KEY_SEMICOLON",
            "apostrophe": "KEY_APOSTROPHE",
            "grave": "KEY_GRAVE",
            "backslash": "KEY_BACKSLASH",
            "KP_Add": "KEY_KPPLUS",
            "KP_Subtract": "KEY_KPMINUS",
            "XF86AudioMute": "KEY_MUTE",
            "XF86AudioPlay": "KEY_PLAYPAUSE",
            "XF86AudioNext": "KEY_NEXTSONG",
            "XF86AudioPrev": "KEY_PREVIOUSSONG",
            "XF86AudioRaiseVolume": "KEY_VOLUMEUP",
            "XF86AudioLowerVolume": "KEY_VOLUMEDOWN",
        }
        if len(name) == 1 and name.isalpha():
            key = f"KEY_{name.upper()}"
        elif len(name) == 1 and name.isdigit():
            key = f"KEY_{name}"
        elif name.startswith("F") and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
            key = f"KEY_{name}"
        else:
            key = special.get(name)
        if not key:
            return None
        return [*modifiers, key]

    def _show_step_dialog(self, segment, field, index, changed):
        steps = getattr(segment, field)
        original = steps[index] if index is not None and 0 <= index < len(steps) else None
        step = copy.deepcopy(original) if original else MacroStep(type=StepType.KEYSTROKE, keys=[])
        trigger = {"macro_cw": "turning clockwise", "macro_ccw": "turning counter-clockwise",
                   "macro_center": "tapping"}[field]

        dialog = Adw.Dialog(title="Edit action" if original else "New action", content_width=560, content_height=640)
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _button: dialog.close())
        header.pack_start(cancel)
        save = Gtk.Button(label="Save")
        save.add_css_class("suggested-action")
        header.pack_end(save)
        view.add_top_bar(header)
        page = Adw.PreferencesPage()
        view.set_content(page)
        dialog.set_child(view)

        basics = Adw.PreferencesGroup(
            title=f"{segment.title} — {trigger}",
            description="The label appears as a hint below the dial.",
        )
        shown_type = step.type
        # Older volume/brightness steps press a key combination (for example
        # Shift + Volume up for fine steps); edit them as shortcuts so the
        # combination survives saving.
        if step.type in (StepType.VOLUME, StepType.BRIGHTNESS) and step.keys and step.direction is None:
            shown_type = StepType.KEYSTROKE
        selected_type = next(
            (position for position, (_label, kind) in enumerate(ACTION_TYPES) if kind is shown_type), 0
        )
        type_row = Adw.ComboRow(title="Action", model=Gtk.StringList.new([label for label, _kind in ACTION_TYPES]))
        type_row.set_selected(selected_type)
        basics.add(type_row)
        label_row = Adw.EntryRow(title="Label (optional)")
        label_row.set_text(step.title or "")
        basics.add(label_row)
        page.add(basics)

        # Keyboard shortcut ---------------------------------------------------------
        key_state = {"keys": list(step.keys or [])}
        shortcut_group = Adw.PreferencesGroup(title="Shortcut", description="Click the field and press the shortcut, or toggle keys below.")
        capture = Gtk.Button()
        capture.add_css_class("proart-key-capture")
        capture.set_tooltip_text("Click here, then press the shortcut on your keyboard")
        shortcut_group.add(capture)
        key_names = Adw.EntryRow(title="Key names (advanced, e.g. KEY_LEFTCTRL KEY_F13)")
        shortcut_group.add(key_names)
        keyboard = Gtk.FlowBox()
        keyboard.set_selection_mode(Gtk.SelectionMode.NONE)
        keyboard.set_max_children_per_line(10)
        keyboard.set_homogeneous(True)
        keyboard.set_margin_top(8)
        key_buttons = []
        syncing = {"active": False}

        def refresh_shortcut(update_entry=True):
            syncing["active"] = True
            capture.set_label(format_keys(key_state["keys"]))
            for code, button in key_buttons:
                button.set_active(code in key_state["keys"])
            if update_entry:
                key_names.set_text(" ".join(key_state["keys"]))
            syncing["active"] = False

        controller = Gtk.EventControllerKey.new()

        def capture_key(_controller, keyval, _keycode, state):
            captured = self._event_keys(keyval, state)
            if captured:
                key_state["keys"] = captured
                refresh_shortcut()
            return True

        controller.connect("key-pressed", capture_key)
        capture.add_controller(controller)

        def names_changed(entry):
            if syncing["active"]:
                return
            key_state["keys"] = [
                name if name.startswith("KEY_") or name.isdigit() else f"KEY_{name.upper()}"
                for name in entry.get_text().split()
            ]
            refresh_shortcut(update_entry=False)

        key_names.connect("changed", names_changed)

        for label, code in (
            ("Ctrl", "KEY_LEFTCTRL"), ("Shift", "KEY_LEFTSHIFT"), ("Alt", "KEY_LEFTALT"),
            ("Super", "KEY_LEFTMETA"), ("[", "KEY_LEFTBRACE"), ("]", "KEY_RIGHTBRACE"),
            ("=", "KEY_EQUAL"), ("-", "KEY_MINUS"), ("Z", "KEY_Z"), ("Y", "KEY_Y"),
            ("←", "KEY_LEFT"), ("→", "KEY_RIGHT"), ("↑", "KEY_UP"), ("↓", "KEY_DOWN"),
            ("PgUp", "KEY_PAGEUP"), ("PgDn", "KEY_PAGEDOWN"), ("Space", "KEY_SPACE"),
            ("Enter", "KEY_ENTER"), ("Tab", "KEY_TAB"), ("Esc", "KEY_ESC"),
        ):
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("proart-key-choice")
            key_buttons.append((code, button))

            def toggle_key(widget, key=code):
                if syncing["active"]:
                    return
                keys = [entry for entry in key_state["keys"] if entry != key]
                if widget.get_active():
                    keys.append(key)
                key_state["keys"] = keys
                refresh_shortcut()

            button.connect("toggled", toggle_key)
            keyboard.append(button)
        shortcut_group.add(keyboard)
        page.add(shortcut_group)

        media_group = Adw.PreferencesGroup(title="Media keys")
        media_box = Gtk.FlowBox()
        media_box.set_selection_mode(Gtk.SelectionMode.NONE)
        media_box.set_max_children_per_line(4)
        for label, keys in (
            ("Mute", ["KEY_MUTE"]),
            ("Play / Pause", ["KEY_PLAYPAUSE"]),
            ("Next track", ["KEY_NEXTSONG"]),
            ("Previous track", ["KEY_PREVIOUSSONG"]),
            ("Stop", ["KEY_STOPCD"]),
            ("Mic mute", ["KEY_MICMUTE"]),
            ("Kbd light +", ["KEY_KBDILLUMUP"]),
            ("Kbd light −", ["KEY_KBDILLUMDOWN"]),
        ):
            button = Gtk.Button(label=label)
            button.connect(
                "clicked",
                lambda _button, shortcut=keys: (key_state.update(keys=list(shortcut)), refresh_shortcut()),
            )
            media_box.append(button)
        media_group.add(media_box)
        page.add(media_group)

        # Direction / amount ----------------------------------------------------------
        amount_group = Adw.PreferencesGroup(title="Direction")
        direction_row = Adw.ComboRow(title="Direction", model=Gtk.StringList.new(["Up / right", "Down / left"]))
        default_down = field == "macro_ccw"
        if step.direction is not None:
            default_down = step.direction in ("down", "counterclockwise", "left")
        direction_row.set_selected(1 if default_down else 0)
        amount_group.add(direction_row)
        amount_row = Adw.SpinRow.new_with_range(1, 2000, 1)
        amount_row.set_title("Amount")
        amount_row.set_value(step.value if isinstance(step.value, int) and step.value > 0 else 1)
        amount_group.add(amount_row)
        axis_row = Adw.ComboRow(title="Scroll axis", model=Gtk.StringList.new(["Vertical", "Horizontal"]))
        axis_row.set_selected(1 if step.axis == "horizontal" else 0)
        amount_group.add(axis_row)
        held_row = Adw.ActionRow(title="Hold while scrolling", subtitle="Ctrl turns scrolling into zoom in most apps")
        held_buttons = {}
        held_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        held_box.set_valign(Gtk.Align.CENTER)
        for label, code in (("Ctrl", "KEY_LEFTCTRL"), ("Shift", "KEY_LEFTSHIFT"), ("Alt", "KEY_LEFTALT")):
            button = Gtk.ToggleButton(label=label)
            button.set_active(code in (step.modifiers or []))
            held_buttons[code] = button
            held_box.append(button)
        held_row.add_suffix(held_box)
        amount_group.add(held_row)
        page.add(amount_group)

        command_group = Adw.PreferencesGroup(
            title="Command",
            description="Runs through the shell. Prefer a shortcut when one exists.",
        )
        command_row = Adw.EntryRow(title="Command")
        command_row.set_text(step.script or " ".join([step.program or "", *(step.args or [])]).strip())
        command_group.add(command_row)
        page.add(command_group)

        delay_group = Adw.PreferencesGroup(title="Wait")
        delay_row = Adw.SpinRow.new_with_range(0, 10, 0.05)
        delay_row.set_title("Seconds")
        delay_row.set_digits(2)
        delay_row.set_value(step.duration or 0.1)
        delay_group.add(delay_row)
        page.add(delay_group)

        def current_type():
            return ACTION_TYPES[type_row.get_selected()][1]

        def refresh_fields(*_args):
            action = current_type()
            shortcut_group.set_visible(action in (StepType.KEYSTROKE, StepType.MEDIA))
            media_group.set_visible(action is StepType.MEDIA)
            amount_group.set_visible(action in (StepType.VOLUME, StepType.BRIGHTNESS, StepType.SCROLL))
            amount_row.set_title("Scroll units (120 = one notch)" if action is StepType.SCROLL else "Repeat")
            axis_row.set_visible(action is StepType.SCROLL)
            held_row.set_visible(action is StepType.SCROLL)
            command_group.set_visible(action in (StepType.SHELL, StepType.COMMAND))
            delay_group.set_visible(action is StepType.DELAY)
            if action is StepType.SCROLL and amount_row.get_value() < 10:
                amount_row.set_value(120)

        type_row.connect("notify::selected", refresh_fields)
        refresh_shortcut()
        refresh_fields()

        def accept(_button):
            action = current_type()
            keys = [key for key in key_state["keys"] if key]
            if action in (StepType.KEYSTROKE, StepType.MEDIA) and not keys:
                self._toast("Press or choose a shortcut first")
                return
            if action in (StepType.SHELL, StepType.COMMAND) and not command_row.get_text().strip():
                self._toast("Enter a command first")
                return
            down = direction_row.get_selected() == 1
            result = MacroStep(type=StepType.SHELL if action is StepType.COMMAND else action)
            result.title = label_row.get_text().strip() or None
            if action in (StepType.KEYSTROKE, StepType.MEDIA):
                result.keys = keys
            elif action in (StepType.VOLUME, StepType.BRIGHTNESS):
                result.direction = "down" if down else "up"
                result.value = amount_row.get_value_as_int()
            elif action is StepType.SCROLL:
                result.direction = "counterclockwise" if down else "clockwise"
                result.value = amount_row.get_value_as_int()
                result.axis = "horizontal" if axis_row.get_selected() == 1 else None
                held = [code for code, button in held_buttons.items() if button.get_active()]
                result.modifiers = held or None
            elif action in (StepType.SHELL, StepType.COMMAND):
                result.script = command_row.get_text().strip()
            elif action is StepType.DELAY:
                result.duration = round(delay_row.get_value(), 2)
            if original is not None and original in steps:
                steps[steps.index(original)] = result
            else:
                steps.append(result)
            dialog.close()
            changed()

        save.connect("clicked", accept)
        dialog.present(self._window)

    # --- Behaviour ------------------------------------------------------------------

    def _build_behaviour_page(self):
        content = self._page_box()
        activation = Adw.PreferencesGroup(
            title="Activation",
            description="Hold the illuminated corner icon of the touchpad to switch the DialPad on or off.",
        )
        activation.add(_spin_row(
            "Hold time", "Seconds the corner icon must be held",
            self.config.activation.activation_time, 0.1, 5.0, 0.1, 1,
            lambda value: self._set_config("activation", "activation_time", round(value, 2)),
        ))
        coactivator = Adw.EntryRow(title="Co-activator keys (comma separated, e.g. Shift)")
        coactivator.set_text(", ".join(self.config.activation.coactivator_keys))
        coactivator.connect(
            "changed",
            lambda entry: self._set_config(
                "activation", "coactivator_keys",
                [key.strip() for key in entry.get_text().split(",") if key.strip()],
            ),
        )
        activation.add(coactivator)
        activation.add(_spin_row(
            "Switch off after inactivity", "Minutes without touch; 0 keeps the DialPad on",
            self.config.gesture.disable_inactivity_time / 60, 0, 120, 1, 0,
            lambda value: self._set_config("gesture", "disable_inactivity_time", int(value * 60)),
        ))
        content.append(activation)

        gesture = Adw.PreferencesGroup(
            title="Rotation",
            description="Global defaults; profiles can scale them with their own sensitivity.",
        )
        gesture.add(_spin_row(
            "Default rotation step", "Degrees of rotation per action",
            self.config.gesture.default_threshold, 5, 360, 5, 0,
            lambda value: self._set_config("gesture", "default_threshold", int(value)),
        ))
        gesture.add(_spin_row(
            "Jitter filter", "Ignore finger movements smaller than this many degrees",
            self.config.gesture.hysteresis, 0, 30, 1, 0,
            lambda value: self._set_config("gesture", "hysteresis", int(value)),
        ))
        gesture.add(_spin_row(
            "Centre hold for menu", "Seconds to hold the centre to return to the radial menu",
            self.config.gesture.center_hold_time, 0.2, 2.0, 0.05, 2,
            lambda value: self._set_config("gesture", "center_hold_time", round(value, 2)),
        ))
        gesture.add(_spin_row(
            "Minimum menu sectors", "Smaller menus are padded so sectors stay comfortable",
            self.config.gesture.slices_minimum_count, 1, 12, 1, 0,
            lambda value: self._set_config("gesture", "slices_minimum_count", int(value)),
        ))
        content.append(gesture)

        overlay = Adw.PreferencesGroup(
            title="On-screen dial",
            description="Applied by the GNOME Shell extension immediately.",
        )
        overlay.add(_spin_row(
            "Size", "Scale of the dial overlay",
            self.config.overlay.scale, 0.6, 1.6, 0.05, 2,
            lambda value: self._set_config("overlay", "scale", round(value, 2)),
        ))
        positions = list(OVERLAY_POSITIONS)
        overlay.add(_combo_row(
            "Position", None,
            [POSITION_LABELS[position] for position in positions],
            positions.index(self.config.overlay.position) if self.config.overlay.position in positions else 1,
            lambda index: self._set_config("overlay", "position", positions[index]),
        ))
        overlay.add(_spin_row(
            "Stay visible after release", "Milliseconds, so the final value can be read",
            self.config.overlay.hide_delay_ms, 0, 5000, 100, 0,
            lambda value: self._set_config("overlay", "hide_delay_ms", int(value)),
        ))
        overlay.add(_switch_row(
            "Show action hints", "Labels for both rotation directions and the tap action",
            self.config.overlay.show_hints,
            lambda active: self._set_config("overlay", "show_hints", active),
        ))
        overlay.add(_spin_row(
            "Progress arc from", "Show a progress arc while turning functions whose step is at least this many degrees",
            self.config.overlay.progress_above_degrees, 5, 360, 5, 0,
            lambda value: self._set_config("overlay", "progress_above_degrees", int(value)),
        ))
        overlay.add(_switch_row(
            "Show finger position", "A dot follows the finger around the ring",
            self.config.overlay.show_pointer,
            lambda active: self._set_config("overlay", "show_pointer", active),
        ))
        accent_row = Adw.ActionRow(title="Accent colour", subtitle="Used for functions without their own colour")
        accent = Gtk.ColorDialogButton.new(Gtk.ColorDialog(with_alpha=False))
        accent.set_valign(Gtk.Align.CENTER)
        rgba = Gdk.RGBA()
        rgba.parse(self.config.overlay.accent or DEFAULT_ACCENT)
        accent.set_rgba(rgba)
        accent.connect("notify::rgba", lambda button, _param: self._set_config("overlay", "accent", _rgba_to_hex(button.get_rgba())))
        accent_row.add_suffix(accent)
        overlay.add(accent_row)
        content.append(overlay)
        return self._scrolled_content(content)

    def _set_config(self, section, attribute, value):
        target = getattr(self.config, section)
        if getattr(target, attribute) != value:
            setattr(target, attribute, value)
            if section == "geometry" and self._calibration_preview is not None:
                self._calibration_preview.queue_draw()
            self._schedule_save()

    # --- Calibration ------------------------------------------------------------------

    def _build_calibration_page(self):
        content = self._page_box()

        guided = Adw.PreferencesGroup(
            title="Guided calibration",
            description=(
                "Measures the dial on any DialPad touchpad: trace the printed outer ring "
                "with one finger, lift it, then trace the edge of the centre button."
            ),
        )
        self._calibration_row = Adw.ActionRow(title="Ready", subtitle="The DialPad pauses while calibrating")
        self._calibration_row.add_prefix(Gtk.Image.new_from_icon_name("find-location-symbolic"))
        self._calibration_start = Gtk.Button(label="Start")
        self._calibration_start.add_css_class("suggested-action")
        self._calibration_start.set_valign(Gtk.Align.CENTER)
        self._calibration_start.connect("clicked", lambda _button: self._start_calibration())
        self._calibration_cancel = Gtk.Button(label="Cancel")
        self._calibration_cancel.set_valign(Gtk.Align.CENTER)
        self._calibration_cancel.set_visible(False)
        self._calibration_cancel.connect("clicked", lambda _button: self._call_driver("CancelCalibration"))
        self._calibration_row.add_suffix(self._calibration_cancel)
        self._calibration_row.add_suffix(self._calibration_start)
        guided.add(self._calibration_row)
        content.append(guided)

        connection = self._get_session_bus()
        if connection is not None:
            self._calibration_signal = connection.signal_subscribe(
                DBUS_NAME, DBUS_INTERFACE, "CalibrationProgress", DBUS_PATH, None,
                Gio.DBusSignalFlags.NONE, self._on_calibration_progress,
            )

        intro = Gtk.Label(
            label="Or match the virtual dial by hand. Changes apply live, so test with a finger while adjusting.",
            xalign=0, wrap=True,
        )
        intro.add_css_class("dim-label")
        content.append(intro)

        self._calibration_preview = Gtk.DrawingArea()
        self._calibration_preview.set_content_height(260)
        self._calibration_preview.set_hexpand(True)
        self._calibration_preview.add_css_class("proart-card")
        self._calibration_preview.set_draw_func(self._draw_calibration)
        content.append(self._calibration_preview)

        geometry = Adw.PreferencesGroup(title="Dial geometry", description="Touchpad units")
        for title, attribute in (
            ("Ring diameter", "circle_diameter"),
            ("Centre button diameter", "center_button_diameter"),
            ("Centre X", "center_x"),
            ("Centre Y", "center_y"),
        ):
            row = _spin_row(
                title, None, getattr(self.config.geometry, attribute), 0, 5000, 5, 0,
                lambda value, attribute=attribute: self._set_config("geometry", attribute, int(value)),
            )
            self._geometry_rows[attribute] = row
            geometry.add(row)
        content.append(geometry)

        icon = Adw.PreferencesGroup(title="Corner activation icon", description="Area in the top-right corner, touchpad units")
        icon.add(_spin_row("Width", None, self.config.geometry.width, 1, 2000, 5, 0,
                           lambda value: self._set_config("geometry", "width", int(value))))
        icon.add(_spin_row("Height", None, self.config.geometry.height, 1, 2000, 5, 0,
                           lambda value: self._set_config("geometry", "height", int(value))))
        content.append(icon)
        return self._scrolled_content(content)

    def _start_calibration(self):
        def started(connection, result):
            try:
                if connection is None:
                    raise RuntimeError
                accepted = connection.call_finish(result).unpack()[0]
            except (GLib.Error, RuntimeError):
                accepted = False
            if not accepted:
                self._calibration_row.set_title("Driver not reachable")
                self._calibration_row.set_subtitle("Calibration needs the running driver (D-Bus)")

        self._calibration_points = []
        self._call_driver("StartCalibration", callback=started)

    def _on_calibration_progress(self, _connection, _sender, _path, _interface, _signal, parameters):
        try:
            state = json.loads(parameters.unpack()[0])
        except (ValueError, TypeError, IndexError):
            return
        max_x, max_y = int(state.get("touchpad_max_x") or 0), int(state.get("touchpad_max_y") or 0)
        if max_x > 0 and max_y > 0:
            self._touchpad_size = (max_x, max_y)
        if state.get("point"):
            self._calibration_points.append(tuple(state["point"]))
            self._calibration_points = self._calibration_points[-400:]
        elif state.get("points") == 0:
            # A stroke was evaluated; the next one starts a fresh trace.
            self._calibration_points = []

        active = bool(state.get("active"))
        self._calibration_start.set_visible(not active)
        self._calibration_cancel.set_visible(active)
        step = f"Step {min(state.get('step_index', 0) + 1, state.get('steps', 2))} of {state.get('steps', 2)}"
        if active:
            self._calibration_row.set_title(f"{step}: {state.get('message', '')}")
            self._calibration_row.set_subtitle(state.get("error") or "Lift the finger when the circle is closed")
        elif state.get("done") and state.get("result"):
            self._apply_calibration(state["result"], state.get("layout") or "")
        else:
            self._calibration_row.set_title(state.get("error") or state.get("message") or "Calibration stopped")
            self._calibration_row.set_subtitle("Press Start to try again")
        if self._calibration_preview is not None:
            self._calibration_preview.queue_draw()

    def _apply_calibration(self, result, layout):
        geometry = self.config.geometry
        for attribute in ("circle_diameter", "center_button_diameter", "center_x", "center_y"):
            value = int(result[attribute])
            setattr(geometry, attribute, value)
            row = self._geometry_rows.get(attribute)
            if row is not None:
                row.set_value(value)
        if layout:
            self.config.device_name = layout
        self._calibration_points = []
        self._calibration_row.set_title("Calibrated")
        self._calibration_row.set_subtitle(
            f"Ring {result['circle_diameter']}, centre {result['center_button_diameter']} "
            f"at {result['center_x']} × {result['center_y']}"
        )
        self._schedule_save()
        self._toast("Dial geometry measured and saved")

    def _draw_calibration(self, _area, cr, width, height):
        max_x, max_y = self._touchpad_size
        margin = 14
        scale = min((width - 2 * margin) / max_x, (height - 2 * margin) / max_y)
        pad_w, pad_h = max_x * scale, max_y * scale
        left = (width - pad_w) / 2
        top = (height - pad_h) / 2
        geometry = self.config.geometry

        cr.save()
        radius = 14
        cr.new_sub_path()
        cr.arc(left + pad_w - radius, top + radius, radius, -math.pi / 2, 0)
        cr.arc(left + pad_w - radius, top + pad_h - radius, radius, 0, math.pi / 2)
        cr.arc(left + radius, top + pad_h - radius, radius, math.pi / 2, math.pi)
        cr.arc(left + radius, top + radius, radius, math.pi, 1.5 * math.pi)
        cr.close_path()
        cr.set_source_rgba(0.17, 0.175, 0.2, 1)
        cr.fill_preserve()
        cr.set_source_rgba(0.45, 0.42, 0.41, 1)
        cr.set_line_width(1)
        cr.stroke()

        cr.rectangle(left + pad_w - geometry.width * scale, top, geometry.width * scale, geometry.height * scale)
        cr.set_source_rgba(0.91, 0.73, 0.55, 0.35)
        cr.fill()

        cx = left + geometry.center_x * scale
        cy = top + geometry.center_y * scale
        cr.arc(cx, cy, geometry.circle_diameter / 2 * scale, 0, 2 * math.pi)
        cr.set_source_rgba(0.91, 0.73, 0.55, 0.18)
        cr.fill_preserve()
        cr.set_source_rgba(0.91, 0.73, 0.55, 0.9)
        cr.set_line_width(2)
        cr.stroke()
        cr.arc(cx, cy, geometry.center_button_diameter / 2 * scale, 0, 2 * math.pi)
        cr.set_source_rgba(0.97, 0.86, 0.75, 0.85)
        cr.set_line_width(1.5)
        cr.stroke()
        cr.move_to(cx - 6, cy)
        cr.line_to(cx + 6, cy)
        cr.move_to(cx, cy - 6)
        cr.line_to(cx, cy + 6)
        cr.stroke()

        if self._calibration_points:
            cr.set_source_rgba(0.42, 0.71, 1.0, 0.95)
            for point_x, point_y in self._calibration_points:
                cr.arc(left + point_x * scale, top + point_y * scale, 2, 0, 2 * math.pi)
                cr.fill()

        cr.set_font_size(10)
        cr.set_source_rgba(0.73, 0.70, 0.67, 1)
        cr.move_to(left + 8, top + pad_h - 8)
        cr.show_text(f"Touchpad {max_x} × {max_y}")
        cr.restore()

    # --- Driver -----------------------------------------------------------------------

    def _build_diagnostics_page(self):
        content = self._page_box()
        status = Adw.PreferencesGroup(title="Driver status")
        rows = {}
        for key, title in (
            ("service", "D-Bus service"),
            ("enabled", "DialPad"),
            ("application", "Focused application"),
            ("profile", "Active profile"),
            ("function", "Selected function"),
            ("environment", "Environment"),
        ):
            row = Adw.ActionRow(title=title, subtitle="Unknown")
            status.add(row)
            rows[key] = row
        self._diagnostics_rows = rows

        refresh = _icon_button("view-refresh-symbolic", "Refresh", self._refresh_diagnostics)
        status.set_header_suffix(refresh)
        content.append(status)

        tools = Adw.PreferencesGroup(title="Tools")
        reload_row = Adw.ActionRow(title="Reload configuration", subtitle="The driver normally reloads after every change")
        reload_button = Gtk.Button(label="Reload")
        reload_button.set_valign(Gtk.Align.CENTER)
        reload_button.connect("clicked", lambda _button: self._reload_driver())
        reload_row.add_suffix(reload_button)
        tools.add(reload_row)
        folder_row = Adw.ActionRow(title="Configuration file", subtitle=str(CONFIG_FILE))
        open_button = Gtk.Button(label="Open folder")
        open_button.set_valign(Gtk.Align.CENTER)
        open_button.connect(
            "clicked",
            lambda _button: Gtk.FileLauncher.new(Gio.File.new_for_path(str(CONFIG_DIR))).launch(self._window, None, None),
        )
        folder_row.add_suffix(open_button)
        tools.add(folder_row)
        content.append(tools)
        return self._scrolled_content(content)

    def _reload_driver(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
        save_config(self.config)

        def done(connection, result):
            try:
                connection.call_finish(result)
                self._toast("Driver reloaded the configuration")
            except (GLib.Error, AttributeError):
                self._toast("Driver is not reachable over D-Bus")

        self._call_driver("ReloadConfig", callback=done)

    @staticmethod
    def _unpack_dbus_value(value):
        return value.unpack() if isinstance(value, GLib.Variant) else value

    def _refresh_diagnostics(self):
        rows = self._diagnostics_rows
        if not rows:
            return
        rows["service"].set_subtitle("Checking…")
        self._call_driver("GetStatus", "(a{sv})", self._on_diagnostics_status)

    def _on_diagnostics_status(self, connection, result, *_user_data):
        rows = self._diagnostics_rows
        if not rows:
            return
        try:
            if connection is None:
                raise RuntimeError("session bus not found")
            response = connection.call_finish(result)
            unpacked = response.unpack()
            status = unpacked[0] if unpacked else {}
            status = {key: self._unpack_dbus_value(value) for key, value in status.items()}
        except (GLib.Error, RuntimeError) as error:
            rows["service"].set_subtitle(f"Unavailable: {getattr(error, 'message', error)}")
            for key in ("enabled", "application", "profile", "function", "environment"):
                rows[key].set_subtitle("Unknown")
            return

        rows["service"].set_subtitle("Connected")
        rows["enabled"].set_subtitle("On" if status.get("enabled") else "Off")
        rows["application"].set_subtitle(str(status.get("application") or "None"))
        mode = "single function" if status.get("mode") == "single" else "radial menu"
        rows["profile"].set_subtitle(f"{status.get('profile') or 'Legacy layout'} · {mode}")
        rows["function"].set_subtitle(
            str(status.get("selected_function") or ("Menu" if status.get("menu_active") else "—"))
        )
        rows["environment"].set_subtitle(
            f"{status.get('session_type') or 'unknown session'} · {status.get('layout') or 'unknown layout'}"
        )
        max_x, max_y = int(status.get("touchpad_max_x") or 0), int(status.get("touchpad_max_y") or 0)
        if max_x > 0 and max_y > 0:
            self._touchpad_size = (max_x, max_y)
            if self._calibration_preview is not None:
                self._calibration_preview.queue_draw()


def main():
    app = Application()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
