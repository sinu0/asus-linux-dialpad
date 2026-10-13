import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Cairo from 'cairo';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';

const BUS_NAME = 'io.github.asuslinuxdrivers.DialPad';
const BUS_PATH = '/io/github/asuslinuxdrivers/DialPad';
const BUS_IFACE = BUS_NAME;
const CONFIG_DIR = GLib.build_filenamev([GLib.get_user_config_dir(), 'asus-dialpad']);
const CONFIG_NAME = 'config.json';

// A dark glass dial in the spirit of the ASUS Dial overlay: one calm
// surface, functions as icon bubbles and colour only where it carries
// meaning (the highlighted function, its level and the finger).
const PALETTE = {
    surfaceTop: [0.17, 0.175, 0.205, 0.97],
    surfaceBottom: [0.085, 0.09, 0.105, 0.97],
    rim: [1, 1, 1, 0.09],
    bubble: [1, 1, 1, 0.07],
    track: [1, 1, 1, 0.08],
    centerTop: [0.205, 0.21, 0.245, 1],
    centerBottom: [0.125, 0.13, 0.15, 1],
    text: [0.96, 0.95, 0.93, 1],
    muted: [0.70, 0.69, 0.67, 1],
    icon: [0.86, 0.85, 0.83, 1],
    iconOnColor: [0.08, 0.08, 0.09, 1],
    champagne: [0.96, 0.82, 0.67, 1],
};

// Logical geometry; everything is multiplied by the configured scale.
const DIAL_D = 360;
const DIAL_R = DIAL_D / 2;
const HINT_H = 46;
// Room around the disc for its symmetric shadow.
const OUTER_R = 162;
const ICON_R = 113;
const BUBBLE_R = 27;
const HIGHLIGHT_R = 152;
const GAUGE_R = 136;
const GAUGE_W = 11;
const CENTER_R = 70;
const ICON_SIZE = 20;
const CENTER_ICON_SIZE = 26;
// Level gauges open at the bottom like a knob scale.
const GAUGE_START = 0.75 * Math.PI;
const GAUGE_SWEEP = 1.5 * Math.PI;
const FONT = 'Adwaita Sans';

// Function names map to GNOME (Adwaita) symbolic icons, the same set the
// settings app uses. First match wins, so specific words come first.
const ICON_RULES = [
    [['record'], 'media-record'],
    [['stream'], 'network-transmit'],
    [['pause'], 'media-playback-pause'],
    [['mic'], 'audio-input-microphone'],
    [['replay', 'save'], 'document-save'],
    [['point', 'cut', 'split', 'clip', 'snap'], 'edit-cut'],
    [['layer'], 'view-list'],
    [['keyframe'], 'starred'],
    [['arrange', 'order'], 'view-sort-ascending'],
    [['cursor'], 'go-next'],
    [['mirror'], 'object-flip-horizontal'],
    [['mute'], 'audio-volume-muted'],
    [['volume', 'audio', 'sound'], 'audio-volume-high'],
    [['keyboard'], 'keyboard-brightness'],
    [['bright', 'exposure', 'light'], 'display-brightness'],
    [['horizontal'], 'object-flip-horizontal'],
    [['scroll'], 'object-flip-vertical'],
    [['timeline'], 'zoom-fit-best'],
    [['zoom'], 'system-search'],
    [['undo', 'history', 'edit'], 'edit-undo'],
    [['redo'], 'edit-redo'],
    [['seek', 'shuttle'], 'media-seek-forward'],
    [['frame'], 'media-skip-forward'],
    [['media', 'track', 'play', 'music'], 'media-playback-start'],
    [['workspace'], 'view-grid'],
    [['tab'], 'view-paged'],
    [['back', 'forward', 'arrow'], 'go-next'],
    [['brush', 'opacity', 'paint', 'draw'], 'document-edit'],
    [['rotate'], 'object-rotate-right'],
    [['scale'], 'zoom-fit-best'],
    [['photo', 'image'], 'image-x-generic'],
    [['rating', 'star'], 'starred'],
    [['label', 'colour', 'color'], 'color-select'],
    [['font', 'text'], 'font-x-generic'],
    [['notif'], 'preferences-system-notifications'],
];
const FADE_IN_MS = 120;
const FADE_OUT_MS = 260;

