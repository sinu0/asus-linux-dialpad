import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Cairo from 'cairo';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

import {
    DEFAULT_SKIN,
    DIAL_D,
    HINT_H,
    iconLayout,
    iconNameFor,
    paintDial,
    parseColor,
    resolveSkin,
} from './dial.js';

const BUS_NAME = 'io.github.asuslinuxdrivers.DialPad';
const BUS_PATH = '/io/github/asuslinuxdrivers/DialPad';
const BUS_IFACE = BUS_NAME;
const CONFIG_DIR = GLib.build_filenamev([GLib.get_user_config_dir(), 'asus-dialpad']);
const CONFIG_NAME = 'config.json';
const SKINS_DIR = GLib.build_filenamev([CONFIG_DIR, 'skins']);
const SKINS_NAME = 'skins.json';
const FADE_IN_MS = 120;
const FADE_OUT_MS = 260;

const DEFAULT_APPEARANCE = {
    scale: 1.0,
    position: 'lower',
    hide_delay_ms: 1500,
    show_hints: true,
    show_pointer: true,
    accent: '#e7b98d',
    skin: DEFAULT_SKIN,
    skin_light: 'frost',
    follow_system_style: false,
};

export default class DialPadExtension extends Extension {
    enable() {
        this._signalId = 0;
        this._detailsSignalId = 0;
        this._focusHandlerId = 0;
        this._monitorsId = 0;
        this._configMonitors = [];
        this._configReloadId = 0;
        this._interfaceSettings = null;
        this._styleChangedId = 0;
        this._overlay = null;
        this._drawingArea = null;
        this._iconLayer = null;
        this._iconKey = '';
        this._hideTimeoutId = 0;
        this._shown = false;
        this._appearance = { ...DEFAULT_APPEARANCE };
        this._skin = resolveSkin(null, DEFAULT_SKIN);
        this._state = {
            enabled: false,
            title: '',
            titles: [],
            icons: [],
            menuTitles: [],
            menuIcons: [],
            value: 0,
            valueAngleStart: 0.0,
            unit: '',
            centerPressed: false,
            valueShowOnlyProgress: false,
            touching: false,
        };
        this._details = {
            profile: '',
            mode: 'multi',
            colors: [],
            color: '',
            hints: {},
            hold_returns: true,
            pointer: -1,
        };

        try {
            this._watchStyle();
            this._loadAppearance();
            this._watchConfig();
            this._connectDBus();
            this._connectFocus();
            this._createOverlay();
            this._fetchDetails();
        } catch (error) {
            log(`dialpad: unable to start overlay: ${error}`);
        }
    }

    disable() {
        this._cancelHide();
        try { this._unwatchConfig(); } catch (_) {}
        try { this._unwatchStyle(); } catch (_) {}
        try { this._disconnectFocus(); } catch (_) {}
        try { this._disconnectDBus(); } catch (_) {}
        try { this._destroyOverlay(); } catch (_) {}
    }

    // --- appearance from config.json -----------------------------------

    _loadAppearance() {
        const appearance = { ...DEFAULT_APPEARANCE };
        try {
            const file = Gio.File.new_for_path(GLib.build_filenamev([CONFIG_DIR, CONFIG_NAME]));
            const [ok, bytes] = file.load_contents(null);
            if (ok) {
                const overlay = JSON.parse(new TextDecoder().decode(bytes)).overlay || {};
                for (const key of Object.keys(DEFAULT_APPEARANCE)) {
                    if (overlay[key] !== undefined && overlay[key] !== null)
                        appearance[key] = overlay[key];
                }
            }
        } catch (_) {
            // A missing or half-written file keeps the defaults.
        }
        appearance.scale = Math.max(0.6, Math.min(1.6, Number(appearance.scale) || 1));
        appearance.hide_delay_ms = Math.max(0, Math.min(10000, Number(appearance.hide_delay_ms) || 0));
        this._appearance = appearance;
        this._accent = parseColor(appearance.accent, [0.906, 0.725, 0.553, 1]);
        this._applySkin();
    }

    _applySkin() {
        const appearance = this._appearance;
        const light = appearance.follow_system_style && !this._systemPrefersDark();
        const id = light ? appearance.skin_light : appearance.skin;
        this._skin = resolveSkin(this._loadSkins(), String(id || DEFAULT_SKIN));
    }

    _systemPrefersDark() {
        return this._interfaceSettings?.get_string('color-scheme') === 'prefer-dark';
    }