const DEFAULT_APPEARANCE = {
    scale: 1.0,
    position: 'lower',
    hide_delay_ms: 1500,
    show_hints: true,
    show_pointer: true,
    accent: '#e7b98d',
};

function parseColor(text, fallback) {
    const match = /^#?([0-9a-f]{6})$/i.exec(String(text || '').trim());
    if (!match)
        return fallback;
    const value = parseInt(match[1], 16);
    return [(value >> 16 & 255) / 255, (value >> 8 & 255) / 255, (value & 255) / 255, 1];
}

function truncate(text, length) {
    text = String(text || '');
    return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function mix(color, other, amount) {
    return color.map((channel, index) => channel * (1 - amount) + other[index] * amount);
}

export default class DialPadExtension extends Extension {
    enable() {
        this._signalId = 0;
        this._detailsSignalId = 0;
        this._focusHandlerId = 0;
        this._monitorsId = 0;
        this._configMonitor = null;
        this._configMonitorId = 0;
        this._configReloadId = 0;
        this._overlay = null;
        this._drawingArea = null;
        this._iconLayer = null;
        this._iconKey = '';
        this._hideTimeoutId = 0;
        this._shown = false;
        this._appearance = { ...DEFAULT_APPEARANCE };
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
    }

    _watchConfig() {
        const directory = Gio.File.new_for_path(CONFIG_DIR);
        try {
            this._configMonitor = directory.monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, null);
        } catch (_) {
            return;
        }
        this._configMonitorId = this._configMonitor.connect('changed', (_monitor, file, other) => {
            const names = [file?.get_basename(), other?.get_basename()];
            if (!names.includes(CONFIG_NAME))
                return;
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
        });
    }

    _unwatchConfig() {
        if (this._configReloadId) {
            GLib.source_remove(this._configReloadId);
            this._configReloadId = 0;
        }
        if (this._configMonitor) {
            if (this._configMonitorId)
                this._configMonitor.disconnect(this._configMonitorId);
            this._configMonitor.cancel();
            this._configMonitor = null;
            this._configMonitorId = 0;
        }
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

    // --- state helpers --------------------------------------------------

    _segmentState() {
        const menu = this._state.titles.some(label => Boolean(label));
        const titles = menu ? this._state.titles : this._state.menuTitles;
        const icons = menu ? this._state.icons : this._state.menuIcons;
        return { titles, icons, count: Math.max(titles.length, 4) };
    }

    _isSelectedMode() {
        return Boolean(this._state.title) && this._state.title !== 'Menu' && !this._state.titles.some(label => Boolean(label));
    }

    _segmentColor(index) {
        return parseColor(this._details.colors?.[index], this._accent);
    }

    _functionColor() {
        return parseColor(this._details.color, this._accent);
    }

    _numericValue() {
        const number = Number(this._state.value);
        return Number.isFinite(number) ? number : null;
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
        const name = (title || '').toLowerCase();
        for (const [words, icon] of ICON_RULES) {
            if (words.some(word => name.includes(word)))
                return Gio.ThemedIcon.new(`${icon}-symbolic`);
        }
        return Gio.ThemedIcon.new('input-dialpad-symbolic');
    }

    _cssColor(color, alpha = 1) {
        const [r, g, b] = color.map(channel => Math.round(channel * 255));
        return `color: rgba(${r}, ${g}, ${b}, ${alpha});`;
    }

    _updateIcons() {
        if (!this._iconLayer)
            return;
        const { titles, icons, count } = this._segmentState();
        const activeTitle = this._state.title === 'Menu' ? '' : this._state.title;
        const scale = this._appearance.scale;
        const key = JSON.stringify([titles, icons, count, scale]);

        if (key !== this._iconKey) {
            this._iconKey = key;
            this._iconLayer.destroy_all_children();
            const slice = (2 * Math.PI) / count;
            const size = Math.round(ICON_SIZE * scale);
            for (let index = 0; index < count; index++) {
                if (!titles[index])
                    continue;
                const angle = (index + 0.5) * slice - Math.PI / 2;
                const icon = new St.Icon({
                    gicon: this._gicon(titles[index], icons[index] || ''),
                    icon_size: size,
                    style_class: 'dialpad-segment-icon',
                });
                icon.set_position(
                    Math.round((DIAL_R + Math.cos(angle) * ICON_R) * scale - size / 2),
                    Math.round((DIAL_R + Math.sin(angle) * ICON_R) * scale - size / 2));
                icon._dialpadTitle = titles[index];
                this._iconLayer.add_child(icon);
            }
        }

        // Icons belong to the menu ring only; a selected function shows its
        // value gauge in the same place.
        this._iconLayer.visible = !this._isSelectedMode();
        for (const icon of this._iconLayer.get_children()) {
            const active = icon._dialpadTitle === activeTitle;
            icon.set_style(this._cssColor(active ? PALETTE.iconOnColor : PALETTE.icon, active ? 1 : 0.85));
        }
        this._updateCenterIcon();
    }

    _updateCenterIcon() {
        const icon = this._centerIcon;
        if (!icon)
            return;
        const title = this._state.title;
        const selected = this._isSelectedMode();
        const hovered = Boolean(title) && title !== 'Menu' && !selected;
        icon.visible = selected || hovered;
        if (!icon.visible || !this._dialOrigin)
            return;

        const { titles, icons } = this._segmentState();
        const index = titles.indexOf(title);
        const scale = this._appearance.scale;
        const size = Math.round(CENTER_ICON_SIZE * scale);
        icon.gicon = this._gicon(title, index >= 0 ? icons[index] || '' : '');
        icon.icon_size = size;
        icon.set_style(this._cssColor(selected ? this._functionColor() : this._activeColor()));
        const [x, y] = this._dialOrigin;
        const offset = selected ? 34 : 26;
        icon.set_position(
            Math.round(x + DIAL_R * scale - size / 2),
            Math.round(y + (DIAL_R - offset) * scale - size / 2));
    }

    _activeColor() {
        const { titles } = this._segmentState();
        const index = titles.indexOf(this._state.title);
        return index >= 0 ? this._segmentColor(index) : this._accent;
    }

    // --- painting -------------------------------------------------------

    _onRepaint(area) {
        const cr = area.get_context();
        cr.save();
        cr.setOperator(Cairo.Operator.CLEAR);
        cr.paint();
        cr.restore();
        if (this._state.enabled) {
            cr.save();
            cr.scale(this._appearance.scale, this._appearance.scale);
            this._drawSurface(cr, DIAL_R, DIAL_R);
            if (this._isSelectedMode()) {
                this._drawGauge(cr, DIAL_R, DIAL_R);
            } else {
                this._drawMenu(cr, DIAL_R, DIAL_R);
            }
            this._drawCenter(cr, DIAL_R, DIAL_R);
            this._drawHints(cr, DIAL_R, DIAL_D + HINT_H / 2);
            cr.restore();
        }
        // GJS does not free Cairo contexts promptly without this.
        cr.$dispose();
    }

    _drawSurface(cr, cx, cy) {
        cr.save();
        // Soft shadow centred under the disc, slightly lower like a light
        // from above; concentric so the dial never looks off-centre.
        const shadow = new Cairo.RadialGradient(cx, cy + 4, OUTER_R - 6, cx, cy + 4, OUTER_R + 16);
        shadow.addColorStopRGBA(0, 0, 0, 0, 0.45);
        shadow.addColorStopRGBA(1, 0, 0, 0, 0);
        cr.arc(cx, cy + 4, OUTER_R + 16, 0, 2 * Math.PI);
        cr.setSource(shadow);
        cr.fill();

        const surface = new Cairo.LinearGradient(cx, cy - OUTER_R, cx, cy + OUTER_R);
        surface.addColorStopRGBA(0, ...PALETTE.surfaceTop);
        surface.addColorStopRGBA(1, ...PALETTE.surfaceBottom);
        cr.arc(cx, cy, OUTER_R, 0, 2 * Math.PI);
        cr.setSource(surface);
        cr.fill();

        cr.arc(cx, cy, OUTER_R - 0.5, 0, 2 * Math.PI);
        cr.setLineWidth(1);
        cr.setSourceRGBA(...PALETTE.rim);
        cr.stroke();
        cr.restore();
    }

    _drawMenu(cr, cx, cy) {
        const { titles, count } = this._segmentState();
        const slice = (2 * Math.PI) / count;
        const activeTitle = this._state.title === 'Menu' ? '' : this._state.title;
        cr.save();
        cr.setLineCap(Cairo.LineCap.ROUND);

        for (let index = 0; index < count; index++) {
            const label = titles[index] || '';
            const mid = (index + 0.5) * slice - Math.PI / 2;
            const x = cx + Math.cos(mid) * ICON_R;
            const y = cy + Math.sin(mid) * ICON_R;

            if (!label) {
                // A free slot is a quiet dot, not a dark hole in the ring.
                cr.arc(x, y, 3, 0, 2 * Math.PI);
                cr.setSourceRGBA(1, 1, 1, 0.14);
                cr.fill();
                continue;
            }

            const color = this._segmentColor(index);
            const active = label === activeTitle;
            if (active) {
                // Glow of the chosen slice and an arc on the rim.
                const start = index * slice - Math.PI / 2 + 0.06;
                const end = (index + 1) * slice - Math.PI / 2 - 0.06;
                cr.moveTo(cx + Math.cos(start) * (CENTER_R + 8), cy + Math.sin(start) * (CENTER_R + 8));
                cr.arc(cx, cy, OUTER_R - 3, start, end);
                cr.arcNegative(cx, cy, CENTER_R + 8, end, start);
                cr.closePath();
                cr.setSourceRGBA(color[0], color[1], color[2], 0.07);
                cr.fill();

                cr.setLineWidth(4);
                cr.setSourceRGBA(...color);
                cr.arc(cx, cy, HIGHLIGHT_R, start + 0.04, end - 0.04);
                cr.stroke();
            }

            cr.arc(x, y, BUBBLE_R, 0, 2 * Math.PI);
            if (active) {
                cr.setSourceRGBA(...color);
                cr.fill();
            } else {
                cr.setSourceRGBA(...PALETTE.bubble);
                cr.fill();
                // A small colour key keeps functions recognisable.
                cr.arc(x, y, BUBBLE_R - 0.75, mid + Math.PI - 0.55, mid + Math.PI + 0.55);
                cr.setLineWidth(1.5);
                cr.setSourceRGBA(color[0], color[1], color[2], 0.75);
                cr.stroke();
            }
        }
        cr.restore();
        this._drawPointer(cr, cx, cy, HIGHLIGHT_R, PALETTE.text);
    }

    _drawGauge(cr, cx, cy) {
        const color = this._functionColor();
        const value = this._numericValue();
        const level = !this._state.valueShowOnlyProgress && this._state.unit === '%' && value !== null;
        cr.save();
        cr.setLineCap(Cairo.LineCap.ROUND);
        cr.setLineWidth(GAUGE_W);

        if (level) {
            // Level functions (volume, brightness…) get a knob-style scale.
            cr.setSourceRGBA(...PALETTE.track);
            cr.arc(cx, cy, GAUGE_R, GAUGE_START, GAUGE_START + GAUGE_SWEEP);
            cr.stroke();
            const fraction = Math.max(0, Math.min(1, value / 100));
            if (fraction > 0.005) {
                cr.setSourceRGBA(...color);
                cr.arc(cx, cy, GAUGE_R, GAUGE_START, GAUGE_START + fraction * GAUGE_SWEEP);
                cr.stroke();
            }
        } else {
            // Endless functions show detents, like the notches of a wheel.
            cr.setSourceRGBA(...PALETTE.track);
            cr.arc(cx, cy, GAUGE_R, 0, 2 * Math.PI);
            cr.stroke();
            cr.setLineWidth(2);
            for (let index = 0; index < 24; index++) {
                const angle = index / 24 * 2 * Math.PI;
                cr.moveTo(cx + Math.cos(angle) * (GAUGE_R - 3), cy + Math.sin(angle) * (GAUGE_R - 3));
                cr.lineTo(cx + Math.cos(angle) * (GAUGE_R + 3), cy + Math.sin(angle) * (GAUGE_R + 3));
            }
            cr.setSourceRGBA(1, 1, 1, 0.16);
            cr.stroke();
        }

        if (this._state.valueShowOnlyProgress) {
            // Progress towards the next step of slow functions (Undo…).
            const fraction = Math.max(-1, Math.min(1, this._state.value / 100));
            if (Math.abs(fraction) >= 0.01) {
                const start = this._state.valueAngleStart * Math.PI / 180 - Math.PI / 2;
                cr.setLineWidth(GAUGE_W);
                cr.setSourceRGBA(...color);
                if (fraction > 0)
                    cr.arc(cx, cy, GAUGE_R, start, start + fraction * 2 * Math.PI);
                else
                    cr.arcNegative(cx, cy, GAUGE_R, start, start + fraction * 2 * Math.PI);
                cr.stroke();
            }
        }
        cr.restore();
        this._drawPointer(cr, cx, cy, GAUGE_R, color);
    }

    _drawPointer(cr, cx, cy, radius, color) {
        const pointer = Number(this._details.pointer);
        if (!this._appearance.show_pointer || !this._state.touching || !(pointer >= 0))
            return;
        const angle = pointer * Math.PI / 180 - Math.PI / 2;
        const x = cx + Math.cos(angle) * radius;
        const y = cy + Math.sin(angle) * radius;
        cr.save();
        const glow = new Cairo.RadialGradient(x, y, 2, x, y, 15);
        glow.addColorStopRGBA(0, color[0], color[1], color[2], 0.55);
        glow.addColorStopRGBA(1, color[0], color[1], color[2], 0);
        cr.arc(x, y, 15, 0, 2 * Math.PI);
        cr.setSource(glow);
        cr.fill();
        cr.arc(x, y, 5.5, 0, 2 * Math.PI);
        cr.setSourceRGBA(1, 1, 1, 0.95);
        cr.fill();
        cr.restore();
    }

    _drawCenter(cr, cx, cy) {
        const selectedMode = this._isSelectedMode();
        const accent = selectedMode ? this._functionColor() : this._accent;
        cr.save();
        const halo = new Cairo.RadialGradient(cx, cy + 2, CENTER_R - 4, cx, cy + 2, CENTER_R + 10);
        halo.addColorStopRGBA(0, 0, 0, 0, 0.35);
        halo.addColorStopRGBA(1, 0, 0, 0, 0);
        cr.arc(cx, cy + 2, CENTER_R + 10, 0, 2 * Math.PI);
        cr.setSource(halo);
        cr.fill();

        const surface = new Cairo.LinearGradient(cx, cy - CENTER_R, cx, cy + CENTER_R);
        surface.addColorStopRGBA(0, ...PALETTE.centerTop);
        surface.addColorStopRGBA(1, ...PALETTE.centerBottom);
        cr.arc(cx, cy, CENTER_R, 0, 2 * Math.PI);
        cr.setSource(surface);
        cr.fill();

        cr.arc(cx, cy, CENTER_R - 0.5, 0, 2 * Math.PI);
        cr.setLineWidth(this._state.centerPressed ? 2.5 : 1);
        cr.setSourceRGBA(...(this._state.centerPressed ? accent : PALETTE.rim));
        cr.stroke();

        const title = this._state.title;
        const profile = (this._details.profile || '').toUpperCase();
        if (selectedMode) {
            const value = !this._state.valueShowOnlyProgress && this._state.unit
                ? `${this._state.value}${this._state.unit}`
                : '';
            this._drawCenteredText(cr, truncate(title, 14), cx, cy + 2, title.length > 10 ? 13 : 16, PALETTE.text, true);
            if (value)
                this._drawCenteredText(cr, value, cx, cy + 27, 18, accent, true);
            else if (profile)
                this._drawCenteredText(cr, truncate(profile, 16), cx, cy + 26, 8.5, PALETTE.muted, false);
        } else if (title && title !== 'Menu') {
            this._drawCenteredText(cr, truncate(title, 14), cx, cy + 10, title.length > 10 ? 13 : 16, PALETTE.text, true);
            this._drawCenteredText(cr, 'Release to select', cx, cy + 32, 8.5, PALETTE.muted, false);
        } else {
            this._drawCenteredText(cr, truncate(profile || 'DIAL', 14), cx, cy - 8, profile.length > 10 ? 11 : 13, PALETTE.text, true);
            this._drawCenteredText(cr, 'Choose a function', cx, cy + 14, 9, PALETTE.muted, false);
        }
        cr.restore();
    }

    _drawHints(cr, cx, cy) {
        if (!this._appearance.show_hints || !this._isSelectedMode())
            return;
        const hints = this._details.hints || {};
        const multi = this._details.mode !== 'single';
        const ccw = truncate(hints.ccw, 20);
        const cw = truncate(hints.cw, 20);
        let center = '';
        if (hints.center) {
            const action = truncate(hints.center, 26);
            center = multi ? `Tap: ${action}  ·  Hold: menu` : `Tap: ${action}`;
        }
        else if (multi)
            center = 'Tap centre: menu';
        if (!ccw && !cw && !center)
            return;

        const width = 300;
        const height = center ? 40 : 24;
        const top = cy - HINT_H / 2 + 2;
        cr.save();
        this._roundedRect(cr, cx - width / 2, top, width, height, 12);
        cr.setSourceRGBA(...PALETTE.surfaceBottom);
        cr.fillPreserve();
        cr.setLineWidth(1);
        cr.setSourceRGBA(...PALETTE.rim);
        cr.stroke();
        const arrowColor = this._functionColor();
        if (ccw) {
            this._drawTurnArrow(cr, cx - width / 2 + 18, top + 12, false, arrowColor);
            this._drawAlignedText(cr, ccw, cx - width / 2 + 30, top + 12, 11, PALETTE.text, 'left');
        }
        if (cw) {
            this._drawTurnArrow(cr, cx + width / 2 - 18, top + 12, true, arrowColor);
            this._drawAlignedText(cr, cw, cx + width / 2 - 30, top + 12, 11, PALETTE.text, 'right');
        }
        if (center)
            this._drawCenteredText(cr, center, cx, top + 29, 9, PALETTE.muted, false);
        cr.restore();
    }

    _drawTurnArrow(cr, x, y, clockwise, color) {
        // Drawn instead of ↺/↻, which the Cairo toy font cannot render.
        const radius = 5.5;
        const start = clockwise ? -Math.PI * 0.85 : -Math.PI * 0.15;
        const end = clockwise ? Math.PI * 0.45 : Math.PI * 0.55;
        cr.save();
        // showText() leaves a current point; start a fresh path.
        cr.newPath();
        cr.setLineWidth(1.6);
        cr.setLineCap(Cairo.LineCap.ROUND);
        cr.setSourceRGBA(...color);
        if (clockwise)
            cr.arc(x, y, radius, start, end);
        else
            cr.arcNegative(x, y, radius, start, end);
        cr.stroke();
        const tipX = x + Math.cos(end) * radius;
        const tipY = y + Math.sin(end) * radius;
        const tangent = end + (clockwise ? Math.PI / 2 : -Math.PI / 2);
        for (const spread of [0.5, -0.5]) {
            const angle = tangent + Math.PI + spread;
            cr.moveTo(tipX, tipY);
            cr.lineTo(tipX + Math.cos(angle) * 4, tipY + Math.sin(angle) * 4);
        }
        cr.stroke();
        cr.restore();
    }

    _roundedRect(cr, x, y, width, height, radius) {
        cr.newSubPath();
        cr.arc(x + width - radius, y + radius, radius, -Math.PI / 2, 0);
        cr.arc(x + width - radius, y + height - radius, radius, 0, Math.PI / 2);
        cr.arc(x + radius, y + height - radius, radius, Math.PI / 2, Math.PI);
        cr.arc(x + radius, y + radius, radius, Math.PI, 1.5 * Math.PI);
        cr.closePath();
    }

    _setFont(cr, size, bold) {
        cr.setFontSize(size);
        cr.selectFontFace(FONT, Cairo.FontSlant.NORMAL, bold ? Cairo.FontWeight.BOLD : Cairo.FontWeight.NORMAL);
    }

    _drawCenteredText(cr, text, x, y, size, color, bold) {
        cr.save();
        cr.setSourceRGBA(...color);
        this._setFont(cr, size, bold);
        const extents = cr.textExtents(text);
        cr.moveTo(x - extents.width / 2 - extents.xBearing, y + extents.height / 2);
        cr.showText(text);
        cr.restore();
    }

    _drawAlignedText(cr, text, x, y, size, color, align) {
        cr.save();
        cr.setSourceRGBA(...color);
        this._setFont(cr, size, false);
        const extents = cr.textExtents(text);
        const left = align === 'right' ? x - extents.width - extents.xBearing : x - extents.xBearing;
        cr.moveTo(left, y + extents.height / 2);
        cr.showText(text);
        cr.restore();
    }
}