    // Follows the GNOME light/dark style switch for follow_system_style.
    _watchStyle() {
        try {
            this._interfaceSettings = new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' });
        } catch (_) {
            this._interfaceSettings = null;
            return;
        }
        this._styleChangedId = this._interfaceSettings.connect('changed::color-scheme', () => {
            if (!this._appearance.follow_system_style)
                return;
            this._applySkin();
            this._updateIcons();
            this._drawingArea?.queue_repaint();
        });
    }

    _unwatchStyle() {
        if (this._interfaceSettings && this._styleChangedId)
            this._interfaceSettings.disconnect(this._styleChangedId);
        this._interfaceSettings = null;
        this._styleChangedId = 0;
    }

    _readJson(path) {
        try {
            const [ok, bytes] = Gio.File.new_for_path(path).load_contents(null);
            return ok ? JSON.parse(new TextDecoder().decode(bytes)) : null;
        } catch (_) {
            return null;
        }
    }

    // Built-in skins ship as skins.json next to this file; every
    // skins/<id>.json in the config directory adds or replaces one.
    _loadSkins() {
        const skins = { ...this._readJson(GLib.build_filenamev([this.path, SKINS_NAME])) || {} };
        const directory = Gio.File.new_for_path(SKINS_DIR);
        let enumerator = null;
        try {
            enumerator = directory.enumerate_children('standard::name', Gio.FileQueryInfoFlags.NONE, null);
        } catch (_) {
            return skins;
        }
        for (let info = enumerator.next_file(null); info; info = enumerator.next_file(null)) {
            const name = info.get_name();
            if (!name.endsWith('.json'))
                continue;
            const skin = this._readJson(GLib.build_filenamev([SKINS_DIR, name]));
            if (skin && typeof skin === 'object')
                skins[name.slice(0, -5)] = skin;
        }
        enumerator.close(null);
        return skins;
    }

    _watchConfig() {
        // config.json and the skins directory; a skins directory created
        // later is picked up when it appears.
        this._configMonitors = [];
        this._watchDirectory(CONFIG_DIR, name => name === CONFIG_NAME || name === 'skins');
        this._watchDirectory(SKINS_DIR, name => name.endsWith('.json'));
    }

    _watchDirectory(path, relevant) {
        let monitor;
        try {
            monitor = Gio.File.new_for_path(path).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
        } catch (_) {
            return;
        }
        const id = monitor.connect('changed', (_monitor, file, other) => {
            const names = [file?.get_basename(), other?.get_basename()].filter(Boolean);
            if (names.some(relevant))
                this._scheduleConfigReload();
        });
        this._configMonitors.push([monitor, id]);
    }

    _scheduleConfigReload() {
        if (this._configReloadId)
            GLib.source_remove(this._configReloadId);
        this._configReloadId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 200, () => {
            this._configReloadId = 0;
            this._loadAppearance();
            this._applyGeometry();
            this._iconKey = '';
            this._updateIcons();
            this._drawingArea?.queue_repaint();
            return GLib.SOURCE_REMOVE;
        });
    }

    _unwatchConfig() {
        if (this._configReloadId) {
            GLib.source_remove(this._configReloadId);
            this._configReloadId = 0;
        }
        for (const [monitor, id] of this._configMonitors || []) {
            monitor.disconnect(id);
            monitor.cancel();
        }
        this._configMonitors = [];
    }

    // --- overlay actors -------------------------------------------------

    _createOverlay() {
        if (!Main.layoutManager?.uiGroup)
            return;

        this._overlay = new St.Widget({ visible: false, reactive: false, opacity: 0 });
        this._drawingArea = new St.DrawingArea();
        this._drawingArea.connect('repaint', this._onRepaint.bind(this));
        this._overlay.add_child(this._drawingArea);
        this._iconLayer = new St.Widget({ reactive: false });
        this._overlay.add_child(this._iconLayer);
        this._centerIcon = new St.Icon({ style_class: 'dialpad-center-icon', visible: false });
        this._overlay.add_child(this._centerIcon);
        Main.layoutManager.uiGroup.add_child(this._overlay);
        this._monitorsId = Main.layoutManager.connect('monitors-changed', () => this._applyGeometry());
        GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._applyGeometry();
            return GLib.SOURCE_REMOVE;
        });
    }

    _destroyOverlay() {
        if (this._monitorsId) {
            Main.layoutManager.disconnect(this._monitorsId);
            this._monitorsId = 0;
        }
        if (!this._overlay)
            return;
        if (this._overlay.get_parent())
            Main.layoutManager.uiGroup.remove_child(this._overlay);
        this._overlay.remove_all_transitions();
        this._overlay.destroy();
        this._overlay = null;
        this._drawingArea = null;
        this._iconLayer = null;
        this._centerIcon = null;
        this._iconKey = '';
        this._shown = false;
    }

    _applyGeometry() {
        if (!this._overlay || !this._drawingArea)
            return;
        const monitor = Main.layoutManager.primaryMonitor;
        if (!monitor)
            return;
        const scale = this._appearance.scale;
        const width = Math.round(DIAL_D * scale);
        const height = Math.round((DIAL_D + HINT_H) * scale);
        this._overlay.set_position(monitor.x, monitor.y);
        this._overlay.set_size(monitor.width, monitor.height);
        this._drawingArea.set_size(width, height);
        this._iconLayer.set_size(width, width);

        const x = Math.round((monitor.width - width) / 2);
        const centred = (monitor.height - width) / 2;
        const positions = {
            center: centred,
            // A slightly lower placement mirrors the unobtrusive Windows ASUS
            // Dial overlay without obscuring the focused application's toolbar.
            lower: centred + Math.min(84, monitor.height * 0.08),
            bottom: monitor.height - height - Math.round(monitor.height * 0.06),
            top: Math.round(monitor.height * 0.08),
        };
        const y = Math.round(positions[this._appearance.position] ?? positions.lower);
        this._drawingArea.set_position(x, y);
        this._iconLayer.set_position(x, y);
        this._dialOrigin = [x, y];
        this._updateIcons();
        this._drawingArea.queue_repaint();
    }

    // --- D-Bus ----------------------------------------------------------

    _connectDBus() {
        this._signalId = Gio.DBus.session.signal_subscribe(
            BUS_NAME, BUS_IFACE, 'OverlayState', BUS_PATH, null,
            Gio.DBusSignalFlags.NONE, this._onOverlayState.bind(this));
        this._detailsSignalId = Gio.DBus.session.signal_subscribe(
            BUS_NAME, BUS_IFACE, 'OverlayDetails', BUS_PATH, null,
            Gio.DBusSignalFlags.NONE, this._onOverlayDetails.bind(this));
    }

    _disconnectDBus() {
        for (const key of ['_signalId', '_detailsSignalId']) {
            if (this[key]) {
                Gio.DBus.session.signal_unsubscribe(this[key]);
                this[key] = 0;
            }
        }
    }

    _fetchDetails() {
        Gio.DBus.session.call(
            BUS_NAME, BUS_PATH, BUS_IFACE, 'GetOverlayDetails', null,
            new GLib.VariantType('(s)'), Gio.DBusCallFlags.NONE, 1000, null,
            (connection, result) => {
                try {
                    const [json] = connection.call_finish(result).deepUnpack();
                    this._mergeDetails(json);
                } catch (_) {
                    // Older drivers have no details; the dial still works.
                }
            });
    }

    _connectFocus() {
        if (!global.display)
            return;
        this._focusHandlerId = global.display.connect('notify::focus-window', this._onFocusWindow.bind(this));
    }

    _disconnectFocus() {
        if (this._focusHandlerId) {
            global.display.disconnect(this._focusHandlerId);
            this._focusHandlerId = 0;
        }
    }

    _mergeDetails(json) {
        try {
            const details = JSON.parse(json);
            if (details && typeof details === 'object')
                Object.assign(this._details, details);
        } catch (_) {}
    }

    _onOverlayDetails(_conn, _sender, _path, _iface, _signal, params) {
        const [json] = params.deepUnpack();
        this._mergeDetails(json);
        this._drawingArea?.queue_repaint();
    }

    _onOverlayState(_conn, _sender, _path, _iface, _signal, params) {
        const [enabled, title, titles, icons, value, valueAngleStart, unit, centerPressed, valueShowOnlyProgress, touching] = params.deepUnpack();
        // Drivers without the touching field keep the dial up while enabled.
        const legacyDriver = params.n_children() < 10;
        const wasEnabled = this._state.enabled;
        this._state.enabled = enabled;
        this._state.title = title || '';
        this._state.titles = titles || [];
        this._state.icons = icons || [];
        if (this._state.titles.some(label => Boolean(label))) {
            this._state.menuTitles = [...this._state.titles];
            this._state.menuIcons = [...this._state.icons];
        }
        this._state.value = value || 0;
        this._state.valueAngleStart = valueAngleStart || 0.0;
        this._state.unit = unit || '';
        this._state.centerPressed = centerPressed || false;
        this._state.valueShowOnlyProgress = valueShowOnlyProgress || false;
        this._state.touching = legacyDriver ? enabled : Boolean(touching);

        this._updateIcons();
        this._updateVisibility(wasEnabled);
        this._drawingArea?.queue_repaint();
    }

    _onFocusWindow() {
        const focusWindow = global.display?.focus_window;
        const tracker = Shell.WindowTracker?.get_default();
        const app = focusWindow && tracker ? tracker.get_window_app(focusWindow) : null;
        const appId = app?.get_id() || '';
        Gio.DBus.session.call(
            BUS_NAME, BUS_PATH, BUS_IFACE, 'SetActiveApplication',
            new GLib.Variant('(s)', [appId]), null,
            Gio.DBusCallFlags.NONE, -1, null, null);
    }

    // --- visibility -----------------------------------------------------

    _updateVisibility(wasEnabled) {
        if (!this._overlay)
            return;
        if (!this._state.enabled) {
            this._hide();
            return;
        }
        if (this._state.touching) {
            this._cancelHide();
            this._show();
            return;
        }
        // Not touching: flash the dial after activation, and let an
        // already visible dial linger so the final value can be read.
        if (!wasEnabled || this._shown) {
            this._show();
            this._scheduleHide();
        }
    }

    _show() {
        if (this._shown)
            return;
        this._shown = true;
        this._overlay.remove_all_transitions();
        this._overlay.visible = true;
        this._overlay.ease({
            opacity: 255,
            duration: FADE_IN_MS,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });
    }

    _hide() {
        this._cancelHide();
        if (!this._shown || !this._overlay)
            return;
        this._shown = false;
        this._overlay.remove_all_transitions();
        this._overlay.ease({
            opacity: 0,
            duration: FADE_OUT_MS,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
            onComplete: () => {
                if (this._overlay && !this._shown)
                    this._overlay.visible = false;
            },
        });
    }

    _scheduleHide() {
        this._cancelHide();
        this._hideTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, this._appearance.hide_delay_ms, () => {
            this._hideTimeoutId = 0;
            this._hide();
            return GLib.SOURCE_REMOVE;
        });
    }

    _cancelHide() {
        if (this._hideTimeoutId) {
            GLib.source_remove(this._hideTimeoutId);
            this._hideTimeoutId = 0;
        }
    }

    // --- icons ----------------------------------------------------------

    _view() {
        return {
            state: this._state,
            details: this._details,
            appearance: this._appearance,
            accent: this._accent,
            skin: this._skin,
        };
    }

    _gicon(title, configured) {
        // A configured icon wins when it exists: an absolute file path or an
        // icon name from the theme.
        if (configured) {
            if (configured.startsWith('/')) {
                if (GLib.file_test(configured, GLib.FileTest.EXISTS))
                    return Gio.FileIcon.new(Gio.File.new_for_path(configured));
            } else {
                return Gio.ThemedIcon.new(configured);
            }
        }
        return Gio.ThemedIcon.new(iconNameFor(title));
    }

    _cssColor(color) {
        const [r, g, b] = color.map(channel => Math.round(channel * 255));
        return `color: rgba(${r}, ${g}, ${b}, ${color[3] ?? 1});`;
    }

    _updateIcons() {
        if (!this._iconLayer)
            return;
        const { menu, menuVisible, center } = iconLayout(this._view());
        const key = JSON.stringify(menu.map(({ title, configured, x, y, size }) => [title, configured, x, y, size]));

        if (key !== this._iconKey) {
            this._iconKey = key;
            this._iconLayer.destroy_all_children();
            for (const entry of menu) {
                const icon = new St.Icon({
                    gicon: this._gicon(entry.title, entry.configured),
                    icon_size: entry.size,
                    style_class: 'dialpad-segment-icon',
                });
                icon.set_position(entry.x, entry.y);
                this._iconLayer.add_child(icon);
            }
        }

        this._iconLayer.visible = menuVisible;
        const icons = this._iconLayer.get_children();
        menu.forEach((entry, index) => icons[index]?.set_style(this._cssColor(entry.color)));
        this._updateCenterIcon(center);
    }

    _updateCenterIcon(center) {
        const icon = this._centerIcon;
        if (!icon)
            return;
        icon.visible = Boolean(center);
        if (!center || !this._dialOrigin)
            return;
        const [x, y] = this._dialOrigin;
        icon.gicon = this._gicon(center.title, center.configured);
        icon.icon_size = center.size;
        icon.set_style(this._cssColor(center.color));
        icon.set_position(x + center.x, y + center.y);
    }

    // --- painting -------------------------------------------------------

    _onRepaint(area) {
        const cr = area.get_context();
        cr.save();
        cr.setOperator(Cairo.Operator.CLEAR);
        cr.paint();
        cr.restore();
        if (this._state.enabled)
            paintDial(cr, this._view());
        // GJS does not free Cairo contexts promptly without this.
        cr.$dispose();
    }
}
